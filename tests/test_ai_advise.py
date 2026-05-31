from __future__ import unicode_literals

import io
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from migra.command import parse_args, run

# ---- Helpers ----


def mock_anthropic():
    """Patch anthropic.Anthropic so lazy imports see the mock."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock()]
    mock_message.content[0].text = (
        "Statement 1: ALTER TABLE public.users ADD COLUMN status text DEFAULT 'active'\n"
        "Risk: HIGH\n"
        "Issue: Adding a column with DEFAULT rewrites the table on PG < 11\n"
        "Estimated impact: At 10M+ rows this could take 5-15 minutes\n"
        "Safer alternative: Add column first, set default separately\n\n"
        "Overall Advisory: HIGH RISK\n"
    )
    mock_response.content = mock_message.content
    mock_client.messages.create.return_value = mock_response

    patcher = patch("anthropic.Anthropic", return_value=mock_client)
    mock_anthropic_class = patcher.start()
    return patcher, mock_anthropic_class, mock_client


# ---- Deterministic pre-classification tests ----


class TestClassifyStatementRisk:
    def test_add_column_with_default_high(self):
        from migra.ai_explain import classify_statement_risk

        result = classify_statement_risk(
            "ALTER TABLE public.users ADD COLUMN status text DEFAULT 'active';"
        )
        assert result["risk"] == "HIGH"
        assert result["confidence"] >= 0.9

    def test_alter_column_type_high(self):
        from migra.ai_explain import classify_statement_risk

        result = classify_statement_risk(
            "ALTER TABLE public.users ALTER COLUMN status TYPE varchar(100);"
        )
        assert result["risk"] == "HIGH"

    def test_create_index_without_concurrently_high(self):
        from migra.ai_explain import classify_statement_risk

        result = classify_statement_risk(
            "CREATE INDEX idx_users_email ON public.users (email);"
        )
        assert result["risk"] == "HIGH"

    def test_create_index_concurrently_medium(self):
        from migra.ai_explain import classify_statement_risk

        result = classify_statement_risk(
            "CREATE INDEX CONCURRENTLY idx_users_email ON public.users (email);"
        )
        assert result["risk"] == "MEDIUM"

    def test_drop_table_high(self):
        from migra.ai_explain import classify_statement_risk

        result = classify_statement_risk("DROP TABLE public.users;")
        assert result["risk"] == "HIGH"

    def test_drop_column_high(self):
        from migra.ai_explain import classify_statement_risk

        result = classify_statement_risk("ALTER TABLE public.users DROP COLUMN email;")
        assert result["risk"] == "HIGH"

    def test_truncate_high(self):
        from migra.ai_explain import classify_statement_risk

        result = classify_statement_risk("TRUNCATE TABLE public.audit_log;")
        assert result["risk"] == "HIGH"

    def test_add_column_no_default_low(self):
        from migra.ai_explain import classify_statement_risk

        result = classify_statement_risk(
            "ALTER TABLE public.users ADD COLUMN email text;"
        )
        assert result["risk"] == "LOW"

    def test_grant_low(self):
        from migra.ai_explain import classify_statement_risk

        result = classify_statement_risk("GRANT SELECT ON public.users TO app_user;")
        assert result["risk"] == "LOW"

    def test_create_schema_low(self):
        from migra.ai_explain import classify_statement_risk

        result = classify_statement_risk("CREATE SCHEMA IF NOT EXISTS staging;")
        assert result["risk"] == "LOW"

    def test_rename_column_medium(self):
        from migra.ai_explain import classify_statement_risk

        result = classify_statement_risk(
            "ALTER TABLE public.users RENAME COLUMN email TO email_address;"
        )
        assert result["risk"] == "MEDIUM"

    def test_alter_table_rename_medium(self):
        from migra.ai_explain import classify_statement_risk

        result = classify_statement_risk(
            "ALTER TABLE public.users RENAME TO app_users;"
        )
        assert result["risk"] == "MEDIUM"


# ---- Advisory prompt building tests ----


class TestBuildAdvisePrompt:
    def test_basic_prompt_structure(self):
        from migra.ai_explain import build_advise_prompt

        sql = "Statement 1: ALTER TABLE t ADD COLUMN c text;"
        prompt = build_advise_prompt(sql)
        assert "Migration statements to analyze:" in prompt
        assert sql in prompt
        assert "Table size statistics unavailable" in prompt
        assert "PostgreSQL 14+" in prompt

    def test_with_table_stats(self):
        from migra.ai_explain import build_advise_prompt

        sql = "Statement 1: DROP TABLE t;"
        stats = "- public.users: ~50000 rows"
        prompt = build_advise_prompt(sql, stats)
        assert stats in prompt
        assert "Table size statistics unavailable" not in prompt


# ---- AIAdvisor class tests ----


class TestAIAdvisor:
    def test_advise_single_statement(self):
        from migra.ai_explain import AIAdvisor

        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            advisor = AIAdvisor(api_key="sk-ant-test-key")
            result = advisor.advise(
                "ALTER TABLE public.users ADD COLUMN status text DEFAULT 'active';",
                [{"risk": "safe"}],
            )

            assert "text" in result
            assert "model" in result
            assert "generated_at" in result
            assert "overall_risk" in result
            assert result["model"] == "claude-haiku-4-5-20251001"
            assert result["overall_risk"] == "HIGH"

            mock_client.messages.create.assert_called_once()
            call_kwargs = mock_client.messages.create.call_args[1]
            assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
            assert call_kwargs["max_tokens"] == 2048
            assert call_kwargs["temperature"] == 0
        finally:
            patcher.stop()

    def test_advise_empty_diff(self):
        from migra.ai_explain import AIAdvisor

        advisor = AIAdvisor(api_key="sk-ant-test-key")
        result = advisor.advise("", [])
        assert "No statements to analyze" in result["text"]
        assert result["model"] == ""

    def test_advise_error_redacts_key(self):
        from migra.ai_explain import AIAdvisor

        patcher = patch("anthropic.Anthropic")
        mock_anthropic_class = patcher.start()
        mock_client = MagicMock()
        error_msg = "API error: sk-ant-invalid-key-12345 is invalid"
        mock_client.messages.create.side_effect = RuntimeError(error_msg)
        mock_anthropic_class.return_value = mock_client

        try:
            advisor = AIAdvisor(api_key="sk-ant-invalid-key-12345")
            with pytest.raises(RuntimeError) as exc_info:
                advisor.advise(
                    "ALTER TABLE t ADD COLUMN c text;",
                    [{"risk": "safe"}],
                )
            error_text = str(exc_info.value)
            assert "sk-ant-***" in error_text
            assert "sk-ant-invalid-key-12345" not in error_text
        finally:
            patcher.stop()

    def test_advise_statement_details(self):
        from migra.ai_explain import AIAdvisor

        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            advisor = AIAdvisor(api_key="sk-ant-test-key")
            result = advisor.advise(
                "ALTER TABLE public.users ADD COLUMN status text DEFAULT 'active';\n"
                "GRANT SELECT ON public.users TO app_user;",
                [{"risk": "safe"}, {"risk": "safe"}],
            )

            assert len(result["statement_details"]) == 2
            assert result["statement_details"][0]["risk"] == "HIGH"
            assert result["statement_details"][1]["risk"] == "LOW"
        finally:
            patcher.stop()


# ---- generate_file_advisory tests ----


class TestGenerateFileAdvisory:
    def test_file_add_column(self):
        from migra.ai_explain import generate_file_advisory

        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".sql", delete=False
            ) as f:
                f.write("ALTER TABLE public.users ADD COLUMN email text;")
                f.flush()
                fname = f.name

            try:
                result = generate_file_advisory(fname, api_key="sk-ant-test-key")
                assert "No statements to analyze" not in result["text"]
            finally:
                os.unlink(fname)
        finally:
            patcher.stop()

    def test_file_empty(self):
        from migra.ai_explain import generate_file_advisory

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            f.write("")
            f.flush()
            fname = f.name

        try:
            result = generate_file_advisory(fname, api_key="sk-ant-test-key")
            assert "No statements to analyze" in result["text"]
        finally:
            os.unlink(fname)

    def test_file_not_found(self):
        from migra.ai_explain import generate_file_advisory

        with pytest.raises(ValueError):
            generate_file_advisory("/nonexistent/file.sql")

    def test_no_api_key(self):
        from migra.ai_explain import generate_file_advisory

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            f.write("DROP TABLE t;")
            f.flush()
            fname = f.name

        try:
            result = generate_file_advisory(fname, api_key=None)
            assert "requires an Anthropic API key" in result["text"]
        finally:
            os.unlink(fname)


# ---- --advise flag integration tests (mocked) ----


class TestAdviseIntegration:
    def test_advise_no_key(self):
        """--advise without API key should print error and exit 1."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("migra.ai_explain.load_config", return_value=None):
                args = parse_args(["--advise", "--", "EMPTY", "EMPTY"])
                out, err = io.StringIO(), io.StringIO()
                status = run(args, out=out, err=err)
                assert status == 1
                assert "API key" in err.getvalue()
                assert "console.anthropic" in err.getvalue()

    def test_advise_missing_package(self):
        """--advise without anthropic package should print error."""
        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "anthropic":
                raise ImportError("No module named 'anthropic'")
            return original_import(name, *args, **kwargs)

        with patch.dict(
            os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-key"}, clear=True
        ):
            with patch("builtins.__import__", side_effect=mock_import):
                args = parse_args(["--advise", "--", "EMPTY", "EMPTY"])
                out, err = io.StringIO(), io.StringIO()
                status = run(args, out=out, err=err)
                assert status == 1
                assert "AI extras" in err.getvalue()

    def test_advise_empty_diff(self):
        """--advise with API key and identical schemas."""
        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            with patch.dict(
                os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=True
            ):
                args = parse_args(["--advise", "--", "EMPTY", "EMPTY"])
                out, err = io.StringIO(), io.StringIO()
                status = run(args, out=out, err=err)
                assert status == 0
                output = out.getvalue()
                assert "No schema differences detected" in output
        finally:
            patcher.stop()

    def test_advise_json_empty_diff(self):
        """--advise + --output json with identical schemas."""
        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            with patch.dict(
                os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=True
            ):
                args = parse_args(
                    ["--advise", "--output", "json", "--", "EMPTY", "EMPTY"]
                )
                out, err = io.StringIO(), io.StringIO()
                status = run(args, out=out, err=err)
                assert status == 0
                data = json.loads(out.getvalue())
                assert data["summary"]["total_statements"] == 0
        finally:
            patcher.stop()


