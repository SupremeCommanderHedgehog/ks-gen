from __future__ import annotations

from ks_gen.verify.reconcile import VerifyReport, VerifyRow
from ks_gen.verify.suggest import build_suggestions


def _report(*rows: VerifyRow, host: str = "h1") -> VerifyReport:
    return VerifyReport(
        host=host,
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=tuple(rows),
        install_baseline_available=True,
    )


def test_build_suggestions_filters_to_new_fail_and_regression():
    report = _report(
        VerifyRow("rule_a", "pass", "pass", False, "clean"),
        VerifyRow("rule_b", "fail", "fail", True, "expected_fail"),
        VerifyRow("rule_c", "error", None, False, "incomplete"),
        VerifyRow("rule_d", "fail", "fail", False, "new_fail"),
        VerifyRow("rule_e", "fail", "pass", False, "regression"),
    )
    out = build_suggestions(report)
    # only rule_d (new_fail) and rule_e (regression) become suggestions
    assert [s.decl.stig_rules_disabled[0] for s in out] == ["rule_d", "rule_e"]
    assert [s.category for s in out] == ["new_fail", "regression"]


def test_build_suggestions_id_format():
    report = _report(
        VerifyRow("rule_d", "fail", "fail", False, "new_fail"),
        VerifyRow("rule_e", "fail", "pass", False, "regression"),
    )
    out = build_suggestions(report)
    assert out[0].decl.id == "auto-new_fail-rule_d"
    assert out[1].decl.id == "auto-regression-rule_e"


def test_build_suggestions_reason_carries_run_context():
    report = _report(
        VerifyRow("rule_d", "fail", "pass", False, "regression"),
        host="web01.example.com",
    )
    suggestion = build_suggestions(report)[0]
    reason = suggestion.decl.reason
    assert reason.startswith("TODO:")
    assert "web01.example.com" in reason
    assert "2026-06-09" in reason
    assert "current=fail" in reason
    assert "install=pass" in reason
    assert "category=regression" in reason


def test_build_suggestions_stig_rules_disabled_is_single_id():
    report = _report(VerifyRow("rule_d", "fail", "fail", False, "new_fail"))
    suggestion = build_suggestions(report)[0]
    assert suggestion.decl.stig_rules_disabled == ["rule_d"]


def test_build_suggestions_empty_report_returns_empty_list():
    report = _report(VerifyRow("rule_a", "pass", "pass", False, "clean"))
    assert build_suggestions(report) == []


def test_build_suggestions_order_matches_report_row_order():
    # build_report sorts by rule_id; build_suggestions preserves that order
    report = _report(
        VerifyRow("rule_a", "fail", "fail", False, "new_fail"),
        VerifyRow("rule_b", "fail", "pass", False, "regression"),
        VerifyRow("rule_c", "fail", "fail", False, "new_fail"),
    )
    out = build_suggestions(report)
    assert [s.decl.stig_rules_disabled[0] for s in out] == ["rule_a", "rule_b", "rule_c"]
