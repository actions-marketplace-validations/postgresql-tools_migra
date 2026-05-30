from __future__ import unicode_literals

import io
import json
import os
import tempfile
from pathlib import Path
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
        "1. SAFE: Adds an email column (text) to the users table.\n"
        "   No existing data is affected.\n\n"
        "Overall risk: LOW\n"
    )
    mock_response.content = mock_message.content
    mock_client.messages.create.return_value = mock_response

    patcher = patch("anthropic.Anthropic", return_value=mock_client)
    mock_anthropic_class = patcher.start()
    return patcher, mock_anthropic_class, mock_client


# ---- API key redaction tests ----


class TestRedactApiKey:
    def test_redacts_full_key(self):
        from migra.ai_explain import redact_api_key

        result = redact_api_key("sk-ant-something123-secret456")
        assert result == "sk-ant-***"

    def test_redacts_key_in_sentence(self):
        from migra.ai_explain import redact_api_key

        result = redact_api_key("Error: key sk-ant-abc123 is invalid")
        assert "sk-ant-***" in result
        assert "sk-ant-abc123" not in result

    def test_no_key_no_change(self):
        from migra.ai_explain import redact_api_key

        result = redact_api_key("Hello, world!")
        assert result == "Hello, world!"

    def test_multiple_keys_redacted(self):
        from migra.ai_explain import redact_api_key

        result = redact_api_key("sk-ant-key1 and sk-ant-key2")
        assert result.count("sk-ant-***") == 2


# ---- API key resolution tests ----


class TestResolveApiKey:
    def test_cli_flag_takes_precedence(self):
        from migra.ai_explain import resolve_api_key

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key"}, clear=True):
            with patch(
                "migra.ai_explain.load_config",
                return_value={"anthropic_api_key": "cfg-key"},
            ):
                result = resolve_api_key(cli_key="cli-key")
                assert result == "cli-key"

    def test_env_var_used_when_no_cli_flag(self):
        from migra.ai_explain import resolve_api_key

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key"}, clear=True):
            with patch("migra.ai_explain.load_config", return_value=None):
                result = resolve_api_key(cli_key=None)
                assert result == "env-key"

    def test_config_file_used_when_no_env_or_flag(self):
        from migra.ai_explain import resolve_api_key

        with patch.dict(os.environ, {}, clear=True):
            with patch(
                "migra.ai_explain.load_config",
                return_value={"anthropic_api_key": "cfg-key"},
            ):
                result = resolve_api_key(cli_key=None)
                assert result == "cfg-key"

    def test_no_key_found(self):
        from migra.ai_explain import resolve_api_key

        with patch.dict(os.environ, {}, clear=True):
            with patch("migra.ai_explain.load_config", return_value=None):
                result = resolve_api_key(cli_key=None)
                assert result is None


# ---- Config file tests ----


class TestConfigFile:
    def test_save_and_load(self):
        from migra.ai_explain import save_config, load_config

        with tempfile.TemporaryDirectory() as td:
            with patch("migra.ai_explain._config_dir") as mock_dir:
                mock_dir.return_value = Path(td)
                config = {
                    "anthropic_api_key": "sk-ant-test-key",
                    "ai_model": "claude-haiku-4-5-20251001",
                }
                save_config(config)
                loaded = load_config()
                assert loaded["anthropic_api_key"] == "sk-ant-test-key"
                assert loaded["ai_model"] == "claude-haiku-4-5-20251001"
                config_path = Path(td) / "config.json"
                assert config_path.exists()

    def test_load_nonexistent(self):
        from migra.ai_explain import load_config

        with tempfile.TemporaryDirectory() as td:
            with patch("migra.ai_explain._config_dir") as mock_dir:
                mock_dir.return_value = Path(td) / "nonexistent"
                result = load_config()
                assert result is None

    def test_existing_config_preserved_on_update(self):
        from migra.ai_explain import save_config, load_config

        with tempfile.TemporaryDirectory() as td:
            with patch("migra.ai_explain._config_dir") as mock_dir:
                mock_dir.return_value = Path(td)
                save_config(
                    {
                        "anthropic_api_key": "old-key",
                        "ai_model": "claude-haiku-4-5-20251001",
                        "explain_verbosity": "standard",
                    }
                )
                loaded = load_config()
                loaded["anthropic_api_key"] = "new-key"
                save_config(loaded)
                reloaded = load_config()
                assert reloaded["anthropic_api_key"] == "new-key"
                assert reloaded["ai_model"] == "claude-haiku-4-5-20251001"
                assert reloaded["explain_verbosity"] == "standard"