# ---- Combined --explain, --advise, --rollback tests ----


class TestCombinedFlags:
    def test_explain_and_advise_empty_diff(self):
        """--explain --advise with identical schemas."""
        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            with patch.dict(
                os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=True
            ):
                args = parse_args(["--explain", "--advise", "--", "EMPTY", "EMPTY"])
                out, err = io.StringIO(), io.StringIO()
                status = run(args, out=out, err=err)
                assert status == 0
                output = out.getvalue()
                assert "No schema differences detected" in output
        finally:
            patcher.stop()

    def test_explain_advise_rollback_empty_diff(self):
        """--explain --advise --rollback with identical schemas."""
        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            with patch.dict(
                os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=True
            ):
                args = parse_args(
                    ["--explain", "--advise", "--rollback", "--", "EMPTY", "EMPTY"]
                )
                out, err = io.StringIO(), io.StringIO()
                status = run(args, out=out, err=err)
                assert status == 0
                output = out.getvalue()
                assert "No schema differences detected" in output
        finally:
            patcher.stop()


# ---- --advise with other flags ----


class TestAdviseWithFlags:
    def test_advise_with_force_destructive(self):
        """--advise + --force-destructive should not error on key check."""
        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            with patch.dict(
                os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=True
            ):
                args = parse_args(
                    ["--advise", "--force-destructive", "--", "EMPTY", "EMPTY"]
                )
                out, err = io.StringIO(), io.StringIO()
                status = run(args, out=out, err=err)
                assert status == 0
                output = out.getvalue()
                assert "No schema differences detected" in output
        finally:
            patcher.stop()

    def test_advise_with_api_key_flag(self):
        """--api-key flag should work with --advise."""
        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            with patch.dict(os.environ, {}, clear=True):
                with patch("migra.ai_explain.load_config", return_value=None):
                    args = parse_args(
                        [
                            "--advise",
                            "--api-key",
                            "sk-ant-cli-key",
                            "--",
                            "EMPTY",
                            "EMPTY",
                        ]
                    )
                    out, err = io.StringIO(), io.StringIO()
                    status = run(args, out=out, err=err)
                    assert status == 0
                    output = out.getvalue()
                    assert "No schema differences detected" in output
        finally:
            patcher.stop()


