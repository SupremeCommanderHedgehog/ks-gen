from __future__ import annotations

from pathlib import Path

import pytest

from ks_gen.verify.arf import RuleResult, parse_arf
from ks_gen.verify.errors import ArfParseError

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_arf_returns_all_results_by_rule_id() -> None:
    results = parse_arf(_read("arf-clean.xml"))
    assert set(results) == {
        "xccdf_org.ssgproject.content_rule_rule_a",
        "xccdf_org.ssgproject.content_rule_rule_b",
        "xccdf_org.ssgproject.content_rule_rule_c",
    }
    assert all(isinstance(r, RuleResult) for r in results.values())
    assert all(r.result == "pass" for r in results.values())


def test_parse_arf_preserves_each_result_state() -> None:
    results = parse_arf(_read("arf-mixed.xml"))
    assert results["xccdf_org.ssgproject.content_rule_rule_a"].result == "pass"
    assert results["xccdf_org.ssgproject.content_rule_rule_d"].result == "fail"
    assert results["xccdf_org.ssgproject.content_rule_rule_f"].result == "error"


def test_parse_arf_raises_on_malformed_xml() -> None:
    with pytest.raises(ArfParseError, match="well-formed"):
        parse_arf("<not really xml")


def test_parse_arf_raises_on_xml_without_test_result() -> None:
    with pytest.raises(ArfParseError, match="TestResult"):
        parse_arf(_read("arf-incomplete.xml"))


def test_parse_arf_normalizes_unknown_result_state() -> None:
    weird = """\
<?xml version="1.0"?>
<TestResult xmlns="http://checklists.nist.gov/xccdf/1.2">
  <rule-result idref="xccdf_org.ssgproject.content_rule_rule_x">
    <result>weirdstate</result>
  </rule-result>
</TestResult>
"""
    results = parse_arf(weird)
    assert results["xccdf_org.ssgproject.content_rule_rule_x"].result == "unknown"


def test_parse_arf_skips_rule_results_without_idref() -> None:
    no_idref = """\
<?xml version="1.0"?>
<TestResult xmlns="http://checklists.nist.gov/xccdf/1.2">
  <rule-result>
    <result>pass</result>
  </rule-result>
  <rule-result idref="xccdf_org.ssgproject.content_rule_keep">
    <result>pass</result>
  </rule-result>
</TestResult>
"""
    results = parse_arf(no_idref)
    assert list(results) == ["xccdf_org.ssgproject.content_rule_keep"]