# ---- Prompt building tests ----


class TestBuildExplainPrompt:
    def test_basic_prompt_structure(self):
        from migra.ai_explain import build_explain_prompt

        sql = "ALTER TABLE public.users ADD COLUMN email text;"
        prompt = build_explain_prompt(sql, "2026-05-30T00:00:00Z", 1, False)

        assert "Migration script to explain:" in prompt
        assert sql in prompt
        assert "MigraDiff (PostgreSQL schema diff)" in prompt
        assert "2026-05-30T00:00:00Z" in prompt
        assert "Statements: 1" in prompt
        assert "Destructive operations detected: no" in prompt

    def test_destructive_detected(self):
        from migra.ai_explain import build_explain_prompt

        prompt = build_explain_prompt("DROP TABLE t;", "ts", 1, True)
        assert "Destructive operations detected: yes" in prompt


# ---- AIExplainer tests ----


class TestAIExplainer:
    def test_explain_basic(self):
        from migra.ai_explain import AIExplainer

        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            explainer = AIExplainer(api_key="sk-ant-test-key")
            result = explainer.explain(
                "ALTER TABLE public.users ADD COLUMN email text;",
                [{"risk": "safe", "sql": "ALTER TABLE..."}],
            )

            assert "text" in result
            assert "model" in result
            assert "generated_at" in result
            assert result["model"] == "claude-haiku-4-5-20251001"
            assert "SAFE" in result["text"]

            mock_client.messages.create.assert_called_once()
            call_kwargs = mock_client.messages.create.call_args[1]
            assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
            assert call_kwargs["max_tokens"] == 1024
            assert call_kwargs["temperature"] == 0
            assert "system" in call_kwargs
        finally:
            patcher.stop()

    def test_explain_empty_diff(self):
        from migra.ai_explain import AIExplainer

        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            explainer = AIExplainer(api_key="sk-ant-test-key")
            explainer.explain("", [])
            mock_client.messages.create.assert_called_once()
        finally:
            patcher.stop()

    def test_explain_error_redacts_key(self):
        from migra.ai_explain import AIExplainer

        patcher = patch("anthropic.Anthropic")
        mock_anthropic_class = patcher.start()
        mock_client = MagicMock()
        error_msg = "API error: sk-ant-invalid-key-12345 is invalid"
        mock_client.messages.create.side_effect = RuntimeError(error_msg)
        mock_anthropic_class.return_value = mock_client

        try:
            explainer = AIExplainer(api_key="sk-ant-invalid-key-12345")
            with pytest.raises(RuntimeError) as exc_info:
                explainer.explain("SELECT 1;", [{"risk": "safe", "sql": "SELECT 1;"}])
            error_text = str(exc_info.value)
            assert "sk-ant-***" in error_text
            assert "sk-ant-invalid-key-12345" not in error_text
        finally:
            patcher.stop()


# ---- --setup-ai command tests ----


