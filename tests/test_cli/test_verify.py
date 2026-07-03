from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from ks_gen.cli import app
from ks_gen.loader import ExitCode
from ks_gen.verify.auth import SudoAuth
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


def test_verify_apply_writes_new_fail_to_host_yaml(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with (
        patch("ks_gen.cli.check_tools"),
        patch("ks_gen.cli.run_verify", return_value=_new_fail_report()),
    ):
        result = runner.invoke(
            app,
            ["verify", "--host", "h1", "--config", str(cfg), "--apply"],
        )

    assert result.exit_code == int(ExitCode.VERIFY_FAIL)
    # Suggestions also rendered because --apply implies --suggest-exceptions
    assert "Suggested exception entries" in result.stdout
    # host.yaml now has the new_fail exception, NOT the regression
    import yaml as _yaml

    after = _yaml.safe_load(cfg.read_text(encoding="utf-8"))
    ids = [e["id"] for e in after.get("exceptions", [])]
    assert ids == ["auto-new_fail-rule_d"]
    # Backup exists
    assert (tmp_path / "host.yaml.bak").exists()
    # Stderr summary mentions the regression was held back
    assert "auto-regression-rule_e" in result.stderr or "auto-regression-rule_e" in result.output


def test_verify_apply_allow_regression_writes_regression_too(tmp_path: Path) -> None:
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
                "--apply",
                "--allow-regression",
            ],
        )

    assert result.exit_code == int(ExitCode.VERIFY_FAIL)
    import yaml as _yaml

    after = _yaml.safe_load(cfg.read_text(encoding="utf-8"))
    ids = [e["id"] for e in after.get("exceptions", [])]
    assert ids == ["auto-new_fail-rule_d", "auto-regression-rule_e"]


def test_verify_allow_regression_without_apply_prints_note(tmp_path: Path) -> None:
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
                "--allow-regression",
            ],
        )

    # host.yaml is NOT modified
    import yaml as _yaml

    after = _yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert "exceptions" not in after or after["exceptions"] in (None, [])
    # The note appears on stderr
    assert "--allow-regression has no effect without --apply" in (result.stderr or result.output)


def test_verify_apply_on_clean_report_prints_nothing_to_apply(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with (
        patch("ks_gen.cli.check_tools"),
        patch("ks_gen.cli.run_verify", return_value=_clean_report()),
    ):
        result = runner.invoke(
            app,
            ["verify", "--host", "h1", "--config", str(cfg), "--apply"],
        )

    # Clean report -> exit 0, no host.yaml mutation, no .bak
    assert result.exit_code == 0
    assert not (tmp_path / "host.yaml.bak").exists()
    # Apply summary still confirms the operator was heard.
    assert "nothing to apply" in (result.stderr or result.output)


def _clean_with_drift() -> VerifyReport:
    """Clean compliance, but tailoring drift present."""
    from ks_gen.rules._types import TailoringOp
    from ks_gen.verify.tailoring_drift import TailoringDriftReport

    drift = TailoringDriftReport(
        profile_id_expected="p",
        profile_id_deployed="p",
        added=[TailoringOp("synthetic_rule", "disable")],
        removed=[],
        changed=[],
    )
    return VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(VerifyRow("rule_a", "pass", "pass", False, "clean"),),
        install_baseline_available=True,
        tailoring_drift=drift,
    )


def _failing_with_drift() -> VerifyReport:
    """Compliance fail AND drift — compliance wins."""
    from ks_gen.rules._types import TailoringOp
    from ks_gen.verify.tailoring_drift import TailoringDriftReport

    drift = TailoringDriftReport(
        profile_id_expected="p",
        profile_id_deployed="p",
        added=[TailoringOp("synthetic_rule", "disable")],
        removed=[],
        changed=[],
    )
    return VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(VerifyRow("rule_b", "fail", "pass", False, "regression"),),
        install_baseline_available=True,
        tailoring_drift=drift,
    )


