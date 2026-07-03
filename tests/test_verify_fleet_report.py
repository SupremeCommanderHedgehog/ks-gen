from __future__ import annotations

import json
from pathlib import Path

from syrupy.assertion import SnapshotAssertion

from ks_gen.loader import ExitCode
from ks_gen.verify.fleet import FleetReport, HostError, HostOutcome, HostSpec
from ks_gen.verify.reconcile import VerifyReport, VerifyRow
from ks_gen.verify.report import render_fleet_json, render_fleet_table
from ks_gen.verify.tailoring_drift import TailoringDriftReport


def _spec(host: str, user: str | None = None) -> HostSpec:
    return HostSpec(host=host, user=user, config_path=Path("c.yaml"), lineno=1)


def _rep(host: str, rows, drift=False) -> VerifyReport:
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
        user="ops",
        timestamp_utc="2026-07-02T00:00:00Z",
        rows=rows,
        install_baseline_available=True,
        tailoring_drift=td,
    )


def _four_host_fleet() -> FleetReport:
    clean_row = VerifyRow("r", "pass", "pass", False, "clean")
    return FleetReport(
        outcomes=(
            HostOutcome(_spec("web01"), _rep("web01", (clean_row,)), None),
            HostOutcome(
                _spec("web02"),
                _rep(
                    "web02",
                    (
                        VerifyRow("r1", "fail", "pass", False, "regression"),
                        VerifyRow("r2", "fail", None, False, "new_fail"),
                    ),
                ),
                None,
            ),
            HostOutcome(_spec("db01"), _rep("db01", (clean_row,), drift=True), None),
            HostOutcome(
                _spec("bastion01", "root"),
                None,
                HostError(
                    label="sshconnect",
                    message="connection refused",
                    exit_code=ExitCode.TRANSPORT_FAIL,
                ),
            ),
        )
    )


def test_render_fleet_table_snapshot(snapshot: SnapshotAssertion) -> None:
    assert render_fleet_table(_four_host_fleet(), jobs=5) == snapshot


def test_render_fleet_json_snapshot(snapshot: SnapshotAssertion) -> None:
    assert render_fleet_json(_four_host_fleet()) == snapshot


def test_render_fleet_json_aggregate_matches_report() -> None:
    fleet = _four_host_fleet()
    payload = json.loads(render_fleet_json(fleet))
    assert payload["aggregate_exit_code"] == fleet.aggregate_exit_code == 6
    assert payload["summary"] == {"clean": 1, "verify_fail": 1, "drift": 1, "transport": 1}
    assert [h["host"] for h in payload["hosts"]] == ["web01", "web02", "db01", "bastion01"]
