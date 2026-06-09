from __future__ import annotations

import pytest

from ks_gen.rules._types import TailoringOp
from ks_gen.tailoring import build_tailoring_xml
from ks_gen.verify.errors import TailoringParseError
from ks_gen.verify.tailoring_drift import (
    OpChange,
    ParsedTailoring,
    TailoringDriftReport,
    compare_tailorings,
    parse_tailoring_xml,
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


def test_parse_round_trips_build_tailoring_xml() -> None:
    ops = [
        TailoringOp(rule_id="rule_a", action="disable"),
        TailoringOp(rule_id="rule_b", action="select"),
        TailoringOp(rule_id="rule_c", action="set_value", value="24"),
    ]
    xml = build_tailoring_xml(ops, profile_id="xccdf_org.ssgproject.content_profile_stig")
    parsed = parse_tailoring_xml(xml)

    assert parsed.profile_id == "xccdf_org.ssgproject.content_profile_stig"
    assert sorted(parsed.ops, key=lambda o: o.rule_id) == sorted(ops, key=lambda o: o.rule_id)


def test_parse_handles_empty_set_value() -> None:
    ops = [TailoringOp(rule_id="rule_a", action="set_value", value="")]
    xml = build_tailoring_xml(ops, profile_id="p")
    parsed = parse_tailoring_xml(xml)
    assert parsed.ops == [TailoringOp(rule_id="rule_a", action="set_value", value="")]


def test_parse_raises_on_garbage_xml() -> None:
    with pytest.raises(TailoringParseError, match="well-formed"):
        parse_tailoring_xml("<not-xml")


def test_parse_raises_on_xml_with_no_profile() -> None:
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<xccdf:Tailoring xmlns:xccdf="http://checklists.nist.gov/xccdf/1.2"/>'
    )
    with pytest.raises(TailoringParseError, match="Profile"):
        parse_tailoring_xml(xml)


def test_parse_ignores_unknown_op_elements() -> None:
    """Forward-compat: unknown child elements inside <Profile> are dropped, not raised."""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<xccdf:Tailoring xmlns:xccdf="http://checklists.nist.gov/xccdf/1.2">'
        '<xccdf:Profile id="x">'
        '<xccdf:select idref="r1" selected="true"/>'
        '<xccdf:future-element idref="r2"/>'
        "</xccdf:Profile>"
        "</xccdf:Tailoring>"
    )
    parsed = parse_tailoring_xml(xml)
    assert parsed.ops == [TailoringOp(rule_id="r1", action="select")]


def _parsed(profile: str, ops: list[TailoringOp]) -> ParsedTailoring:
    return ParsedTailoring(profile_id=profile, ops=ops)


def test_compare_clean_no_drift() -> None:
    ops = [TailoringOp("r1", "disable"), TailoringOp("r2", "select")]
    report = compare_tailorings(_parsed("p", ops), _parsed("p", ops))
    assert report.added == []
    assert report.removed == []
    assert report.changed == []
    assert report.profile_id_expected == report.profile_id_deployed == "p"


def test_compare_added_only() -> None:
    expected = _parsed("p", [TailoringOp("r1", "disable"), TailoringOp("r2", "disable")])
    deployed = _parsed("p", [TailoringOp("r1", "disable")])
    report = compare_tailorings(expected, deployed)
    assert report.added == [TailoringOp("r2", "disable")]
    assert report.removed == []
    assert report.changed == []


def test_compare_removed_only() -> None:
    expected = _parsed("p", [TailoringOp("r1", "disable")])
    deployed = _parsed("p", [TailoringOp("r1", "disable"), TailoringOp("r2", "disable")])
    report = compare_tailorings(expected, deployed)
    assert report.added == []
    assert report.removed == [TailoringOp("r2", "disable")]
    assert report.changed == []


def test_compare_changed_set_value() -> None:
    expected = _parsed("p", [TailoringOp("r1", "set_value", "24")])
    deployed = _parsed("p", [TailoringOp("r1", "set_value", "5")])
    report = compare_tailorings(expected, deployed)
    assert report.added == []
    assert report.removed == []
    assert report.changed == [
        OpChange(rule_id="r1", action="set_value", expected_value="24", deployed_value="5")
    ]


def test_compare_select_to_disable_is_two_changes_not_one() -> None:
    """Action is part of the op identity, so a flip surfaces as remove+add."""
    expected = _parsed("p", [TailoringOp("r1", "select")])
    deployed = _parsed("p", [TailoringOp("r1", "disable")])
    report = compare_tailorings(expected, deployed)
    assert report.added == [TailoringOp("r1", "select")]
    assert report.removed == [TailoringOp("r1", "disable")]
    assert report.changed == []


def test_compare_profile_id_mismatch_with_no_op_drift() -> None:
    ops = [TailoringOp("r1", "disable")]
    report = compare_tailorings(_parsed("p1", ops), _parsed("p2", ops))
    assert report.profile_id_expected == "p1"
    assert report.profile_id_deployed == "p2"
    assert report.added == []
    assert report.removed == []
    assert report.changed == []


def test_compare_all_four_categories_simultaneously() -> None:
    expected = _parsed(
        "p1",
        [
            TailoringOp("r_added", "disable"),
            TailoringOp("r_changed", "set_value", "24"),
            TailoringOp("r_same", "select"),
        ],
    )
    deployed = _parsed(
        "p2",
        [
            TailoringOp("r_removed", "disable"),
            TailoringOp("r_changed", "set_value", "5"),
            TailoringOp("r_same", "select"),
        ],
    )
    report = compare_tailorings(expected, deployed)
    assert report.added == [TailoringOp("r_added", "disable")]
    assert report.removed == [TailoringOp("r_removed", "disable")]
    assert report.changed == [
        OpChange(rule_id="r_changed", action="set_value", expected_value="24", deployed_value="5")
    ]
    assert report.profile_id_expected == "p1"
    assert report.profile_id_deployed == "p2"


def test_compare_results_sorted_by_rule_id() -> None:
    expected = _parsed(
        "p",
        [TailoringOp("rule_z", "disable"), TailoringOp("rule_a", "disable")],
    )
    deployed = _parsed("p", [])
    report = compare_tailorings(expected, deployed)
    assert [op.rule_id for op in report.added] == ["rule_a", "rule_z"]
