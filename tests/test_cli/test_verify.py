from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from ks_gen.cli import app
from ks_gen.loader import ExitCode
from ks_gen.verify.errors import (
    OscapInvocationError,
    SshConnectError,
    SudoPromptError,
    ToolMissingError,
)
from ks_gen.verify.reconcile import VerifyReport, VerifyRow

VALID_YAML = textwrap.dedent(
    """\
    system: {hostname: h1}
    user:
      admin:
        name: ops
        authorized_keys: ["ssh-ed25519 A a@b"]
        sudo: nopasswd_yes
    """
)


def _write_cfg(tmp_path: Path) -> Path:
    p = tmp_path / "host.yaml"
    p.write_text(VALID_YAML, encoding="utf-8")
    return p


def _clean_report() -> VerifyReport:
    return VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-07T12:00:00Z",
        rows=(VerifyRow("rule_a", "pass", "pass", False, "clean"),),
        install_baseline_available=True,
    )


def _failing_report() -> VerifyReport:
    return VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-07T12:00:00Z",
        rows=(VerifyRow("rule_b", "fail", "pass", False, "regression"),),
        install_baseline_available=True,
    )


def test_verify_exits_0_on_clean_report(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with (
        patch("ks_gen.cli.run_verify", return_value=_clean_report()),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(app, ["verify", "--host", "h1", "--config", str(cfg)])
    assert result.exit_code == 0, result.output


def test_verify_exits_6_on_failing_report(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with (
        patch("ks_gen.cli.run_verify", return_value=_failing_report()),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(app, ["verify", "--host", "h1", "--config", str(cfg)])
    assert result.exit_code == 6


@pytest.mark.parametrize(
    "error,expected_exit,fragment",
    [
        (SshConnectError("Connection refused"), 7, "transport"),
        (SudoPromptError("passwordless"), 7, "sudo"),
        (OscapInvocationError("tailoring"), 7, "oscap"),
    ],
)
def test_verify_maps_verify_errors_to_exit_codes(
    tmp_path: Path, error: Exception, expected_exit: int, fragment: str
) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with patch("ks_gen.cli.run_verify", side_effect=error), patch("ks_gen.cli.check_tools"):
        result = runner.invoke(app, ["verify", "--host", "h1", "--config", str(cfg)])
    assert result.exit_code == expected_exit
    assert fragment in result.output.lower()


def test_verify_exit_5_when_ssh_not_on_path(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with patch("ks_gen.cli.check_tools", side_effect=ToolMissingError("ssh")):
        result = runner.invoke(app, ["verify", "--host", "h1", "--config", str(cfg)])
    assert result.exit_code == 5


def test_verify_exit_2_when_config_invalid(tmp_path: Path) -> None:
    cfg = tmp_path / "host.yaml"
    cfg.write_text("not-a-mapping", encoding="utf-8")
    runner = CliRunner()
    with patch("ks_gen.cli.check_tools"):
        result = runner.invoke(app, ["verify", "--host", "h1", "--config", str(cfg)])
    assert result.exit_code == 2


def test_verify_format_json_emits_json(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with (
        patch("ks_gen.cli.run_verify", return_value=_clean_report()),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(
            app, ["verify", "--host", "h1", "--config", str(cfg), "--format", "json"]
        )
    assert result.exit_code == 0
    assert '"host":' in result.output
    assert '"is_clean": true' in result.output


def test_verify_resolves_user_from_host_yaml_when_not_passed(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    captured_user: list[str] = []

    def fake_run(**kwargs: object) -> VerifyReport:
        captured_user.append(str(kwargs["user"]))
        return _clean_report()

    with patch("ks_gen.cli.run_verify", side_effect=fake_run), patch("ks_gen.cli.check_tools"):
        result = runner.invoke(app, ["verify", "--host", "h1", "--config", str(cfg)])
    assert result.exit_code == 0
    assert captured_user == ["ops"]


def test_verify_user_flag_overrides_config(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    captured_user: list[str] = []

    def fake_run(**kwargs: object) -> VerifyReport:
        captured_user.append(str(kwargs["user"]))
        return _clean_report()

    with patch("ks_gen.cli.run_verify", side_effect=fake_run), patch("ks_gen.cli.check_tools"):
        result = runner.invoke(
            app, ["verify", "--host", "h1", "--config", str(cfg), "--user", "audit"]
        )
    assert result.exit_code == 0
    assert captured_user == ["audit"]


def _new_fail_report() -> VerifyReport:
    return VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(
            VerifyRow("rule_d", "fail", "fail", False, "new_fail"),
            VerifyRow("rule_e", "fail", "pass", False, "regression"),
        ),
        install_baseline_available=True,
    )


def test_verify_suggest_exceptions_appends_yaml_block(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with (
        patch("ks_gen.cli.check_tools"),
        patch("ks_gen.cli.run_verify", return_value=_new_fail_report()),
    ):
        result = runner.invoke(
            app,
            ["verify", "--host", "h1", "--config", str(cfg), "--suggest-exceptions"],
        )
    assert result.exit_code == int(ExitCode.VERIFY_FAIL)
    assert "Suggested exception entries" in result.stdout
    assert "auto-new_fail-rule_d" in result.stdout
    assert "auto-regression-rule_e" in result.stdout


def test_verify_suggest_exceptions_json_includes_array(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with (
        patch("ks_gen.cli.check_tools"),
        patch("ks_gen.cli.run_verify", return_value=_new_fail_report()),
    ):
        result = runner.invoke(
            app,
            [
                "verify",
                "--host",
                "h1",
                "--config",
                str(cfg),
                "--suggest-exceptions",
                "--format",
                "json",
            ],
        )
    import json as _json

    payload = _json.loads(result.stdout)
    assert "suggested_exceptions" in payload
    assert len(payload["suggested_exceptions"]) == 2
