from __future__ import annotations

from pathlib import Path

import pytest

from ks_gen.loader import ConfigError, ExitCode
from ks_gen.verify.arf import RuleResult
from ks_gen.verify.baseline import BaselineReport, ReadBaseline, orphan_rule_ids, read_baseline
from ks_gen.verify.errors import ArfMissingError, ArfParseError


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


def _arf_with_start_time(start_time: str | None = "2026-06-05T09:30:00Z") -> str:
    """Build a minimal but valid ARF with optional start-time attribute."""
    attr = f' start-time="{start_time}"' if start_time is not None else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<arf:asset-report-collection xmlns:arf="http://scap.nist.gov/schema/asset-reporting-format/1.1">'
        '<arf:reports><arf:report id="r1"><arf:content>'
        f'<TestResult xmlns="http://checklists.nist.gov/xccdf/1.2" id="xccdf_org.test_TR"{attr}>'
        '<rule-result idref="xccdf_org.ssgproject.content_rule_rule_a">'
        "<result>pass</result>"
        "</rule-result>"
        "</TestResult>"
        "</arf:content></arf:report></arf:reports>"
        "</arf:asset-report-collection>"
    )


def test_read_baseline_happy_path(tmp_path: Path) -> None:
    arf = tmp_path / "b.arf.xml"
    arf.write_text(_arf_with_start_time(), encoding="utf-8")

    result = read_baseline(arf)

    assert result.path == arf
    assert result.captured_utc == "2026-06-05T09:30:00Z"
    assert "xccdf_org.ssgproject.content_rule_rule_a" in result.results
    assert result.results["xccdf_org.ssgproject.content_rule_rule_a"].result == "pass"


def test_read_baseline_no_start_time_returns_none(tmp_path: Path) -> None:
    arf = tmp_path / "b.arf.xml"
    arf.write_text(_arf_with_start_time(start_time=None), encoding="utf-8")

    result = read_baseline(arf)

    assert result.captured_utc is None


def test_read_baseline_missing_file_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as exc_info:
        read_baseline(tmp_path / "does-not-exist.arf.xml")
    assert exc_info.value.exit_code == ExitCode.USAGE


def test_read_baseline_empty_file_raises_arf_missing(tmp_path: Path) -> None:
    arf = tmp_path / "empty.arf.xml"
    arf.write_text("", encoding="utf-8")

    with pytest.raises(ArfMissingError, match="empty"):
        read_baseline(arf)


def test_read_baseline_garbage_raises_arf_parse_error(tmp_path: Path) -> None:
    arf = tmp_path / "garbage.arf.xml"
    arf.write_text("<not-xml", encoding="utf-8")

    with pytest.raises(ArfParseError, match="well-formed"):
        read_baseline(arf)


def test_read_baseline_no_test_result_raises_arf_parse_error(tmp_path: Path) -> None:
    arf = tmp_path / "no-tr.arf.xml"
    arf.write_text(
        '<?xml version="1.0"?><root xmlns="http://example.com"><other/></root>',
        encoding="utf-8",
    )

    with pytest.raises(ArfParseError, match="TestResult"):
        read_baseline(arf)


def test_read_baseline_directory_raises_config_error(tmp_path: Path) -> None:
    """A directory at the path is a USAGE error, not a parse error."""
    with pytest.raises(ConfigError) as exc_info:
        read_baseline(tmp_path)
    assert exc_info.value.exit_code == ExitCode.USAGE


def _rr(rule_id: str, result: str = "pass") -> RuleResult:
    return RuleResult(rule_id=rule_id, result=result)  # type: ignore[arg-type]


def test_orphan_rule_ids_baseline_subset_of_current_returns_empty() -> None:
    baseline = {"r1": _rr("r1"), "r2": _rr("r2")}
    current = {"r1": _rr("r1"), "r2": _rr("r2"), "r3": _rr("r3")}
    assert orphan_rule_ids(baseline, current) == ()


def test_orphan_rule_ids_baseline_has_extras_returns_those() -> None:
    baseline = {"r1": _rr("r1"), "r2": _rr("r2"), "r_stale": _rr("r_stale")}
    current = {"r1": _rr("r1"), "r2": _rr("r2")}
    assert orphan_rule_ids(baseline, current) == ("r_stale",)


def test_orphan_rule_ids_sorted_alphabetically() -> None:
    baseline = {"r_z": _rr("r_z"), "r_a": _rr("r_a"), "r_m": _rr("r_m")}
    current: dict[str, RuleResult] = {}
    assert orphan_rule_ids(baseline, current) == ("r_a", "r_m", "r_z")


def test_orphan_rule_ids_empty_inputs_returns_empty() -> None:
    assert orphan_rule_ids({}, {}) == ()


def test_orphan_rule_ids_empty_baseline_returns_empty() -> None:
    current = {"r1": _rr("r1")}
    assert orphan_rule_ids({}, current) == ()


def test_orphan_rule_ids_empty_current_returns_all_baseline() -> None:
    baseline = {"r1": _rr("r1"), "r2": _rr("r2")}
    assert orphan_rule_ids(baseline, {}) == ("r1", "r2")
