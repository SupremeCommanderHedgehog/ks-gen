from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from ks_gen.verify.arf import RuleResult
from ks_gen.verify.reconcile import (
    VerifyReport,
    VerifyRow,
    build_report,
    categorize,
)


@pytest.mark.parametrize(
    "current,install,expected,want",
    [
        ("pass", "pass", False, "clean"),
        ("pass", "fail", False, "clean"),
        ("pass", None, False, "clean"),
        ("fixed", "fail", False, "clean"),
        ("notapplicable", "fail", False, "clean"),
        ("notselected", "fail", False, "clean"),
        ("informational", "fail", False, "clean"),
        ("fail", "pass", True, "expected_fail"),
        ("fail", "pass", False, "regression"),
        ("fail", "fixed", False, "regression"),
        ("fail", "notapplicable", False, "regression"),
        ("fail", "fail", False, "new_fail"),
        ("fail", None, False, "new_fail"),
        ("fail", "error", False, "new_fail"),
        ("error", "pass", False, "incomplete"),
        ("notchecked", "pass", False, "incomplete"),
        ("unknown", "pass", False, "incomplete"),
    ],
)
def test_categorize_matrix(current: str, install: str | None, expected: bool, want: str) -> None:
    assert categorize(current, install, expected) == want


def test_build_report_groups_rules_into_categories() -> None:
    current = {
        "rule_a": RuleResult("rule_a", "pass"),
        "rule_b": RuleResult("rule_b", "fail"),
        "rule_c": RuleResult("rule_c", "fail"),
        "rule_d": RuleResult("rule_d", "fail"),
        "rule_e": RuleResult("rule_e", "error"),
    }
    install = {
        "rule_a": RuleResult("rule_a", "pass"),
        "rule_b": RuleResult("rule_b", "fail"),
        "rule_c": RuleResult("rule_c", "pass"),
        "rule_d": RuleResult("rule_d", "fail"),
        "rule_e": RuleResult("rule_e", "pass"),
    }
    expected_failures = {"rule_d"}
    report = build_report(
        current=current,
        install=install,
        expected_failures=expected_failures,
        host="h1",
        user="ops",
        timestamp_utc="2026-06-07T00:00:00Z",
    )
    by_id = {r.rule_id: r for r in report.rows}
    assert by_id["rule_a"].category == "clean"
    assert by_id["rule_b"].category == "new_fail"
    assert by_id["rule_c"].category == "regression"
    assert by_id["rule_d"].category == "expected_fail"
    assert by_id["rule_e"].category == "incomplete"
    assert report.install_baseline_available is True
    assert report.is_clean is False


def test_build_report_clean_when_no_actionable_failures() -> None:
    current = {"rule_a": RuleResult("rule_a", "pass")}
    report = build_report(
        current=current,
        install={"rule_a": RuleResult("rule_a", "pass")},
        expected_failures=set(),
        host="h1",
        user="ops",
        timestamp_utc="ts",
    )
    assert report.is_clean is True


def test_build_report_install_none_drops_install_column() -> None:
    current = {"rule_a": RuleResult("rule_a", "fail")}
    report = build_report(
        current=current,
        install=None,
        expected_failures=set(),
        host="h1",
        user="ops",
        timestamp_utc="ts",
    )
    assert report.install_baseline_available is False
    assert report.rows[0].install is None
    assert report.rows[0].category == "new_fail"


def test_build_report_rules_only_in_install_are_ignored() -> None:
    current = {"rule_a": RuleResult("rule_a", "pass")}
    install = {
        "rule_a": RuleResult("rule_a", "pass"),
        "rule_old": RuleResult("rule_old", "pass"),
    }
    report = build_report(
        current=current,
        install=install,
        expected_failures=set(),
        host="h1",
        user="ops",
        timestamp_utc="ts",
    )
    assert [r.rule_id for r in report.rows] == ["rule_a"]