class TestSetupAI:
    def test_setup_ai_missing_package(self):
        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "anthropic":
                raise ImportError("No module named 'anthropic'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            from migra.command import parse_args, run

            args = parse_args(["--setup-ai"])
            out, err = io.StringIO(), io.StringIO()
            status = run(args, out=out, err=err)
            assert status == 1
            assert "AI extras" in err.getvalue()

    def test_setup_ai_produces_output(self):
        from migra.ai_explain import setup_ai_interactive

        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client

            with patch("getpass.getpass", return_value="sk-ant-valid-key"):
                with tempfile.TemporaryDirectory() as td:
                    with patch("migra.ai_explain._config_dir") as mock_dir:
                        mock_dir.return_value = Path(td) / ".migradiff"

                        out, err = io.StringIO(), io.StringIO()
                        status = setup_ai_interactive(out, err)
                        assert status == 0
                        output = out.getvalue()
                        assert "Key validated successfully" in output
                        assert "setup-ai" not in output  # No error

    def test_setup_ai_invalid_key(self):
        from migra.ai_explain import setup_ai_interactive

        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = RuntimeError("401 invalid")
            mock_anthropic.return_value = mock_client

            with patch("getpass.getpass", return_value="sk-ant-bad-key"):
                out, err = io.StringIO(), io.StringIO()
                status = setup_ai_interactive(out, err)
                assert status == 1
                assert "failed" in err.getvalue().lower()


# ---- --explain flag integration tests (mocked) ----


class TestExplainIntegration:
    def test_explain_no_key(self):
        """--explain without any API key should print error and exit 1."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("migra.ai_explain.load_config", return_value=None):
                args = parse_args(["--explain", "EMPTY", "EMPTY"])
                out, err = io.StringIO(), io.StringIO()
                status = run(args, out=out, err=err)
                assert status == 1
                assert "API key" in err.getvalue()
                assert "console.anthropic" in err.getvalue()

    def test_explain_missing_package(self):
        """--explain without anthropic package should print error."""
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
                args = parse_args(["--explain", "EMPTY", "EMPTY"])
                out, err = io.StringIO(), io.StringIO()
                status = run(args, out=out, err=err)
                assert status == 1
                assert "AI extras" in err.getvalue()

    def test_explain_empty_diff_with_key(self):
        """--explain with API key and identical schemas."""
        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            with patch.dict(
                os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=True
            ):
                args = parse_args(["--explain", "EMPTY", "EMPTY"])
                out, err = io.StringIO(), io.StringIO()
                status = run(args, out=out, err=err)
                assert status == 0
                output = out.getvalue()
                assert "No schema differences detected" in output
                assert "The schemas are identical" in output
        finally:
            patcher.stop()

    def test_explain_json_empty_diff(self):
        """--explain + --output json with identical schemas."""
        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            with patch.dict(
                os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=True
            ):
                args = parse_args(["--explain", "--output", "json", "EMPTY", "EMPTY"])
                out, err = io.StringIO(), io.StringIO()
                status = run(args, out=out, err=err)
                assert status == 0
                data = json.loads(out.getvalue())
                assert "explanation" not in data
                assert data["summary"]["total_statements"] == 0
        finally:
            patcher.stop()


# ---- Security tests ----


class TestSecurity:
    def test_api_key_not_in_output(self):
        """API key should never appear in stdout or stderr."""
        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            with patch.dict(
                os.environ,
                {"ANTHROPIC_API_KEY": "sk-ant-test-secret-key-12345"},
                clear=True,
            ):
                args = parse_args(["--explain", "EMPTY", "EMPTY"])
                out, err = io.StringIO(), io.StringIO()
                run(args, out=out, err=err)
                output = out.getvalue() + err.getvalue()
                assert "sk-ant-test-secret-key-12345" not in output
        finally:
            patcher.stop()

    def test_key_redaction_regex(self):
        """Verify the redaction regex works on various key formats."""
        from migra.ai_explain import redact_api_key

        keys = [
            "sk-ant-something",
            "sk-ant-a1b2c3d4e5",
            "sk-ant-abc-def-ghi",
        ]
        for key in keys:
            result = redact_api_key("Error: {} is invalid".format(key))
            assert "sk-ant-***" in result
            assert key not in result


# ---- --explain with --force-destructive flag (via EMPTY) ----


class TestExplainWithFlags:
    def test_explain_with_force_destructive(self):
        """--explain + --force-destructive should not error on key check."""
        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            with patch.dict(
                os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=True
            ):
                args = parse_args(
                    ["--explain", "--force-destructive", "EMPTY", "EMPTY"]
                )
                out, err = io.StringIO(), io.StringIO()
                status = run(args, out=out, err=err)
                assert status == 0
                output = out.getvalue()
                assert "No schema differences detected" in output
        finally:
            patcher.stop()

    def test_explain_with_api_key_flag(self):
        """--api-key flag should be used for key resolution."""
        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            with patch.dict(os.environ, {}, clear=True):
                with patch("migra.ai_explain.load_config", return_value=None):
                    args = parse_args(
                        [
                            "--explain",
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


# ---- validate_api_key tests ----


class TestValidateApiKey:
    def test_valid_key_succeeds(self):
        from migra.ai_explain import validate_api_key

        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client
            result = validate_api_key("sk-ant-valid")
            assert result is True

    def test_invalid_key_raises(self):
        from migra.ai_explain import validate_api_key

        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = RuntimeError("401 invalid")
            mock_anthropic.return_value = mock_client
            with pytest.raises((ValueError, RuntimeError)):
                validate_api_key("sk-ant-bad")


# ---- resolve_api_key integration with command flow ----


class TestKeyResolutionInCommand:
    def test_env_var_used(self):
        """ANTHROPIC_API_KEY env var is used when no --api-key."""
        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            with patch.dict(
                os.environ, {"ANTHROPIC_API_KEY": "sk-ant-env-key"}, clear=True
            ):
                with patch("migra.ai_explain.load_config", return_value=None):
                    args = parse_args(["--explain", "EMPTY", "EMPTY"])
                    out, err = io.StringIO(), io.StringIO()
                    status = run(args, out=out, err=err)
                    assert status == 0
        finally:
            patcher.stop()

    def test_config_file_used(self):
        """Config file key is used when no env var or --api-key."""
        patcher, mock_anthropic_mod, mock_client = mock_anthropic()
        try:
            with patch.dict(os.environ, {}, clear=True):
                with patch(
                    "migra.ai_explain.load_config",
                    return_value={"anthropic_api_key": "sk-ant-config-key"},
                ):
                    args = parse_args(["--explain", "EMPTY", "EMPTY"])
                    out, err = io.StringIO(), io.StringIO()
                    status = run(args, out=out, err=err)
                    assert status == 0
        finally:
            patcher.stop()


# ---- --setup-ai preserves existing config ----


class TestSetupAIPreservesConfig:
    def test_update_preserves_other_fields(self):
        from migra.ai_explain import setup_ai_interactive

        with patch("anthropic.Anthropic") as mock_anthropic:
            mock_client = MagicMock()
            mock_anthropic.return_value = mock_client

            with patch("getpass.getpass", return_value="sk-ant-new-key"):
                with tempfile.TemporaryDirectory() as td:

                    config_dir = Path(td) / ".migradiff"
                    config_dir.mkdir()
                    existing = {
                        "anthropic_api_key": "sk-ant-old-key",
                        "ai_model": "claude-haiku-4-5-20251001",
                        "explain_verbosity": "detailed",
                    }
                    with open(config_dir / "config.json", "w") as f:
                        json.dump(existing, f)

                    with patch("migra.ai_explain._config_dir", return_value=config_dir):
                        out, err = io.StringIO(), io.StringIO()
                        status = setup_ai_interactive(out, err)
                        assert status == 0

                        with open(config_dir / "config.json", "r") as f:
                            saved = json.load(f)
                        assert saved["anthropic_api_key"] == "sk-ant-new-key"
                        assert saved["ai_model"] == "claude-haiku-4-5-20251001"
                        assert saved["explain_verbosity"] == "detailed"


# ---- Build explain prompt edge cases ----


class TestBuildExplainPromptEdge:
    def test_large_sql_script(self):
        from migra.ai_explain import build_explain_prompt

        sql = "\n".join(
            ["CREATE TABLE public.t{} (id int);".format(i) for i in range(10)]
        )
        prompt = build_explain_prompt(sql, "ts", 10, True)
        assert "Destructive operations detected: yes" in prompt
        assert "Statements: 10" in prompt

    def test_no_destructive(self):
        from migra.ai_explain import build_explain_prompt

        prompt = build_explain_prompt("CREATE TABLE t (id int);", "ts", 1, False)
        assert "Destructive operations detected: no" in prompt


# ---- Config dir creation permission test ----


class TestConfigDirPermissions:
    def test_config_dir_created_with_permissions(self):
        """Config dir is created with proper mode (Unix only; skip on Windows)."""
        import sys

        if sys.platform == "win32":
            pytest.skip("chmod not enforced on Windows")

        from migra.ai_explain import save_config

        with tempfile.TemporaryDirectory() as td:
            config_dir = Path(td) / ".migradiff"
            with patch("migra.ai_explain._config_dir", return_value=config_dir):
                save_config({"anthropic_api_key": "sk-ant-test"})
                assert config_dir.exists()
                mode = os.stat(str(config_dir)).st_mode
                assert mode & 0o777 == 0o700

    def test_config_file_created_with_600_permissions(self):
        """Config file is created with chmod 600 (Unix only; skip on Windows)."""
        import sys

        if sys.platform == "win32":
            pytest.skip("chmod not enforced on Windows")

        from migra.ai_explain import save_config

        with tempfile.TemporaryDirectory() as td:
            config_dir = Path(td) / ".migradiff"
            with patch("migra.ai_explain._config_dir", return_value=config_dir):
                save_config({"anthropic_api_key": "sk-ant-test"})
                config_path = config_dir / "config.json"
                assert config_path.exists()
                mode = os.stat(str(config_path)).st_mode
                assert mode & 0o777 == 0o600
