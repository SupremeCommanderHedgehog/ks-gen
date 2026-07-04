from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from ks_gen.cli import app
from ks_gen.loader import ExitCode
from ks_gen.verify.fleet import FleetReport, HostError, HostOutcome, HostSpec
from ks_gen.verify.history import RunRecord, write_record
from ks_gen.verify.reconcile import VerifyReport, VerifyRow

# Mirrors the VALID_YAML/_write_cfg helper in tests/test_cli/test_verify.py.
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


def _report(host: str) -> VerifyReport:
    return VerifyReport(
        host=host,
        user="opsadmin",
        timestamp_utc="2026-07-04T02:00:00Z",
        rows=(
            VerifyRow("rule_a", "pass", "pass", False, "clean"),
            VerifyRow("rule_b", "fail", None, False, "new_fail"),
        ),
        install_baseline_available=True,
    )


def test_record_writes_single_host_file(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    hist = tmp_path / "hist"
    runner = CliRunner()
    with (
        patch("ks_gen.cli.run_verify", return_value=_report("h1")),
        patch("ks_gen.cli.check_tools", return_value=None),
    ):
        result = runner.invoke(
            app,
            ["verify", "--host", "h1", "--config", str(cfg), "--record", str(hist)],
        )
    # new_fail -> exit 6, but the record must still have been written
    assert result.exit_code == 6
    line = (hist / "h1.jsonl").read_text(encoding="utf-8").strip()
    payload = json.loads(line)
    assert payload["host"] == "h1"
    assert payload["rows"] == [["rule_b", "new_fail"]]


def test_record_writes_local_mode(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    hist = tmp_path / "hist"
    runner = CliRunner()
    with (
        patch("ks_gen.cli.run_verify", return_value=_report("localbox")),
        patch("ks_gen.cli.LocalTransport") as lt,
    ):
        lt.return_value.preflight.return_value = None
        result = runner.invoke(
            app,
            ["verify", "--local", "--config", str(cfg), "--record", str(hist)],
        )
    assert result.exit_code == 6
    assert (hist / "localbox.jsonl").is_file()


def test_record_writes_per_host_files_in_fleet(tmp_path: Path) -> None:
    hist = tmp_path / "hist"
    hosts_file = tmp_path / "fleet.txt"
    cfg = tmp_path / "h.yaml"
    cfg.write_text("# placeholder\n", encoding="utf-8")
    hosts_file.write_text(f"h1  {cfg}\nh2  {cfg}\n", encoding="utf-8")

    fleet = FleetReport(
        outcomes=(
            HostOutcome(
                spec=HostSpec("h1", None, cfg, 1), report=_report("h1"), error=None, user="opsadmin"
            ),
            HostOutcome(
                spec=HostSpec("h2", None, cfg, 2), report=_report("h2"), error=None, user="opsadmin"
            ),
        )
    )
    runner = CliRunner()
    with (
        patch(
            "ks_gen.cli.parse_hosts_file",
            return_value=[HostSpec("h1", None, cfg, 1), HostSpec("h2", None, cfg, 2)],
        ),
        patch("ks_gen.cli.check_tools", return_value=None),
        patch("ks_gen.cli.resolve_sudo_auth"),
        patch("ks_gen.cli.run_fleet", return_value=fleet),
    ):
        result = runner.invoke(app, ["verify", "--hosts", str(hosts_file), "--record", str(hist)])
    assert result.exit_code == 6  # both hosts have a new_fail
    assert (hist / "h1.jsonl").is_file()
    assert (hist / "h2.jsonl").is_file()


def test_record_writes_clean_run_single_host(tmp_path: Path) -> None:
    # A fully-clean report still records, and exits 0 (guards the write-before-raise placement).
    cfg = _write_cfg(tmp_path)
    hist = tmp_path / "hist"
    clean = VerifyReport(
        host="h1",
        user="opsadmin",
        timestamp_utc="2026-07-04T02:00:00Z",
        rows=(VerifyRow("rule_a", "pass", "pass", False, "clean"),),
        install_baseline_available=True,
    )
    runner = CliRunner()
    with (
        patch("ks_gen.cli.run_verify", return_value=clean),
        patch("ks_gen.cli.check_tools", return_value=None),
    ):
        result = runner.invoke(
            app, ["verify", "--host", "h1", "--config", str(cfg), "--record", str(hist)]
        )
    assert result.exit_code == 0
    assert (hist / "h1.jsonl").is_file()


def test_record_skips_errored_host_in_fleet(tmp_path: Path) -> None:
    hist = tmp_path / "hist"
    cfg = tmp_path / "h.yaml"
    cfg.write_text("# placeholder\n", encoding="utf-8")
    hosts_file = tmp_path / "fleet.txt"
    hosts_file.write_text(f"h1  {cfg}\nh2  {cfg}\n", encoding="utf-8")

    fleet = FleetReport(
        outcomes=(
            HostOutcome(
                spec=HostSpec("h1", None, cfg, 1),
                report=_report("h1"),
                error=None,
                user="opsadmin",
            ),
            HostOutcome(
                spec=HostSpec("h2", None, cfg, 2),
                report=None,
                error=HostError(
                    label="transport",
                    message="ssh failed",
                    exit_code=ExitCode.TRANSPORT_FAIL,
                ),
                user="opsadmin",
            ),
        )
    )
    runner = CliRunner()
    with (
        patch(
            "ks_gen.cli.parse_hosts_file",
            return_value=[HostSpec("h1", None, cfg, 1), HostSpec("h2", None, cfg, 2)],
        ),
        patch("ks_gen.cli.check_tools", return_value=None),
        patch("ks_gen.cli.resolve_sudo_auth"),
        patch("ks_gen.cli.run_fleet", return_value=fleet),
    ):
        runner.invoke(app, ["verify", "--hosts", str(hosts_file), "--record", str(hist)])
    # successful host recorded; errored host (report=None) has no file
    assert (hist / "h1.jsonl").is_file()
    assert not (hist / "h2.jsonl").exists()


def _seed(hist: Path, host: str) -> None:
    write_record(
        hist,
        RunRecord(
            host=host,
            user="opsadmin",
            timestamp_utc="2026-07-04T02:00:00Z",
            summary={
                "clean": 1,
                "expected_fail": 0,
                "new_fail": 1,
                "regression": 0,
                "incomplete": 0,
            },
            is_clean=False,
            drift=False,
            rows=(("rule_b", "new_fail"),),
        ),
    )


def test_verify_history_table(tmp_path: Path) -> None:
    hist = tmp_path / "hist"
    _seed(hist, "h1")
    runner = CliRunner()
    result = runner.invoke(app, ["verify-history", str(hist)])
    assert result.exit_code == 0
    assert "history host=h1" in result.stdout
    assert "TIMELINE" in result.stdout


def test_verify_history_json(tmp_path: Path) -> None:
    hist = tmp_path / "hist"
    _seed(hist, "h1")
    runner = CliRunner()
    result = runner.invoke(app, ["verify-history", str(hist), "--format", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert "h1" in parsed


def test_verify_history_host_filter(tmp_path: Path) -> None:
    hist = tmp_path / "hist"
    _seed(hist, "h1")
    _seed(hist, "h2")
    runner = CliRunner()
    result = runner.invoke(app, ["verify-history", str(hist), "--host", "h1"])
    assert result.exit_code == 0
    assert "history host=h1" in result.stdout
    assert "history host=h2" not in result.stdout


def test_verify_history_unknown_host_is_usage(tmp_path: Path) -> None:
    hist = tmp_path / "hist"
    _seed(hist, "h1")
    runner = CliRunner()
    result = runner.invoke(app, ["verify-history", str(hist), "--host", "nope"])
    assert result.exit_code == int(ExitCode.USAGE)


def test_verify_history_empty_dir_is_usage(tmp_path: Path) -> None:
    hist = tmp_path / "empty"
    hist.mkdir()
    runner = CliRunner()
    result = runner.invoke(app, ["verify-history", str(hist)])
    assert result.exit_code == int(ExitCode.USAGE)


def test_verify_history_bad_format_is_usage(tmp_path: Path) -> None:
    hist = tmp_path / "hist"
    _seed(hist, "h1")
    runner = CliRunner()
    result = runner.invoke(app, ["verify-history", str(hist), "--format", "html"])
    assert result.exit_code == int(ExitCode.USAGE)


def test_verify_history_malformed_record_is_usage(tmp_path: Path) -> None:
    hist = tmp_path / "hist"
    hist.mkdir()
    (hist / "h1.jsonl").write_text("not-json\n", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(app, ["verify-history", str(hist)])
    assert result.exit_code == int(ExitCode.USAGE)


def test_verify_history_table_multi_host_sorted(tmp_path: Path) -> None:
    hist = tmp_path / "hist"
    _seed(hist, "h2")
    _seed(hist, "h1")
    runner = CliRunner()
    result = runner.invoke(app, ["verify-history", str(hist)])
    assert result.exit_code == 0
    out = result.stdout
    assert "history host=h1" in out
    assert "history host=h2" in out
    assert out.index("history host=h1") < out.index("history host=h2")
