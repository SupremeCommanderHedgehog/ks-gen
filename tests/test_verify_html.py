from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

from ks_gen.loader import ExitCode
from ks_gen.rules._types import TailoringOp
from ks_gen.verify.baseline import BaselineReport
from ks_gen.verify.fleet import FleetReport, HostError, HostOutcome, HostSpec
from ks_gen.verify.html import render_fleet_html, render_html
from ks_gen.verify.reconcile import VerifyReport, VerifyRow
from ks_gen.verify.suggest import build_suggestions
from ks_gen.verify.tailoring_drift import OpChange, TailoringDriftReport


def assert_well_formed(doc: str) -> None:
    """Cheap structural gate: parses without error, self-contained, no script.

    Note: the stdlib HTMLParser is lenient (does not raise on unclosed or
    mismatched tags), so this checks encoding/self-containment, not tree
    structure.
    """
    assert doc.startswith("<!DOCTYPE html>")
    assert "<html" in doc and "</html>" in doc
    assert "<body" in doc and "</body>" in doc
    # self-contained: no external assets, no scripting
    assert "http://" not in doc and "https://" not in doc
    assert "<script" not in doc.lower()
    HTMLParser().feed(doc)  # raises on malformed constructs


def _report(rows: tuple[VerifyRow, ...], **kw: object) -> VerifyReport:
    return VerifyReport(
        host=str(kw.get("host", "host1")),
        user="admin",
        timestamp_utc="2026-07-03T12:00:00Z",
        rows=rows,
        install_baseline_available=bool(kw.get("install_baseline_available", True)),
        tailoring_drift=kw.get("tailoring_drift"),  # type: ignore[arg-type]
        baseline=kw.get("baseline"),  # type: ignore[arg-type]
    )


CLEAN_ROW = VerifyRow(
    rule_id="xccdf_org.ssgproject.content_rule_ok",
    current="pass",
    install="pass",
    expected=False,
    category="clean",
)
REGRESSION_ROW = VerifyRow(
    rule_id="xccdf_org.ssgproject.content_rule_bad",
    current="fail",
    install="pass",
    expected=False,
    category="regression",
)


def test_clean_report_shows_clean_badge_and_no_actionable_rows() -> None:
    doc = render_html(_report((CLEAN_ROW,)))
    assert_well_formed(doc)
    assert "CLEAN" in doc
    assert "FAILURES" not in doc
    assert "(no actionable rows)" in doc
    # clean rows are summarized, not tabled
    assert "content_rule_ok" not in doc


def test_regression_report_shows_failures_badge_and_row() -> None:
    doc = render_html(_report((CLEAN_ROW, REGRESSION_ROW)))
    assert_well_formed(doc)
    assert "FAILURES" in doc
    assert "content_rule_bad" in doc
    assert 'class="regression"' in doc
    # summary counts appear
    assert "regression=1" in doc


def test_dynamic_values_are_escaped() -> None:
    evil = VerifyRow(
        rule_id="<script>alert(1)</script>",
        current="fail",
        install=None,
        expected=False,
        category="new_fail",
    )
    doc = render_html(_report((evil,)))
    assert "<script>alert(1)</script>" not in doc
    assert "&lt;script&gt;" in doc
    assert_well_formed(doc)


def test_host_name_is_escaped() -> None:
    doc = render_html(_report((CLEAN_ROW,), host="<b>host</b>"))
    assert "<b>host</b>" not in doc
    assert "&lt;b&gt;host&lt;/b&gt;" in doc
    assert_well_formed(doc)


def test_install_baseline_note_only_when_unavailable() -> None:
    with_note = render_html(_report((CLEAN_ROW,), install_baseline_available=False))
    assert "install-time ARF not present" in with_note
    without = render_html(_report((CLEAN_ROW,), install_baseline_available=True))
    assert "install-time ARF not present" not in without


def test_baseline_section_and_orphan_note() -> None:
    bl = BaselineReport(
        path="/tmp/base.arf", captured_utc="2026-07-01T00:00:00Z", orphans=("xccdf_rule_gone",)
    )
    doc = render_html(_report((CLEAN_ROW,), baseline=bl))
    assert "/tmp/base.arf" in doc
    assert "captured 2026-07-01T00:00:00Z" in doc
    assert "1 rule in baseline not present" in doc
    assert_well_formed(doc)


def test_drift_section_renders_ops_when_present() -> None:
    drift = TailoringDriftReport(
        profile_id_expected="stig",
        profile_id_deployed="stig",
        added=[TailoringOp(rule_id="rule_added", action="select")],
        removed=[TailoringOp(rule_id="rule_removed", action="disable")],
        changed=[
            OpChange(rule_id="rule_val", action="set_value", expected_value="7", deployed_value="9")
        ],
    )
    doc = render_html(_report((CLEAN_ROW,), tailoring_drift=drift))
    assert "Tailoring drift" in doc
    assert "rule_added" in doc and "rule_removed" in doc
    assert "rule_val" in doc and "9" in doc and "7" in doc
    assert_well_formed(doc)


def test_no_drift_section_when_drift_report_empty() -> None:
    empty = TailoringDriftReport(
        profile_id_expected="stig",
        profile_id_deployed="stig",
        added=[],
        removed=[],
        changed=[],
    )
    doc = render_html(_report((CLEAN_ROW,), tailoring_drift=empty))
    assert "Tailoring drift" not in doc


def test_suggestions_block_present_only_when_passed() -> None:
    rep = _report((REGRESSION_ROW,))
    sug = build_suggestions(rep)
    with_sug = render_html(rep, suggestions=sug)
    assert "Suggested exceptions" in with_sug
    assert "<pre>" in with_sug
    without = render_html(rep, suggestions=None)
    assert "Suggested exceptions" not in without
    assert_well_formed(with_sug)


