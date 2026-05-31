from __future__ import unicode_literals

import io
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from migra.command import parse_args, run

# ---- Helpers ----


def outs():
    return io.StringIO(), io.StringIO()


def mock_anthropic():
    """Patch anthropic.Anthropic so lazy imports see the mock."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_message = MagicMock()
    mock_message.content = [MagicMock()]
    mock_message.content[0].text = (
        "ALTER TABLE public.users DROP COLUMN email;\n"
        "\n"
        "CREATE TABLE public.legacy_sessions (\n"
        "    id serial PRIMARY KEY,\n"
        "    user_id integer\n"
        ");"
    )
    mock_response.content = mock_message.content
    mock_client.messages.create.return_value = mock_response

    patcher = patch("anthropic.Anthropic", return_value=mock_client)
    mock_anthropic_class = patcher.start()
    return patcher, mock_anthropic_class, mock_client


# ---- Deterministic rollback generation tests ----


class TestGenerateDeterministicRollback:
    def test_add_column(self):
        from migra.ai_explain import generate_deterministic_rollback

        sql = "ALTER TABLE public.users ADD COLUMN email text;"
        rollback, needs_ai = generate_deterministic_rollback(sql)
        assert 'ALTER TABLE public.users DROP COLUMN "email";' in rollback
        assert needs_ai == []

    def test_create_index(self):
        from migra.ai_explain import generate_deterministic_rollback

        sql = "CREATE INDEX idx_users_email ON public.users (email);"
        rollback, needs_ai = generate_deterministic_rollback(sql)
        assert 'DROP INDEX IF EXISTS "idx_users_email";' in rollback
        assert needs_ai == []

    def test_create_enum_type(self):
        from migra.ai_explain import generate_deterministic_rollback

        sql = "CREATE TYPE public.mood AS ENUM ('happy', 'sad');"
        rollback, needs_ai = generate_deterministic_rollback(sql)
        assert 'DROP TYPE IF EXISTS "public.mood";' in rollback
        assert needs_ai == []

    def test_rename_column(self):
        from migra.ai_explain import generate_deterministic_rollback

        sql = "ALTER TABLE public.users RENAME COLUMN email TO email_address;"
        rollback, needs_ai = generate_deterministic_rollback(sql)
        assert 'RENAME COLUMN "email_address" TO "email"' in rollback
        assert needs_ai == []

    def test_add_constraint(self):
        from migra.ai_explain import generate_deterministic_rollback

        sql = "ALTER TABLE public.users ADD CONSTRAINT uq_email UNIQUE (email);"
        rollback, needs_ai = generate_deterministic_rollback(sql)
        assert 'DROP CONSTRAINT IF EXISTS "uq_email"' in rollback
        assert needs_ai == []

    def test_create_schema(self):
        from migra.ai_explain import generate_deterministic_rollback

        sql = "CREATE SCHEMA IF NOT EXISTS staging;"
        rollback, needs_ai = generate_deterministic_rollback(sql)
        assert 'DROP SCHEMA IF EXISTS "staging";' in rollback
        assert needs_ai == []

    def test_set_default(self):
        from migra.ai_explain import generate_deterministic_rollback

        sql = "ALTER TABLE public.users ALTER COLUMN status SET DEFAULT 'active';"
        rollback, needs_ai = generate_deterministic_rollback(sql)
        assert (
            'ALTER TABLE public.users ALTER COLUMN "status" DROP DEFAULT;' in rollback
        )
        assert needs_ai == []

    def test_drop_table_needs_ai(self):
        from migra.ai_explain import generate_deterministic_rollback

        sql = "DROP TABLE public.legacy_sessions;"
        rollback, needs_ai = generate_deterministic_rollback(sql)
        assert rollback == ""
        assert needs_ai == [sql.strip()]

    def test_drop_column_needs_ai(self):
        from migra.ai_explain import generate_deterministic_rollback

        sql = "ALTER TABLE public.users DROP COLUMN email;"
        rollback, needs_ai = generate_deterministic_rollback(sql)
        assert rollback == ""
        assert needs_ai == [sql.strip()]

    def test_alter_column_type_needs_ai(self):
        from migra.ai_explain import generate_deterministic_rollback

        sql = "ALTER TABLE public.users ALTER COLUMN status TYPE varchar(50);"
        rollback, needs_ai = generate_deterministic_rollback(sql)
        assert rollback == ""
        assert needs_ai == [sql.strip()]

    def test_truncate_non_reversible(self):
        from migra.ai_explain import generate_deterministic_rollback

        sql = "TRUNCATE TABLE public.audit_log;"
        rollback, needs_ai = generate_deterministic_rollback(sql)
        assert "CANNOT ROLLBACK" in rollback
        assert "TRUNCATE" in rollback
        assert "Data has been permanently deleted" in rollback
        assert needs_ai == []

    def test_multiple_statements_reversed_order(self):
        from migra.ai_explain import generate_deterministic_rollback

        sql = "CREATE INDEX idx_a ON t (a);\n" "CREATE INDEX idx_b ON t (b);\n"
        rollback, needs_ai = generate_deterministic_rollback(sql)
        idx_a_pos = rollback.find("idx_a")
        idx_b_pos = rollback.find("idx_b")
        assert idx_b_pos < idx_a_pos  # reversed order

    def test_empty_sql(self):
        from migra.ai_explain import generate_deterministic_rollback

        rollback, needs_ai = generate_deterministic_rollback("")
        assert rollback == ""
        assert needs_ai == []

    def test_whitespace_only(self):
        from migra.ai_explain import generate_deterministic_rollback

        rollback, needs_ai = generate_deterministic_rollback("   \n\n  ")
        assert rollback == ""
        assert needs_ai == []

    def test_drop_type_needs_ai(self):
        from migra.ai_explain import generate_deterministic_rollback

        sql = "DROP TYPE public.mood;"
        rollback, needs_ai = generate_deterministic_rollback(sql)
        assert rollback == ""
        assert needs_ai == [sql.strip()]


# ---- Rollback prompt building tests ----


class TestBuildRollbackPrompt:
    def test_basic_prompt_structure(self):
        from migra.ai_explain import build_rollback_prompt

        sql = "ALTER TABLE public.users ADD COLUMN email text;"
        prompt = build_rollback_prompt(sql)
        assert "Migration to reverse:" in prompt
        assert sql in prompt
        assert "No schema context available." in prompt
        assert "Generate the complete rollback migration in reverse order" in prompt

    def test_with_schema_context(self):
        from migra.ai_explain import build_rollback_prompt

        sql = "DROP TABLE public.users;"
        ctx = "CREATE TABLE public.users (id integer);"
        prompt = build_rollback_prompt(sql, ctx)
        assert ctx in prompt
        assert "No schema context" not in prompt


# ---- AIRollback class tests ----


class TestAIRollback:
    def test_rollback_deterministic_only(self):
        from migra.ai_explain import AIRollback

        rollbacker = AIRollback(api_key="sk-ant-test-key")
        result = rollbacker.generate_rollback(
            "ALTER TABLE public.users ADD COLUMN email text;"
        )
        assert "text" in result
        assert "model" in result
        assert "generated_at" in result
        assert result["model"] == "deterministic"
        assert "DROP COLUMN" in result["text"]

    def test_rollback_with_ai(self):
        from migra.ai_explain import AIRollback

        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            rollbacker = AIRollback(api_key="sk-ant-test-key")
            result = rollbacker.generate_rollback(
                "DROP TABLE public.legacy_sessions;",
                source_schema_context=(
                    "CREATE TABLE public.legacy_sessions (id serial PRIMARY KEY);"
                ),
            )
            assert "text" in result
            assert result["model"] == "claude-haiku-4-5-20251001"
            assert "Original Migration" in result["text"]
            assert "Rollback Migration" in result["text"]

            mock_client.messages.create.assert_called_once()
            call_kwargs = mock_client.messages.create.call_args[1]
            assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
            assert call_kwargs["max_tokens"] == 2048
            assert call_kwargs["temperature"] == 0
        finally:
            patcher.stop()

    def test_rollback_error_redacts_key(self):
        from migra.ai_explain import AIRollback

        patcher = patch("anthropic.Anthropic")
        mock_anthropic_class = patcher.start()
        mock_client = MagicMock()
        error_msg = "API error: sk-ant-invalid-key-12345 is invalid"
        mock_client.messages.create.side_effect = RuntimeError(error_msg)
        mock_anthropic_class.return_value = mock_client

        try:
            rollbacker = AIRollback(api_key="sk-ant-invalid-key-12345")
            with pytest.raises(RuntimeError) as exc_info:
                rollbacker.generate_rollback(
                    "DROP TABLE public.t;",
                    source_schema_context="CREATE TABLE public.t (id int);",
                )
            error_text = str(exc_info.value)
            assert "sk-ant-***" in error_text
            assert "sk-ant-invalid-key-12345" not in error_text
        finally:
            patcher.stop()

    def test_rollback_empty_migration(self):
        from migra.ai_explain import AIRollback

        rollbacker = AIRollback(api_key="sk-ant-test-key")
        result = rollbacker.generate_rollback("")
        assert result["text"] == ""


# ---- generate_file_rollback tests ----


class TestGenerateFileRollback:
    def test_file_add_column(self):
        from migra.ai_explain import generate_file_rollback

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            f.write("ALTER TABLE public.users ADD COLUMN email text;")
            f.flush()
            fname = f.name

        try:
            result = generate_file_rollback(fname)
            assert "DROP COLUMN" in result["text"]
            assert result["model"] == "deterministic"
        finally:
            os.unlink(fname)

    def test_file_drop_table_no_context(self):
        from migra.ai_explain import generate_file_rollback

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            f.write("DROP TABLE public.legacy_sessions;")
            f.flush()
            fname = f.name

        try:
            result = generate_file_rollback(fname)
            assert "WARNING" in result["text"]
            assert (
                "DROP TABLE reversal requires original schema context" in result["text"]
            )
            assert result["model"] == ""
        finally:
            os.unlink(fname)

    def test_file_truncate(self):
        from migra.ai_explain import generate_file_rollback

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            f.write("TRUNCATE TABLE public.audit_log;")
            f.flush()
            fname = f.name

        try:
            result = generate_file_rollback(fname)
            assert "CANNOT ROLLBACK" in result["text"]
            assert "TRUNCATE" in result["text"]
        finally:
            os.unlink(fname)

    def test_file_empty(self):
        from migra.ai_explain import generate_file_rollback

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            f.write("")
            f.flush()
            fname = f.name

        try:
            result = generate_file_rollback(fname)
            assert result["text"] == "Nothing to roll back"
        finally:
            os.unlink(fname)

    def test_file_not_found(self):
        from migra.ai_explain import generate_file_rollback

        with pytest.raises(ValueError):
            generate_file_rollback("/nonexistent/file.sql")


# ---- --rollback flag integration tests (mocked) ----


class TestRollbackIntegration:
    def test_rollback_no_key(self):
        """--rollback without API key should print error and exit 1."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("migra.ai_explain.load_config", return_value=None):
                args = parse_args(["--rollback", "--", "EMPTY", "EMPTY"])
                out, err = io.StringIO(), io.StringIO()
                status = run(args, out=out, err=err)
                assert status == 1
                assert "API key" in err.getvalue()
                assert "console.anthropic" in err.getvalue()

    def test_rollback_missing_package(self):
        """--rollback without anthropic package should print error."""
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
                args = parse_args(["--rollback", "--", "EMPTY", "EMPTY"])
                out, err = io.StringIO(), io.StringIO()
                status = run(args, out=out, err=err)
                assert status == 1
                assert "AI extras" in err.getvalue()

    def test_rollback_empty_diff_with_key(self):
        """--rollback with API key and identical schemas."""
        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            with patch.dict(
                os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=True
            ):
                args = parse_args(["--rollback", "--", "EMPTY", "EMPTY"])
                out, err = io.StringIO(), io.StringIO()
                status = run(args, out=out, err=err)
                assert status == 0
                output = out.getvalue()
                assert "No schema differences detected" in output
        finally:
            patcher.stop()

    def test_rollback_json_empty_diff(self):
        """--rollback + --output json with identical schemas."""
        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            with patch.dict(
                os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=True
            ):
                args = parse_args(["--rollback", "--output", "json", "EMPTY", "EMPTY"])
                out, err = io.StringIO(), io.StringIO()
                status = run(args, out=out, err=err)
                assert status == 0
                data = json.loads(out.getvalue())
                assert data["summary"]["total_statements"] == 0
        finally:
            patcher.stop()


