from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

from ks_gen.verify.errors import ArfParseError

VALID_RESULTS: frozenset[str] = frozenset(
    {
        "pass",
        "fail",
        "notapplicable",
        "notchecked",
        "notselected",
        "error",
        "unknown",
        "fixed",
        "informational",
    }
)


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    result: str


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_arf(text: str) -> dict[str, RuleResult]:
    """Parse an XCCDF ARF (or bare XCCDF results XML) into {rule_id: RuleResult}.

    Tolerant of namespace variation: matches elements by local-name. Result states
    outside the XCCDF vocabulary are normalized to 'unknown' rather than rejected.
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ArfParseError(f"ARF is not well-formed XML: {e}") from e

    results: dict[str, RuleResult] = {}
    found_test_result = _localname(root.tag) == "TestResult"

    for elem in root.iter():
        local = _localname(elem.tag)
        if local == "TestResult":
            found_test_result = True
        if local != "rule-result":
            continue
        rule_id = elem.get("idref")
        if not rule_id:
            continue
        for child in elem:
            if _localname(child.tag) != "result":
                continue
            state = (child.text or "").strip()
            if state not in VALID_RESULTS:
                state = "unknown"
            results[rule_id] = RuleResult(rule_id=rule_id, result=state)
            break

    if not found_test_result:
        raise ArfParseError("XML has no TestResult element — not an XCCDF/ARF document")

    return results
