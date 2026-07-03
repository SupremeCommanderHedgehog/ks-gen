from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from ks_gen.loader import ConfigError, ExitCode
from ks_gen.verify.auth import PASSWORDLESS
from ks_gen.verify.errors import SshConnectError
from ks_gen.verify.fleet import (
    FleetOptions,
    FleetReport,
    HostError,
    HostOutcome,
    HostSpec,
    make_verify_one,
    parse_hosts_file,
    run_fleet,
)
from ks_gen.verify.reconcile import VerifyReport, VerifyRow
from ks_gen.verify.tailoring_drift import TailoringDriftReport


def _spec(host: str = "h1", user: str | None = None) -> HostSpec:
    return HostSpec(host=host, user=user, config_path=Path("cfg.yaml"), lineno=1)


def _report(host: str, rows: tuple[VerifyRow, ...], drift: bool = False) -> VerifyReport:
    td = None
    if drift:
        td = TailoringDriftReport(
            profile_id_expected="p",
            profile_id_deployed="q",
            added=(),
            removed=(),
            changed=(),
        )
    return VerifyReport(
        host=host,
        user="u",
        timestamp_utc="2026-07-02T00:00:00Z",
        rows=rows,
        install_baseline_available=True,
        tailoring_drift=td,
    )


def test_outcome_status_clean() -> None:
    rep = _report("h1", (VerifyRow("r", "pass", "pass", False, "clean"),))
    out = HostOutcome(spec=_spec(), report=rep, error=None)
    assert out.status == "clean"


def test_outcome_status_verify_fail() -> None:
    rep = _report("h1", (VerifyRow("r", "fail", "pass", False, "regression"),))
    out = HostOutcome(spec=_spec(), report=rep, error=None)
    assert out.status == "verify_fail"


def test_outcome_status_drift() -> None:
    rep = _report("h1", (VerifyRow("r", "pass", "pass", False, "clean"),), drift=True)
    out = HostOutcome(spec=_spec(), report=rep, error=None)
    assert out.status == "drift"


def test_outcome_status_transport() -> None:
    err = HostError(label="sshconnect", message="refused", exit_code=ExitCode.TRANSPORT_FAIL)
    out = HostOutcome(spec=_spec(), report=None, error=err)
    assert out.status == "transport"


def test_outcome_status_verify_fail_beats_drift() -> None:
    # A report that is both non-clean AND has drift must report verify_fail:
    # `not is_clean` short-circuits before the drift check.
    rep = _report("h1", (VerifyRow("r", "fail", "pass", False, "regression"),), drift=True)
    out = HostOutcome(spec=_spec(), report=rep, error=None)
    assert out.status == "verify_fail"


def _outcome(status: str) -> HostOutcome:
    if status == "transport":
        return HostOutcome(
            spec=_spec(),
            report=None,
            error=HostError(label="sshconnect", message="x", exit_code=ExitCode.TRANSPORT_FAIL),
        )
    if status == "verify_fail":
        rep = _report("h", (VerifyRow("r", "fail", "pass", False, "regression"),))
    elif status == "drift":
        rep = _report("h", (VerifyRow("r", "pass", "pass", False, "clean"),), drift=True)
    else:  # clean
        rep = _report("h", (VerifyRow("r", "pass", "pass", False, "clean"),))
    return HostOutcome(spec=_spec(), report=rep, error=None)


def _fleet(*statuses: str) -> FleetReport:
    return FleetReport(outcomes=tuple(_outcome(s) for s in statuses))


def test_aggregate_all_clean_is_0() -> None:
    assert _fleet("clean", "clean").aggregate_exit_code == 0


def test_aggregate_verify_fail_wins_over_transport_and_drift() -> None:
    assert _fleet("clean", "drift", "transport", "verify_fail").aggregate_exit_code == 6


def test_aggregate_transport_wins_over_drift() -> None:
    assert _fleet("clean", "drift", "transport").aggregate_exit_code == 7


def test_aggregate_drift_only_is_8() -> None:
    assert _fleet("clean", "drift").aggregate_exit_code == 8


