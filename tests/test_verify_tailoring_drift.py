from __future__ import annotations

import pytest

from ks_gen.rules._types import TailoringOp
from ks_gen.tailoring import build_tailoring_xml
from ks_gen.verify.errors import TailoringParseError
from ks_gen.verify.tailoring_drift import (
    OpChange,
    ParsedTailoring,
    TailoringDriftReport,
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
