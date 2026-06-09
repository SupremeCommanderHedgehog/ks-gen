from __future__ import annotations

from ks_gen.verify.baseline import BaselineReport, ReadBaseline


def test_baseline_report_shape() -> None:
    report = BaselineReport(
        path="./baseline.arf.xml",
        captured_utc="2026-06-05T09:30:00Z",
        orphans=("rule_x", "rule_y"),
    )
    assert report.path == "./baseline.arf.xml"
    assert report.captured_utc == "2026-06-05T09:30:00Z"
    assert report.orphans == ("rule_x", "rule_y")


def test_read_baseline_shape() -> None:
    from ks_gen.verify.arf import RuleResult

    rb = ReadBaseline(
        results={"rule_a": RuleResult(rule_id="rule_a", result="pass")},
        captured_utc=None,
        path=__import__("pathlib").Path("./b.arf.xml"),
    )
    assert "rule_a" in rb.results
    assert rb.captured_utc is None