def test_build_report_rows_are_sorted_by_rule_id() -> None:
    current = {
        "rule_z": RuleResult("rule_z", "pass"),
        "rule_a": RuleResult("rule_a", "pass"),
        "rule_m": RuleResult("rule_m", "pass"),
    }
    report = build_report(
        current=current,
        install=None,
        expected_failures=set(),
        host="h1",
        user="ops",
        timestamp_utc="ts",
    )
    assert [r.rule_id for r in report.rows] == ["rule_a", "rule_m", "rule_z"]


def test_verify_row_is_frozen() -> None:
    row = VerifyRow(
        rule_id="r",
        current="pass",
        install=None,
        expected=False,
        category="clean",
    )
    with pytest.raises(FrozenInstanceError):
        row.category = "new_fail"  # type: ignore[misc]


def test_verify_report_is_immutable_tuple_of_rows() -> None:
    report = VerifyReport(
        host="h",
        user="u",
        timestamp_utc="t",
        rows=(),
        install_baseline_available=False,
    )
    assert isinstance(report.rows, tuple)
    with pytest.raises(FrozenInstanceError):
        report.rows = (VerifyRow("r", "pass", None, False, "clean"),)  # type: ignore[misc]


def test_verify_report_tailoring_drift_defaults_to_none() -> None:
    from ks_gen.verify.reconcile import VerifyReport

    report = VerifyReport(
        host="h",
        user="u",
        timestamp_utc="2026-06-09T00:00:00Z",
        rows=(),
        install_baseline_available=True,
    )
    assert report.tailoring_drift is None
    assert report.has_tailoring_drift is False


def test_verify_report_has_tailoring_drift_false_when_empty_drift_attached() -> None:
    from ks_gen.verify.reconcile import VerifyReport
    from ks_gen.verify.tailoring_drift import TailoringDriftReport

    drift = TailoringDriftReport(
        profile_id_expected="p",
        profile_id_deployed="p",
        added=[],
        removed=[],
        changed=[],
    )
    report = VerifyReport(
        host="h",
        user="u",
        timestamp_utc="2026-06-09T00:00:00Z",
        rows=(),
        install_baseline_available=True,
        tailoring_drift=drift,
    )
    assert report.tailoring_drift is drift
    assert report.has_tailoring_drift is False


def test_verify_report_has_tailoring_drift_true_when_changes_present() -> None:
    from ks_gen.rules._types import TailoringOp
    from ks_gen.verify.reconcile import VerifyReport
    from ks_gen.verify.tailoring_drift import TailoringDriftReport

    drift = TailoringDriftReport(
        profile_id_expected="p",
        profile_id_deployed="p",
        added=[TailoringOp("r1", "disable")],
        removed=[],
        changed=[],
    )
    report = VerifyReport(
        host="h",
        user="u",
        timestamp_utc="2026-06-09T00:00:00Z",
        rows=(),
        install_baseline_available=True,
        tailoring_drift=drift,
    )
    assert report.has_tailoring_drift is True


def test_verify_report_has_tailoring_drift_true_on_profile_id_mismatch_alone() -> None:
    from ks_gen.verify.reconcile import VerifyReport
    from ks_gen.verify.tailoring_drift import TailoringDriftReport

    drift = TailoringDriftReport(
        profile_id_expected="p1",
        profile_id_deployed="p2",
        added=[],
        removed=[],
        changed=[],
    )
    report = VerifyReport(
        host="h",
        user="u",
        timestamp_utc="2026-06-09T00:00:00Z",
        rows=(),
        install_baseline_available=True,
        tailoring_drift=drift,
    )
    assert report.has_tailoring_drift is True


def test_verify_report_baseline_defaults_to_none() -> None:
    from ks_gen.verify.reconcile import VerifyReport

    report = VerifyReport(
        host="h",
        user="u",
        timestamp_utc="2026-06-09T00:00:00Z",
        rows=(),
        install_baseline_available=True,
    )
    assert report.baseline is None
