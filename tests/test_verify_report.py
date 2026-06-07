from __future__ import annotations

import json

from syrupy.assertion import SnapshotAssertion

from ks_gen.verify.reconcile import VerifyReport, VerifyRow
from ks_gen.verify.report import render_json, render_table


def _make_report(rows: tuple[VerifyRow, ...], baseline: bool = True) -> VerifyReport:
    return VerifyReport(
        host="h1.example.com",
        user="opsadmin",
        timestamp_utc="2026-06-07T12:00:00Z",
        rows=rows,
        install_baseline_available=baseline,
    )


def test_render_table_clean_report(snapshot: SnapshotAssertion) -> None:
    report = _make_report(
        (VerifyRow("xccdf_org.ssgproject.content_rule_a", "pass", "pass", False, "clean"),)
    )
    assert render_table(report) == snapshot


def test_render_table_one_of_each_category(snapshot: SnapshotAssertion) -> None:
    report = _make_report(
        (
            VerifyRow("xccdf_org.ssgproject.content_rule_a", "pass", "pass", False, "clean"),
            VerifyRow("xccdf_org.ssgproject.content_rule_b", "fail", "fail", False, "new_fail"),
            VerifyRow("xccdf_org.ssgproject.content_rule_c", "fail", "pass", False, "regression"),
            VerifyRow("xccdf_org.ssgproject.content_rule_d", "fail", "pass", True, "expected_fail"),
            VerifyRow("xccdf_org.ssgproject.content_rule_e", "error", "pass", False, "incomplete"),
        )
    )
    assert render_table(report) == snapshot


def test_render_table_no_baseline_shows_banner(snapshot: SnapshotAssertion) -> None:
    report = _make_report(
        (VerifyRow("xccdf_org.ssgproject.content_rule_a", "fail", None, False, "new_fail"),),
        baseline=False,
    )
    assert render_table(report) == snapshot


def test_render_json_shape() -> None:
    report = _make_report(
        (
            VerifyRow("rule_a", "pass", "pass", False, "clean"),
            VerifyRow("rule_b", "fail", None, False, "new_fail"),
        )
    )
    out = render_json(report)
    payload = json.loads(out)
    assert payload["host"] == "h1.example.com"
    assert payload["user"] == "opsadmin"
    assert payload["timestamp_utc"] == "2026-06-07T12:00:00Z"
    assert payload["install_baseline_available"] is True
    assert payload["is_clean"] is False
    assert payload["summary"] == {
        "clean": 1,
        "expected_fail": 0,
        "new_fail": 1,
        "regression": 0,
        "incomplete": 0,
    }
    assert payload["rows"] == [
        {
            "rule_id": "rule_a",
            "current": "pass",
            "install": "pass",
            "expected": False,
            "category": "clean",
        },
        {
            "rule_id": "rule_b",
            "current": "fail",
            "install": None,
            "expected": False,
            "category": "new_fail",
        },
    ]