def test_drift_section_renders_profile_change() -> None:
    drift = TailoringDriftReport(
        profile_id_expected="stig_new",
        profile_id_deployed="stig_old",
        added=[],
        removed=[],
        changed=[],
    )
    doc = render_html(_report((CLEAN_ROW,), tailoring_drift=drift))
    assert "Tailoring drift" in doc
    assert "profile changed" in doc
    assert "stig_old" in doc and "stig_new" in doc
    assert_well_formed(doc)


def test_baseline_timestamp_unknown_when_captured_none() -> None:
    bl = BaselineReport(path="/tmp/b.arf", captured_utc=None, orphans=())
    doc = render_html(_report((CLEAN_ROW,), baseline=bl))
    assert "timestamp unknown" in doc
    assert "/tmp/b.arf" in doc
    assert_well_formed(doc)


def test_baseline_orphans_plural() -> None:
    bl = BaselineReport(
        path="/tmp/b.arf", captured_utc="2026-07-01T00:00:00Z", orphans=("r1", "r2")
    )
    doc = render_html(_report((CLEAN_ROW,), baseline=bl))
    assert "2 rules in baseline not present" in doc
    assert_well_formed(doc)


def test_empty_suggestions_list_renders_no_section() -> None:
    # suggestions=[] ("asked, none found") renders no block, same as None.
    rep = _report((CLEAN_ROW,))
    doc = render_html(rep, suggestions=[])
    assert "Suggested exceptions" not in doc
    assert_well_formed(doc)


def _spec(host: str) -> HostSpec:
    return HostSpec(host=host, user=None, config_path=Path("h.yaml"), lineno=1)


def test_fleet_html_mixed_outcomes() -> None:
    clean = HostOutcome(spec=_spec("good"), report=_report((CLEAN_ROW,)), error=None)
    failed = HostOutcome(spec=_spec("bad"), report=_report((REGRESSION_ROW,)), error=None)
    dead = HostOutcome(
        spec=_spec("dead"),
        report=None,
        error=HostError(
            label="SshError", message="connection refused", exit_code=ExitCode.TRANSPORT_FAIL
        ),
    )
    fleet = FleetReport(outcomes=(clean, failed, dead))
    doc = render_fleet_html(fleet, jobs=5)
    assert_well_formed(doc)
    # aggregate verdict + exit code (verify_fail dominates -> FAILURES, exit 6)
    assert "FAILURES" in doc
    assert "exit 6" in doc
    # every host appears
    assert "good" in doc and "bad" in doc and "dead" in doc
    # error host shows its label + message
    assert "SshError" in doc
    assert "connection refused" in doc
    # per-host detail: the failing host's rule is tabled
    assert "content_rule_bad" in doc


def test_fleet_html_escapes_error_message() -> None:
    dead = HostOutcome(
        spec=_spec("h"),
        report=None,
        error=HostError(label="Err", message="<b>boom</b>", exit_code=ExitCode.TRANSPORT_FAIL),
    )
    doc = render_fleet_html(FleetReport(outcomes=(dead,)), jobs=1)
    assert "<b>boom</b>" not in doc
    assert "&lt;b&gt;boom&lt;/b&gt;" in doc


def test_fleet_html_drift_host_row() -> None:
    drift = TailoringDriftReport(
        profile_id_expected="stig",
        profile_id_deployed="stig",
        added=[TailoringOp(rule_id="rule_x", action="select")],
        removed=[],
        changed=[],
    )
    # clean compliance + non-empty drift => status "drift"
    o = HostOutcome(
        spec=_spec("drifter"),
        report=_report((CLEAN_ROW,), tailoring_drift=drift),
        error=None,
    )
    doc = render_fleet_html(FleetReport(outcomes=(o,)), jobs=1)
    assert 'class="drift"' in doc
    assert "drifter" in doc
    assert_well_formed(doc)


def test_fleet_html_all_clean_badge() -> None:
    o = HostOutcome(spec=_spec("good"), report=_report((CLEAN_ROW,)), error=None)
    doc = render_fleet_html(FleetReport(outcomes=(o,)), jobs=1)
    assert "CLEAN" in doc
    assert "FAILURES" not in doc
    assert "exit 0" in doc
    assert_well_formed(doc)


def test_single_host_drift_only_badge_is_drift_not_clean() -> None:
    drift = TailoringDriftReport(
        profile_id_expected="stig",
        profile_id_deployed="stig",
        added=[TailoringOp(rule_id="rule_x", action="select")],
        removed=[],
        changed=[],
    )
    # compliance-clean but drifted => verdict must not be a green CLEAN badge
    doc = render_html(_report((CLEAN_ROW,), tailoring_drift=drift))
    assert 'class="badge drift"' in doc
    assert ">DRIFT<" in doc
    assert 'class="badge clean"' not in doc
    assert_well_formed(doc)


def test_fleet_drift_only_aggregate_badge_is_drift() -> None:
    drift = TailoringDriftReport(
        profile_id_expected="stig",
        profile_id_deployed="stig",
        added=[TailoringOp(rule_id="rule_x", action="select")],
        removed=[],
        changed=[],
    )
    o = HostOutcome(
        spec=_spec("d"), report=_report((CLEAN_ROW,), tailoring_drift=drift), error=None
    )
    doc = render_fleet_html(FleetReport(outcomes=(o,)), jobs=1)
    assert 'class="badge drift"' in doc
    assert 'class="badge clean"' not in doc
    assert_well_formed(doc)
