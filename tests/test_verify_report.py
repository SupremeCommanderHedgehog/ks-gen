from __future__ import annotations

import json

from syrupy.assertion import SnapshotAssertion

from ks_gen.verify.reconcile import VerifyReport, VerifyRow
from ks_gen.verify.report import render_json, render_table
from ks_gen.verify.suggest import build_suggestions


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


# --- suggestions= param tests ----------------------------------------------


def _report_with_failures() -> VerifyReport:
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


def test_render_table_without_suggestions_unchanged():
    report = _report_with_failures()
    out_with_none = render_table(report)
    out_without_param = render_table(report, suggestions=None)
    assert out_with_none == out_without_param
    assert "Suggested exception entries" not in out_with_none


def test_render_table_with_suggestions_appends_block():
    report = _report_with_failures()
    suggestions = build_suggestions(report)
    out = render_table(report, suggestions=suggestions)
    assert "Suggested exception entries" in out
    assert "auto-new_fail-rule_d" in out
    assert "auto-regression-rule_e" in out


def test_render_json_without_suggestions_omits_key():
    import json as _json

    report = _report_with_failures()
    payload = _json.loads(render_json(report))
    assert "suggested_exceptions" not in payload


def test_render_json_with_suggestions_includes_array():
    import json as _json

    report = _report_with_failures()
    suggestions = build_suggestions(report)
    payload = _json.loads(render_json(report, suggestions=suggestions))
    assert "suggested_exceptions" in payload
    assert len(payload["suggested_exceptions"]) == 2
    assert payload["suggested_exceptions"][0] == {
        "category": "new_fail",
        "decl": {
            "id": "auto-new_fail-rule_d",
            "reason": payload["suggested_exceptions"][0]["decl"]["reason"],
            "stig_rules_disabled": ["rule_d"],
        },
    }


def test_render_json_with_empty_suggestions_includes_empty_array():
    import json as _json

    report = _report_with_failures()
    payload = _json.loads(render_json(report, suggestions=[]))
    assert payload["suggested_exceptions"] == []


# --- tailoring_drift rendering tests ----------------------------------------


def test_render_table_appends_drift_section_when_present(snapshot) -> None:
    from ks_gen.rules._types import TailoringOp
    from ks_gen.verify.reconcile import VerifyReport, VerifyRow
    from ks_gen.verify.report import render_table
    from ks_gen.verify.tailoring_drift import OpChange, TailoringDriftReport

    drift = TailoringDriftReport(
        profile_id_expected="profile_a",
        profile_id_deployed="profile_b",
        added=[TailoringOp("rule_x", "disable")],
        removed=[TailoringOp("rule_y", "select")],
        changed=[
            OpChange(rule_id="rule_z", action="set_value", expected_value="24", deployed_value="5")
        ],
    )
    report = VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(VerifyRow("rule_b", "fail", "pass", False, "regression"),),
        install_baseline_available=True,
        tailoring_drift=drift,
    )
    out = render_table(report)
    assert out == snapshot


def test_render_table_no_drift_section_when_drift_none() -> None:
    from ks_gen.verify.reconcile import VerifyReport
    from ks_gen.verify.report import render_table

    report = VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(),
        install_baseline_available=True,
    )
    assert "Tailoring drift" not in render_table(report)


def test_render_json_includes_tailoring_drift_when_present(snapshot) -> None:
    from ks_gen.rules._types import TailoringOp
    from ks_gen.verify.reconcile import VerifyReport
    from ks_gen.verify.report import render_json
    from ks_gen.verify.tailoring_drift import OpChange, TailoringDriftReport

    drift = TailoringDriftReport(
        profile_id_expected="profile_a",
        profile_id_deployed="profile_b",
        added=[TailoringOp("rule_x", "disable")],
        removed=[TailoringOp("rule_y", "select")],
        changed=[
            OpChange(rule_id="rule_z", action="set_value", expected_value="24", deployed_value="5")
        ],
    )
    report = VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(),
        install_baseline_available=True,
        tailoring_drift=drift,
    )
    assert render_json(report) == snapshot


def test_render_json_no_tailoring_drift_key_when_field_is_none() -> None:
    import json as _json

    from ks_gen.verify.reconcile import VerifyReport
    from ks_gen.verify.report import render_json

    report = VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(),
        install_baseline_available=True,
    )
    payload = _json.loads(render_json(report))
    assert "tailoring_drift" not in payload


# --- baseline rendering tests ------------------------------------------------


def test_render_table_includes_baseline_header_when_present(snapshot) -> None:
    from ks_gen.verify.baseline import BaselineReport
    from ks_gen.verify.reconcile import VerifyReport, VerifyRow
    from ks_gen.verify.report import render_table

    baseline = BaselineReport(
        path="./baseline.arf.xml",
        captured_utc="2026-06-05T09:30:00Z",
        orphans=("xccdf_org.ssgproject.content_rule_rule_stale",),
    )
    report = VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(VerifyRow("rule_b", "fail", "pass", False, "regression"),),
        install_baseline_available=True,
        baseline=baseline,
    )
    out = render_table(report)
    assert out == snapshot


def test_render_table_baseline_header_without_timestamp(snapshot) -> None:
    """When captured_utc is None, the parenthetical reads (timestamp unknown)."""
    from ks_gen.verify.baseline import BaselineReport
    from ks_gen.verify.reconcile import VerifyReport
    from ks_gen.verify.report import render_table

    baseline = BaselineReport(
        path="./baseline.arf.xml",
        captured_utc=None,
        orphans=(),
    )
    report = VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(),
        install_baseline_available=True,
        baseline=baseline,
    )
    out = render_table(report)
    assert out == snapshot


def test_render_table_no_baseline_section_when_field_none() -> None:
    from ks_gen.verify.reconcile import VerifyReport
    from ks_gen.verify.report import render_table

    report = VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(),
        install_baseline_available=True,
    )
    out = render_table(report)
    assert "baseline:" not in out
    assert "may be stale" not in out


def test_render_json_includes_baseline_when_present(snapshot) -> None:
    from ks_gen.verify.baseline import BaselineReport
    from ks_gen.verify.reconcile import VerifyReport
    from ks_gen.verify.report import render_json

    baseline = BaselineReport(
        path="./baseline.arf.xml",
        captured_utc="2026-06-05T09:30:00Z",
        orphans=("xccdf_org.ssgproject.content_rule_rule_stale",),
    )
    report = VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(),
        install_baseline_available=True,
        baseline=baseline,
    )
    assert render_json(report) == snapshot


def test_render_json_no_baseline_key_when_field_is_none() -> None:
    import json as _json

    from ks_gen.verify.reconcile import VerifyReport
    from ks_gen.verify.report import render_json

    report = VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(),
        install_baseline_available=True,
    )
    payload = _json.loads(render_json(report))
    assert "baseline" not in payload