def test_verify_check_tailoring_flag_threads_through(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    captured: dict[str, object] = {}

    def fake_run_verify(**kwargs: object) -> VerifyReport:
        captured.update(kwargs)
        return _clean_report()

    with (
        patch("ks_gen.cli.run_verify", side_effect=fake_run_verify),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(
            app, ["verify", "--host", "h1", "--config", str(cfg), "--check-tailoring"]
        )
    assert result.exit_code == 0, result.output
    assert captured["check_tailoring"] is True


def test_verify_check_tailoring_default_false_when_flag_absent(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    captured: dict[str, object] = {}

    def fake_run_verify(**kwargs: object) -> VerifyReport:
        captured.update(kwargs)
        return _clean_report()

    with (
        patch("ks_gen.cli.run_verify", side_effect=fake_run_verify),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(app, ["verify", "--host", "h1", "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert captured["check_tailoring"] is False


def test_verify_exits_8_on_drift_only(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with (
        patch("ks_gen.cli.run_verify", return_value=_clean_with_drift()),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(
            app, ["verify", "--host", "h1", "--config", str(cfg), "--check-tailoring"]
        )
    assert result.exit_code == 8, result.output


def test_verify_compliance_fail_wins_over_drift(tmp_path: Path) -> None:
    """When both compliance fail and drift, exit 6 (VERIFY_FAIL) — not 8."""
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with (
        patch("ks_gen.cli.run_verify", return_value=_failing_with_drift()),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(
            app, ["verify", "--host", "h1", "--config", str(cfg), "--check-tailoring"]
        )
    assert result.exit_code == 6, result.output


def test_verify_capture_baseline_threads_through(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    out = tmp_path / "captured.arf"
    runner = CliRunner()
    captured: dict[str, object] = {}

    def fake_run_verify(**kwargs: object) -> VerifyReport:
        captured.update(kwargs)
        return _clean_report()

    with (
        patch("ks_gen.cli.run_verify", side_effect=fake_run_verify),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(
            app,
            ["verify", "--host", "h1", "--config", str(cfg), "--capture-baseline", str(out)],
        )
    assert result.exit_code == 0, result.output
    assert captured["capture_to"] == out


def test_verify_baseline_threads_through(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    baseline = tmp_path / "baseline.arf"
    baseline.write_text("<TestResult/>", encoding="utf-8")
    runner = CliRunner()
    captured: dict[str, object] = {}

    def fake_run_verify(**kwargs: object) -> VerifyReport:
        captured.update(kwargs)
        return _clean_report()

    with (
        patch("ks_gen.cli.run_verify", side_effect=fake_run_verify),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(
            app,
            ["verify", "--host", "h1", "--config", str(cfg), "--baseline", str(baseline)],
        )
    assert result.exit_code == 0, result.output
    assert captured["baseline_path"] == baseline


def test_verify_baseline_and_capture_baseline_mutually_exclusive(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    baseline = tmp_path / "b.arf"
    capture = tmp_path / "c.arf"
    baseline.write_text("<TestResult/>", encoding="utf-8")
    runner = CliRunner()

    with patch("ks_gen.cli.check_tools"):
        result = runner.invoke(
            app,
            [
                "verify",
                "--host",
                "h1",
                "--config",
                str(cfg),
                "--baseline",
                str(baseline),
                "--capture-baseline",
                str(capture),
            ],
        )
    assert result.exit_code == 1, result.output  # USAGE
    assert "mutually exclusive" in result.output


def test_verify_baseline_missing_file_exit_usage(tmp_path: Path) -> None:
    """When the library raises ConfigError(USAGE), the CLI exits 1 with the message."""
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    missing = tmp_path / "does-not-exist.arf"

    from ks_gen.loader import ConfigError, ExitCode

    with (
        patch(
            "ks_gen.cli.run_verify",
            side_effect=ConfigError(
                f"--baseline path does not exist: {missing}",
                ExitCode.USAGE,
            ),
        ),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(
            app,
            ["verify", "--host", "h1", "--config", str(cfg), "--baseline", str(missing)],
        )
    assert result.exit_code == 1, result.output  # USAGE


def test_verify_ask_sudo_pass_threads_password_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _write_cfg(tmp_path)
    monkeypatch.setenv("KSGEN_SUDO_PASSWORD", "secret")
    captured: dict[str, object] = {}

    def fake_run_verify(**kw: object) -> VerifyReport:
        captured["sudo_auth"] = kw["sudo_auth"]
        return _clean_report()

    runner = CliRunner()
    with (
        patch("ks_gen.cli.run_verify", side_effect=fake_run_verify),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(
            app, ["verify", "--host", "h1", "--config", str(cfg), "--ask-sudo-pass"]
        )
    assert result.exit_code == 0, result.output
    assert isinstance(captured["sudo_auth"], SudoAuth)
    assert captured["sudo_auth"].is_password is True


def test_verify_default_is_passwordless(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _write_cfg(tmp_path)
    monkeypatch.delenv("KSGEN_SUDO_PASSWORD", raising=False)
    captured: dict[str, object] = {}

    def fake_run_verify(**kw: object) -> VerifyReport:
        captured["sudo_auth"] = kw["sudo_auth"]
        return _clean_report()

    runner = CliRunner()
    with (
        patch("ks_gen.cli.run_verify", side_effect=fake_run_verify),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(app, ["verify", "--host", "h1", "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert captured["sudo_auth"].is_password is False


def _write_hosts(tmp_path: Path, cfg: Path) -> Path:
    hosts = tmp_path / "hosts.txt"
    hosts.write_text(f"h1 {cfg.name}\nh2 {cfg.name}\n", encoding="utf-8")
    return hosts


def test_verify_requires_host_or_hosts(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["verify", "--config", str(cfg)])
    assert result.exit_code == int(ExitCode.USAGE)
    assert "exactly one of --host / --hosts" in result.output


def test_verify_rejects_both_host_and_hosts(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    hosts = _write_hosts(tmp_path, cfg)
    runner = CliRunner()
    result = runner.invoke(app, ["verify", "--host", "h1", "--hosts", str(hosts)])
    assert result.exit_code == int(ExitCode.USAGE)


def test_verify_rejects_config_with_hosts(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    hosts = _write_hosts(tmp_path, cfg)
    runner = CliRunner()
    result = runner.invoke(app, ["verify", "--hosts", str(hosts), "--config", str(cfg)])
    assert result.exit_code == int(ExitCode.USAGE)
    assert "--config is not valid with --hosts" in result.output


def test_verify_rejects_apply_with_hosts(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    hosts = _write_hosts(tmp_path, cfg)
    runner = CliRunner()
    result = runner.invoke(app, ["verify", "--hosts", str(hosts), "--apply"])
    assert result.exit_code == int(ExitCode.USAGE)
    assert "not valid with --hosts" in result.output


def test_verify_hosts_happy_path_exit_code(tmp_path: Path) -> None:
    from ks_gen.verify.fleet import FleetReport, HostOutcome

    cfg = _write_cfg(tmp_path)
    hosts = _write_hosts(tmp_path, cfg)

    def fake_fleet(specs, *, jobs, verify_one):
        outcomes = tuple(HostOutcome(spec=s, report=_clean_report(), error=None) for s in specs)
        return FleetReport(outcomes=outcomes)

    runner = CliRunner()
    with (
        patch("ks_gen.cli.run_fleet", side_effect=fake_fleet),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(app, ["verify", "--hosts", str(hosts)])
    assert result.exit_code == 0, result.output
    assert "fleet: 2 hosts" in result.output


def test_verify_hosts_fails_exit_6(tmp_path: Path) -> None:
    from ks_gen.verify.fleet import FleetReport, HostOutcome

    cfg = _write_cfg(tmp_path)
    hosts = _write_hosts(tmp_path, cfg)

    def fake_fleet(specs, *, jobs, verify_one):
        outcomes = tuple(HostOutcome(spec=s, report=_failing_report(), error=None) for s in specs)
        return FleetReport(outcomes=outcomes)

    runner = CliRunner()
    with (
        patch("ks_gen.cli.run_fleet", side_effect=fake_fleet),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(app, ["verify", "--hosts", str(hosts)])
    assert result.exit_code == int(ExitCode.VERIFY_FAIL)


def test_verify_fleet_format_html_stdout(tmp_path: Path) -> None:
    from ks_gen.verify.fleet import FleetReport, HostOutcome

    cfg = _write_cfg(tmp_path)
    hosts = _write_hosts(tmp_path, cfg)

    def fake_fleet(specs, *, jobs, verify_one):
        outcomes = tuple(HostOutcome(spec=s, report=_clean_report(), error=None) for s in specs)
        return FleetReport(outcomes=outcomes)

    runner = CliRunner()
    with (
        patch("ks_gen.cli.run_fleet", side_effect=fake_fleet),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(app, ["verify", "--hosts", str(hosts), "--format", "html"])
    assert result.exit_code == 0
    assert "<!DOCTYPE html>" in result.output
    assert "fleet —" in result.output


def test_verify_fleet_html_out_writes_file_stdout_stays_table(tmp_path: Path) -> None:
    from ks_gen.verify.fleet import FleetReport, HostOutcome

    cfg = _write_cfg(tmp_path)
    hosts = _write_hosts(tmp_path, cfg)
    out = tmp_path / "fleet-report.html"

    def fake_fleet(specs, *, jobs, verify_one):
        outcomes = tuple(HostOutcome(spec=s, report=_clean_report(), error=None) for s in specs)
        return FleetReport(outcomes=outcomes)

    runner = CliRunner()
    with (
        patch("ks_gen.cli.run_fleet", side_effect=fake_fleet),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(app, ["verify", "--hosts", str(hosts), "--html-out", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    assert out.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
    assert "<!DOCTYPE html>" not in result.output


def test_verify_local_happy_path(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    captured: dict[str, object] = {}

    def fake_run_verify(**kwargs: object) -> VerifyReport:
        captured.update(kwargs)
        return _clean_report()

    with (
        patch("ks_gen.cli.LocalTransport.preflight"),
        patch("ks_gen.cli.run_verify", side_effect=fake_run_verify),
    ):
        result = runner.invoke(app, ["verify", "--local", "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert captured["local"] is True


def test_verify_local_requires_config() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["verify", "--local"])
    assert result.exit_code == int(ExitCode.USAGE)
    assert "--config is required with --local" in result.output


def test_verify_local_rejects_ssh_flags(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["verify", "--local", "--config", str(cfg), "--user", "bob"])
    assert result.exit_code == int(ExitCode.USAGE)
    assert "--user" in result.output
    assert "not valid with --local" in result.output


def test_verify_local_rejects_apply(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["verify", "--local", "--config", str(cfg), "--apply"])
    assert result.exit_code == int(ExitCode.USAGE)
    assert "--apply" in result.output


def test_verify_local_rejects_allow_regression(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["verify", "--local", "--config", str(cfg), "--allow-regression"])
    assert result.exit_code == int(ExitCode.USAGE)
    assert "--allow-regression" in result.output
    assert "not valid with --local" in result.output


def test_verify_rejects_local_with_host(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["verify", "--local", "--host", "1.2.3.4", "--config", str(cfg)])
    assert result.exit_code == int(ExitCode.USAGE)
    assert "exactly one of --host / --hosts / --local" in result.output


def test_verify_local_non_root_preflight_errors(tmp_path: Path) -> None:
    from ks_gen.loader import ConfigError

    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with patch(
        "ks_gen.cli.LocalTransport.preflight",
        side_effect=ConfigError(
            "verify --local must run as root (EUID 0); re-run under sudo",
            ExitCode.USAGE,
        ),
    ):
        result = runner.invoke(app, ["verify", "--local", "--config", str(cfg)])
    assert result.exit_code == int(ExitCode.USAGE)
    assert "must run as root" in result.output


def test_verify_format_html_to_stdout(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with (
        patch("ks_gen.cli.run_verify", return_value=_clean_report()),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(
            app, ["verify", "--host", "h1", "--config", str(cfg), "--format", "html"]
        )
    assert result.exit_code == 0
    assert "<!DOCTYPE html>" in result.output
    assert "CLEAN" in result.output


def test_verify_html_out_writes_file_and_stdout_stays_table(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    out = tmp_path / "report.html"
    with (
        patch("ks_gen.cli.run_verify", return_value=_clean_report()),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(
            app, ["verify", "--host", "h1", "--config", str(cfg), "--html-out", str(out)]
        )
    assert result.exit_code == 0
    assert out.exists()
    assert out.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
    assert "<!DOCTYPE html>" not in result.output


def test_verify_html_out_written_even_on_failing_run(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    out = tmp_path / "report.html"
    with (
        patch("ks_gen.cli.run_verify", return_value=_failing_report()),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(
            app, ["verify", "--host", "h1", "--config", str(cfg), "--html-out", str(out)]
        )
    # non-clean report => exit 6, but the HTML artifact must still be written
    assert result.exit_code == int(ExitCode.VERIFY_FAIL)
    assert out.exists()
    assert out.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_verify_html_out_bad_parent_dir_is_usage_error(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    out = tmp_path / "nope" / "report.html"
    result = runner.invoke(
        app, ["verify", "--host", "h1", "--config", str(cfg), "--html-out", str(out)]
    )
    assert result.exit_code == int(ExitCode.USAGE)
    assert "html-out" in result.output


def test_verify_html_out_parent_is_file_is_usage_error(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    parent = tmp_path / "afile"
    parent.write_text("x", encoding="utf-8")
    out = parent / "out.html"  # parent is a regular file, not a dir
    runner = CliRunner()
    result = runner.invoke(
        app, ["verify", "--host", "h1", "--config", str(cfg), "--html-out", str(out)]
    )
    assert result.exit_code == int(ExitCode.USAGE)
    assert "html-out" in result.output
    assert "Traceback" not in result.output


def test_verify_local_allows_format_html(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with (
        patch("ks_gen.cli.run_verify", return_value=_clean_report()),
        patch("ks_gen.cli.LocalTransport.preflight"),
    ):
        result = runner.invoke(app, ["verify", "--local", "--config", str(cfg), "--format", "html"])
    assert result.exit_code == 0
    assert "<!DOCTYPE html>" in result.output
