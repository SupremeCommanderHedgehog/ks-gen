from __future__ import annotations

from ks_gen.rules._types import TailoringOp
from ks_gen.verify.tailoring_drift import (
    OpChange,
    ParsedTailoring,
    TailoringDriftReport,
)


def test_parsed_tailoring_shape() -> None:
    op = TailoringOp(rule_id="r1", action="disable")
    pt = ParsedTailoring(profile_id="p", ops=[op])
    assert pt.profile_id == "p"
    assert pt.ops == [op]


def test_op_change_shape() -> None:
    change = OpChange(
        rule_id="r1",
        action="set_value",
        expected_value="5",
        deployed_value="24",
    )
    assert change.rule_id == "r1"
    assert change.expected_value == "5"
    assert change.deployed_value == "24"


def test_tailoring_drift_report_shape() -> None:
    report = TailoringDriftReport(
        profile_id_expected="p1",
        profile_id_deployed="p2",
        added=[],
        removed=[],
        changed=[],
    )
    assert report.profile_id_expected == "p1"
    assert report.profile_id_deployed == "p2"
    assert report.added == []
    assert report.removed == []
    assert report.changed == []
