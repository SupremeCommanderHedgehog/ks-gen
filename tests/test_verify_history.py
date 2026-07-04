from __future__ import annotations

import json as _json
from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion

from ks_gen.loader import ConfigError, ExitCode
from ks_gen.verify.history import (
    Delta,
    RunRecord,
    Streak,
    delta,
    read_history,
    read_host_history,
    record_from_report,
    render_history_json,
    render_history_table,
    streaks,
    write_record,
)
from ks_gen.verify.reconcile import VerifyReport, VerifyRow
from ks_gen.verify.tailoring_drift import TailoringDriftReport


def _report(rows: tuple[VerifyRow, ...], *, drift: bool = False) -> VerifyReport:
    td = None
    if drift:
        td = TailoringDriftReport(
            profile_id_expected="p",
            profile_id_deployed="q",
            added=[],
            removed=[],
            changed=[],
        )
    return VerifyReport(
        host="h1",
        user="opsadmin",
        timestamp_utc="2026-07-04T02:00:00Z",
        rows=rows,
        install_baseline_available=True,
        tailoring_drift=td,
    )


def test_record_from_report_omits_clean_rows() -> None:
    report = _report(
        (
            VerifyRow("rule_a", "pass", "pass", False, "clean"),
            VerifyRow("rule_b", "fail", "fail", False, "new_fail"),
            VerifyRow("rule_c", "fail", "pass", False, "regression"),
            VerifyRow("rule_d", "fail", "pass", True, "expected_fail"),
            VerifyRow("rule_e", "error", "pass", False, "incomplete"),
        )
    )
    rec = record_from_report(report)
    assert rec.host == "h1"
    assert rec.user == "opsadmin"
    assert rec.timestamp_utc == "2026-07-04T02:00:00Z"
    assert rec.rows == (
        ("rule_b", "new_fail"),
        ("rule_c", "regression"),
        ("rule_d", "expected_fail"),
        ("rule_e", "incomplete"),
    )
    assert rec.summary == {
        "clean": 1,
        "expected_fail": 1,
        "new_fail": 1,
        "regression": 1,
        "incomplete": 1,
    }
    assert rec.is_clean is False
    assert rec.drift is False
    assert rec.verdict == "FAIL"


def test_record_verdict_clean_report() -> None:
    rec = record_from_report(_report((VerifyRow("rule_a", "pass", "pass", False, "clean"),)))
    assert rec.is_clean is True
    assert rec.drift is False
    assert rec.rows == ()
    assert rec.verdict == "CLEAN"


def test_record_drift_only_is_fail_verdict() -> None:
    rec = record_from_report(
        _report((VerifyRow("rule_a", "pass", "pass", False, "clean"),), drift=True)
    )
    assert rec.is_clean is True
    assert rec.drift is True
    assert rec.verdict == "FAIL"


def test_record_failing_rule_ids() -> None:
    rec = record_from_report(
        _report(
            (
                VerifyRow("rule_b", "fail", None, False, "new_fail"),
                VerifyRow("rule_c", "fail", "pass", False, "regression"),
            )
        )
    )
    assert rec.failing_rule_ids == frozenset({"rule_b", "rule_c"})


# ---------------------------------------------------------------------------
# Task 2: JSONL write + read round-trip
# ---------------------------------------------------------------------------


def _rec(
    ts: str,
    rows: tuple[tuple[str, str], ...],
    *,
    host: str = "h1",
    is_clean: bool = False,
    drift: bool = False,
) -> RunRecord:
    return RunRecord(
        host=host,
        user="opsadmin",
        timestamp_utc=ts,
        summary={
            "clean": 0,
            "expected_fail": 0,
            "new_fail": len(rows),
            "regression": 0,
            "incomplete": 0,
        },
        is_clean=is_clean,
        drift=drift,
        rows=rows,
    )


def test_write_then_read_round_trip(tmp_path: Path) -> None:
    rec = _rec("2026-07-04T02:00:00Z", (("rule_b", "new_fail"),))
    write_record(tmp_path, rec)
    back = read_host_history(tmp_path / "h1.jsonl")
    assert back == [rec]