def _write_cfg(dirpath: Path, name: str) -> Path:
    p = dirpath / name
    p.write_text(
        "system: {hostname: h}\n"
        "user:\n"
        "  admin:\n"
        "    name: ops\n"
        "    authorized_keys: ['ssh-ed25519 A a@b']\n"
        "    sudo: nopasswd_yes\n",
        encoding="utf-8",
    )
    return p


def test_parse_basic_two_hosts(tmp_path: Path) -> None:
    _write_cfg(tmp_path, "web.yaml")
    _write_cfg(tmp_path, "db.yaml")
    hosts = tmp_path / "hosts.txt"
    hosts.write_text(
        "# a comment\n\nweb01.example.com    web.yaml\nadmin@db01           db.yaml\n",
        encoding="utf-8",
    )
    specs = parse_hosts_file(hosts)
    assert [s.host for s in specs] == ["web01.example.com", "db01"]
    assert specs[0].user is None
    assert specs[1].user == "admin"
    assert specs[1].config_path == (tmp_path / "db.yaml").resolve()


def test_parse_malformed_line_reports_lineno(tmp_path: Path) -> None:
    _write_cfg(tmp_path, "web.yaml")
    hosts = tmp_path / "hosts.txt"
    hosts.write_text("web01 web.yaml extra_field\n", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        parse_hosts_file(hosts)
    assert "line 1" in str(exc.value)


def test_parse_missing_config_reports_lineno(tmp_path: Path) -> None:
    hosts = tmp_path / "hosts.txt"
    hosts.write_text("web01 does-not-exist.yaml\n", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        parse_hosts_file(hosts)
    assert "line 1" in str(exc.value)


def test_parse_collects_multiple_bad_lines(tmp_path: Path) -> None:
    hosts = tmp_path / "hosts.txt"
    hosts.write_text("onlyonefield\nweb missing.yaml\n", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        parse_hosts_file(hosts)
    msg = str(exc.value)
    assert "line 1" in msg and "line 2" in msg


def test_parse_config_paths_relative_to_hosts_file(tmp_path: Path) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    _write_cfg(sub, "web.yaml")
    hosts = sub / "hosts.txt"
    hosts.write_text("web01 web.yaml\n", encoding="utf-8")
    specs = parse_hosts_file(hosts)
    assert specs[0].config_path == (sub / "web.yaml").resolve()


def test_parse_empty_file_is_error(tmp_path: Path) -> None:
    hosts = tmp_path / "hosts.txt"
    hosts.write_text("", encoding="utf-8")
    with pytest.raises(ConfigError):
        parse_hosts_file(hosts)


def test_parse_all_comments_is_error(tmp_path: Path) -> None:
    hosts = tmp_path / "hosts.txt"
    hosts.write_text("# just a comment\n\n# another\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        parse_hosts_file(hosts)


def test_outcome_status_error_with_verify_fail_exit_is_verify_fail() -> None:
    # A caught VerifyError carrying VERIFY_FAIL (e.g. TailoringParseError) must
    # report verify_fail, not transport — matching single-host exit semantics.
    err = HostError(label="tailoringparse", message="bad xml", exit_code=ExitCode.VERIFY_FAIL)
    out = HostOutcome(spec=_spec(), report=None, error=err)
    assert out.status == "verify_fail"


def test_run_fleet_preserves_input_order_despite_completion_order() -> None:
    specs = [_spec(f"h{i}", None) for i in range(5)]

    def slow_reverse(spec: HostSpec) -> HostOutcome:
        # earlier specs sleep longer, so completion order is reversed
        idx = int(spec.host[1:])
        time.sleep((5 - idx) * 0.01)
        rep = _report(spec.host, (VerifyRow("r", "pass", "pass", False, "clean"),))
        return HostOutcome(spec=spec, report=rep, error=None)

    fleet = run_fleet(specs, jobs=5, verify_one=slow_reverse)
    assert [o.spec.host for o in fleet.outcomes] == [f"h{i}" for i in range(5)]


def test_run_fleet_isolates_a_raising_host() -> None:
    specs = [_spec("good", None), _spec("bad", None)]

    def one(spec: HostSpec) -> HostOutcome:
        if spec.host == "bad":
            raise RuntimeError("boom")  # must not abort the fleet
        rep = _report(spec.host, (VerifyRow("r", "pass", "pass", False, "clean"),))
        return HostOutcome(spec=spec, report=rep, error=None)

    fleet = run_fleet(specs, jobs=2, verify_one=one)
    by_host = {o.spec.host: o for o in fleet.outcomes}
    assert by_host["good"].status == "clean"
    assert by_host["bad"].status == "transport"
    assert by_host["bad"].error is not None
    assert "boom" in by_host["bad"].error.message


def test_run_fleet_respects_jobs_limit() -> None:
    specs = [_spec(f"h{i}", None) for i in range(4)]
    active = 0
    peak = 0
    lock = threading.Lock()

    def one(spec: HostSpec) -> HostOutcome:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        rep = _report(spec.host, (VerifyRow("r", "pass", "pass", False, "clean"),))
        return HostOutcome(spec=spec, report=rep, error=None)

    run_fleet(specs, jobs=2, verify_one=one)
    assert peak <= 2


def _opts(**kw) -> FleetOptions:
    base = dict(
        no_drift=False,
        check_tailoring=False,
        ssh_extra_opts=[],
        timeout=600,
        sudo_auth=PASSWORDLESS,
        fleet_user=None,
    )
    base.update(kw)
    return FleetOptions(**base)


def test_verify_one_success_wraps_report(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path, "web.yaml")
    spec = HostSpec(host="web01", user="admin", config_path=cfg, lineno=1)
    rep = _report("web01", (VerifyRow("r", "pass", "pass", False, "clean"),))
    verify_one = make_verify_one(_opts())
    with patch("ks_gen.verify.fleet.run_verify", return_value=rep) as rv:
        out = verify_one(spec)
    assert out.status == "clean"
    assert out.report is rep
    # inline user@ wins over cfg.user.admin.name
    assert rv.call_args.kwargs["user"] == "admin"


def test_verify_one_uses_fleet_user_when_no_inline(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path, "web.yaml")
    spec = HostSpec(host="web01", user=None, config_path=cfg, lineno=1)
    rep = _report("web01", (VerifyRow("r", "pass", "pass", False, "clean"),))
    verify_one = make_verify_one(_opts(fleet_user="deploy"))
    with patch("ks_gen.verify.fleet.run_verify", return_value=rep) as rv:
        verify_one(spec)
    assert rv.call_args.kwargs["user"] == "deploy"


def test_verify_one_falls_back_to_cfg_admin(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path, "web.yaml")  # admin.name == "ops"
    spec = HostSpec(host="web01", user=None, config_path=cfg, lineno=1)
    rep = _report("web01", (VerifyRow("r", "pass", "pass", False, "clean"),))
    verify_one = make_verify_one(_opts())
    with patch("ks_gen.verify.fleet.run_verify", return_value=rep) as rv:
        verify_one(spec)
    assert rv.call_args.kwargs["user"] == "ops"


def test_verify_one_catches_verify_error_as_host_error(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path, "web.yaml")
    spec = HostSpec(host="web01", user=None, config_path=cfg, lineno=1)
    verify_one = make_verify_one(_opts())
    with patch("ks_gen.verify.fleet.run_verify", side_effect=SshConnectError("refused")):
        out = verify_one(spec)
    assert out.status == "transport"
    assert out.error is not None
    assert out.error.exit_code == int(ExitCode.TRANSPORT_FAIL)
    assert "refused" in out.error.message


def test_verify_one_records_resolved_user_on_success(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path, "web.yaml")
    spec = HostSpec(host="web01", user=None, config_path=cfg, lineno=1)
    rep = _report("web01", (VerifyRow("r", "pass", "pass", False, "clean"),))
    verify_one = make_verify_one(_opts(fleet_user="deploy"))
    with patch("ks_gen.verify.fleet.run_verify", return_value=rep):
        out = verify_one(spec)
    assert out.user == "deploy"


def test_verify_one_records_resolved_user_on_failure(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path, "web.yaml")  # cfg admin == "ops"
    spec = HostSpec(host="web01", user=None, config_path=cfg, lineno=1)
    verify_one = make_verify_one(_opts())  # no inline, no fleet_user -> cfg admin
    with patch("ks_gen.verify.fleet.run_verify", side_effect=SshConnectError("refused")):
        out = verify_one(spec)
    assert out.status == "transport"
    assert out.user == "ops"