# ---- Combined --explain and --rollback tests ----


class TestCombinedExplainRollback:
    def test_explain_and_rollback_empty_diff(self):
        """--explain --rollback with identical schemas."""
        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            with patch.dict(
                os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=True
            ):
                args = parse_args(["--explain", "--rollback", "--", "EMPTY", "EMPTY"])
                out, err = io.StringIO(), io.StringIO()
                status = run(args, out=out, err=err)
                assert status == 0
                output = out.getvalue()
                assert "No schema differences detected" in output
        finally:
            patcher.stop()

    def test_rollback_file_flag(self):
        """--rollback with a migration file path."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            f.write("ALTER TABLE public.users ADD COLUMN email text;")
            f.flush()
            fname = f.name

        try:
            args = parse_args(["--rollback", fname])
            out, err = io.StringIO(), io.StringIO()
            status = run(args, out=out, err=err)
            assert status == 0
            output = out.getvalue()
            assert "DROP COLUMN" in output
        finally:
            os.unlink(fname)


# ---- --rollback with --safe flag ---


class TestRollbackWithFlags:
    def test_rollback_with_force_destructive(self):
        """--rollback + --force-destructive should not error on key check."""
        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            with patch.dict(
                os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=True
            ):
                args = parse_args(
                    ["--rollback", "--force-destructive", "EMPTY", "EMPTY"]
                )
                out, err = io.StringIO(), io.StringIO()
                status = run(args, out=out, err=err)
                assert status == 0
                output = out.getvalue()
                assert "No schema differences detected" in output
        finally:
            patcher.stop()

    def test_rollback_with_api_key_flag(self):
        """--api-key flag should work with --rollback."""
        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            with patch.dict(os.environ, {}, clear=True):
                with patch("migra.ai_explain.load_config", return_value=None):
                    args = parse_args(
                        [
                            "--rollback",
                            "--api-key",
                            "sk-ant-cli-key",
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


class TestRollbackSecurity:
    def test_api_key_not_in_output(self):
        """API key should never appear in stdout or stderr."""
        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            with patch.dict(
                os.environ,
                {"ANTHROPIC_API_KEY": "sk-ant-test-secret-key-12345"},
                clear=True,
            ):
                args = parse_args(["--rollback", "--", "EMPTY", "EMPTY"])
                out, err = io.StringIO(), io.StringIO()
                run(args, out=out, err=err)
                output = out.getvalue() + err.getvalue()
                assert "sk-ant-test-secret-key-12345" not in output
        finally:
            patcher.stop()


# ---- _split_statements tests ----


class TestSplitStatements:
    def test_single_statement(self):
        from migra.ai_explain import _split_statements

        stmts = _split_statements("ALTER TABLE t ADD COLUMN c text;")
        assert len(stmts) == 1

    def test_multiple_statements(self):
        from migra.ai_explain import _split_statements

        sql = "CREATE INDEX a ON t (a);\nCREATE INDEX b ON t (b);"
        stmts = _split_statements(sql)
        assert len(stmts) == 2

    def test_empty_input(self):
        from migra.ai_explain import _split_statements

        assert _split_statements("") == []


# ---- extract_drop_references tests ----


class TestExtractDropReferences:
    def test_drop_table(self):
        from migra.ai_explain import extract_drop_references

        refs = extract_drop_references("DROP TABLE public.users;")
        assert "PUBLIC.USERS" in refs["tables"]

    def test_drop_column(self):
        from migra.ai_explain import extract_drop_references

        refs = extract_drop_references("ALTER TABLE public.users DROP COLUMN email;")
        assert len(refs["columns"]) == 1
        assert refs["columns"][0]["table"] == "PUBLIC.USERS"
        assert refs["columns"][0]["column"] == "EMAIL"

    def test_no_drops(self):
        from migra.ai_explain import extract_drop_references

        refs = extract_drop_references("ALTER TABLE t ADD COLUMN c text;")
        assert refs["tables"] == []
        assert refs["columns"] == []
        assert refs["types"] == []

    def test_empty_input(self):
        from migra.ai_explain import extract_drop_references

        refs = extract_drop_references("")
        assert refs["tables"] == []
        assert refs["columns"] == []
        assert refs["types"] == []