# ---- Security tests ----


class TestAdviseSecurity:
    def test_api_key_not_in_output(self):
        """API key should never appear in stdout or stderr."""
        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            with patch.dict(
                os.environ,
                {"ANTHROPIC_API_KEY": "sk-ant-test-secret-key-12345"},
                clear=True,
            ):
                args = parse_args(["--advise", "--", "EMPTY", "EMPTY"])
                out, err = io.StringIO(), io.StringIO()
                run(args, out=out, err=err)
                output = out.getvalue() + err.getvalue()
                assert "sk-ant-test-secret-key-12345" not in output
        finally:
            patcher.stop()


# ---- _numbered_sql_statements tests ----


class TestNumberedSqlStatements:
    def test_single_statement(self):
        from migra.ai_explain import _numbered_sql_statements

        result = _numbered_sql_statements("ALTER TABLE t ADD COLUMN c text;")
        assert "Statement 1:" in result

    def test_multiple_statements(self):
        from migra.ai_explain import _numbered_sql_statements

        sql = "CREATE INDEX a ON t (a);\nCREATE INDEX b ON t (b);"
        result = _numbered_sql_statements(sql)
        assert "Statement 1:" in result
        assert "Statement 2:" in result
        assert result.index("Statement 1:") < result.index("Statement 2:")