def test_write_creates_dir_and_appends(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "hist"
    write_record(target, _rec("2026-07-01T02:00:00Z", ()))
    write_record(target, _rec("2026-07-04T02:00:00Z", (("rule_b", "new_fail"),)))
    lines = (target / "h1.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_read_sorts_oldest_to_newest(tmp_path: Path) -> None:
    write_record(tmp_path, _rec("2026-07-04T02:00:00Z", ()))
    write_record(tmp_path, _rec("2026-07-01T02:00:00Z", ()))
    recs = read_host_history(tmp_path / "h1.jsonl")
    assert [r.timestamp_utc for r in recs] == [
        "2026-07-01T02:00:00Z",
        "2026-07-04T02:00:00Z",
    ]


def test_read_history_keys_by_host(tmp_path: Path) -> None:
    write_record(tmp_path, _rec("2026-07-04T02:00:00Z", (), host="h1"))
    write_record(tmp_path, _rec("2026-07-04T02:00:00Z", (), host="h2"))
    history = read_history(tmp_path)
    assert set(history) == {"h1", "h2"}


def test_read_history_missing_dir_is_usage(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as exc:
        read_history(tmp_path / "nope")
    assert exc.value.exit_code == ExitCode.USAGE


def test_read_history_empty_dir_is_usage(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as exc:
        read_history(tmp_path)
    assert exc.value.exit_code == ExitCode.USAGE


def test_read_malformed_json_is_usage(tmp_path: Path) -> None:
    (tmp_path / "h1.jsonl").write_text("not json\n", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        read_host_history(tmp_path / "h1.jsonl")
    assert exc.value.exit_code == ExitCode.USAGE


def test_read_missing_key_is_usage(tmp_path: Path) -> None:
    (tmp_path / "h1.jsonl").write_text('{"host": "h1"}\n', encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        read_host_history(tmp_path / "h1.jsonl")
    assert exc.value.exit_code == ExitCode.USAGE
    assert "h1.jsonl:1" in str(exc.value)


def test_write_record_dir_is_file_is_usage(tmp_path: Path) -> None:
    f = tmp_path / "notadir"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        write_record(f, _rec("2026-07-04T02:00:00Z", ()))
    assert exc.value.exit_code == ExitCode.USAGE


def test_read_host_history_all_blank_lines_returns_empty(tmp_path: Path) -> None:
    (tmp_path / "h1.jsonl").write_text("\n  \n\n", encoding="utf-8")
    assert read_host_history(tmp_path / "h1.jsonl") == []


# ---------------------------------------------------------------------------
# Task 3: Streaks + delta analysis
# ---------------------------------------------------------------------------


def test_streaks_counts_consecutive_from_newest() -> None:
    records = [
        _rec("2026-07-01T02:00:00Z", (("rule_b", "new_fail"),)),
        _rec("2026-07-02T02:00:00Z", (("rule_b", "new_fail"),)),
        _rec("2026-07-03T02:00:00Z", (("rule_b", "new_fail"), ("rule_c", "regression"))),
    ]
    result = streaks(records)
    assert result == [
        Streak(rule_id="rule_b", category="new_fail", length=3),
        Streak(rule_id="rule_c", category="regression", length=1),
    ]


def test_streaks_resets_on_clean_run() -> None:
    records = [
        _rec("2026-07-01T02:00:00Z", (("rule_b", "new_fail"),)),
        _rec("2026-07-02T02:00:00Z", ()),
        _rec("2026-07-03T02:00:00Z", (("rule_b", "new_fail"),)),
    ]
    assert streaks(records) == [Streak(rule_id="rule_b", category="new_fail", length=1)]


def test_streaks_only_reports_currently_failing() -> None:
    records = [
        _rec("2026-07-01T02:00:00Z", (("rule_b", "new_fail"),)),
        _rec("2026-07-02T02:00:00Z", ()),
    ]
    assert streaks(records) == []


def test_streaks_empty_history() -> None:
    assert streaks([]) == []


def test_delta_added_and_recovered() -> None:
    records = [
        _rec("2026-07-01T02:00:00Z", (("rule_b", "new_fail"), ("rule_z", "new_fail"))),
        _rec("2026-07-04T02:00:00Z", (("rule_b", "new_fail"), ("rule_y", "regression"))),
    ]
    d = delta(records)
    assert d.since_utc == "2026-07-01T02:00:00Z"
    assert d.added == (("rule_y", "regression"),)
    assert d.recovered == (("rule_z", "new_fail"),)


def test_delta_needs_two_runs() -> None:
    assert delta([]) == Delta(since_utc=None, added=(), recovered=())
    one = [_rec("2026-07-04T02:00:00Z", (("rule_b", "new_fail"),))]
    assert delta(one) == Delta(since_utc=None, added=(), recovered=())


def test_streaks_tie_break_by_rule_id() -> None:
    records = [
        _rec("2026-07-01T02:00:00Z", (("rule_z", "new_fail"), ("rule_a", "new_fail"))),
        _rec("2026-07-02T02:00:00Z", (("rule_z", "new_fail"), ("rule_a", "regression"))),
    ]
    result = streaks(records)
    assert result == [
        Streak(rule_id="rule_a", category="regression", length=2),
        Streak(rule_id="rule_z", category="new_fail", length=2),
    ]


def test_delta_no_change() -> None:
    records = [
        _rec("2026-07-01T02:00:00Z", (("rule_b", "new_fail"),)),
        _rec("2026-07-04T02:00:00Z", (("rule_b", "new_fail"),)),
    ]
    d = delta(records)
    assert d.since_utc == "2026-07-01T02:00:00Z"
    assert d.added == ()
    assert d.recovered == ()


# ---------------------------------------------------------------------------
# Task 4: Table + JSON renderers
# ---------------------------------------------------------------------------


def _history_fixture() -> list[RunRecord]:
    return [
        RunRecord(
            "h1",
            "opsadmin",
            "2026-06-28T02:00:00Z",
            {"clean": 412, "expected_fail": 3, "new_fail": 0, "regression": 0, "incomplete": 1},
            is_clean=True,
            drift=False,
            rows=(),
        ),
        RunRecord(
            "h1",
            "opsadmin",
            "2026-07-01T02:00:00Z",
            {"clean": 410, "expected_fail": 3, "new_fail": 2, "regression": 0, "incomplete": 1},
            is_clean=False,
            drift=False,
            rows=(("rule_x", "new_fail"), ("rule_z", "new_fail")),
        ),
        RunRecord(
            "h1",
            "opsadmin",
            "2026-07-04T02:00:00Z",
            {"clean": 411, "expected_fail": 3, "new_fail": 1, "regression": 1, "incomplete": 0},
            is_clean=False,
            drift=False,
            rows=(("rule_x", "new_fail"), ("rule_y", "regression")),
        ),
    ]


def test_render_history_table(snapshot: SnapshotAssertion) -> None:
    assert render_history_table("h1", _history_fixture()) == snapshot


def test_render_history_json_shape() -> None:
    out = render_history_json({"h1": _history_fixture()})
    parsed = _json.loads(out)
    assert set(parsed) == {"h1"}
    h1 = parsed["h1"]
    assert [r["timestamp_utc"] for r in h1["runs"]] == [
        "2026-06-28T02:00:00Z",
        "2026-07-01T02:00:00Z",
        "2026-07-04T02:00:00Z",
    ]
    streak_x = next(s for s in h1["streaks"] if s["rule_id"] == "rule_x")
    assert streak_x["length"] == 2
    assert h1["delta"]["since_utc"] == "2026-07-01T02:00:00Z"
    assert h1["delta"]["added"] == [["rule_y", "regression"]]
    assert h1["delta"]["recovered"] == [["rule_z", "new_fail"]]


def test_render_history_table_all_clean_history() -> None:
    recs = [
        RunRecord(
            "h1",
            "ops",
            "2026-07-01T02:00:00Z",
            {"clean": 420, "expected_fail": 0, "new_fail": 0, "regression": 0, "incomplete": 0},
            is_clean=True,
            drift=False,
            rows=(),
        ),
        RunRecord(
            "h1",
            "ops",
            "2026-07-04T02:00:00Z",
            {"clean": 420, "expected_fail": 0, "new_fail": 0, "regression": 0, "incomplete": 0},
            is_clean=True,
            drift=False,
            rows=(),
        ),
    ]
    out = render_history_table("h1", recs)
    assert "PERSISTENT FAILURES (streaks): none" in out
    assert "SINCE 2026-07-01T02:00:00Z" in out
    assert "(no change)" in out


def test_render_history_table_empty_history_does_not_crash() -> None:
    out = render_history_table("h9", [])
    assert "history host=h9  (0 runs)" in out
    assert "SINCE PREVIOUS RUN: n/a (need at least two runs)" in out


def test_render_history_json_multi_host() -> None:
    out = render_history_json({"h1": _history_fixture(), "h2": _history_fixture()})
    parsed = _json.loads(out)
    assert set(parsed) == {"h1", "h2"}
    assert len(parsed["h2"]["runs"]) == 3


def test_streaks_excludes_accepted_and_incomplete() -> None:
    # expected_fail (accepted) + incomplete (uneval'd) are non-clean but NOT failures
    records = [
        _rec("2026-07-01T02:00:00Z", (("rule_e", "expected_fail"), ("rule_i", "incomplete"))),
        _rec("2026-07-02T02:00:00Z", (("rule_e", "expected_fail"), ("rule_i", "incomplete"))),
    ]
    assert streaks(records) == []


def test_delta_category_worsening_shows_as_added() -> None:
    # rule_e goes expected_fail (accepted) -> regression (a real failure): must surface as added
    records = [
        _rec("2026-07-01T02:00:00Z", (("rule_e", "expected_fail"),)),
        _rec("2026-07-04T02:00:00Z", (("rule_e", "regression"),)),
    ]
    d = delta(records)
    assert d.added == (("rule_e", "regression"),)
    assert d.recovered == ()


def test_render_table_expected_fail_not_persistent_failure() -> None:
    rec = RunRecord(
        "h1",
        "ops",
        "2026-07-04T02:00:00Z",
        {"clean": 410, "expected_fail": 2, "new_fail": 0, "regression": 0, "incomplete": 0},
        is_clean=True,
        drift=False,
        rows=(("rule_e", "expected_fail"), ("rule_f", "expected_fail")),
    )
    out = render_history_table("h1", [rec])
    assert "CLEAN" in out
    assert "PERSISTENT FAILURES (streaks): none" in out


def test_read_history_skips_jsonl_directory(tmp_path: Path) -> None:
    (tmp_path / "archive.jsonl").mkdir()  # a directory that matches the *.jsonl glob
    write_record(tmp_path, _rec("2026-07-04T02:00:00Z", (("rule_b", "new_fail"),), host="h1"))
    history = read_history(tmp_path)
    assert set(history) == {"h1"}  # the directory is ignored, no crash
