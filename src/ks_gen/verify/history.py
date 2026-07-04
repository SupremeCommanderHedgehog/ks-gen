"""verify run history — slim per-run records, JSONL store, trend analysis.

Pure file + analysis logic: no SSH, no oscap, no host.yaml. Imports one-
directionally from report.py / reconcile.py and is imported only by cli.py,
so the module graph stays acyclic (the CodeQL py/unsafe-cyclic-import lesson
from #13/#15). Records omit `clean` rows entirely ("clean = absent"); the
five category totals live in `summary`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ks_gen.loader import ConfigError, ExitCode
from ks_gen.verify.reconcile import VerifyReport
from ks_gen.verify.report import _summary

# Only new_fail/regression are actual compliance failures — this mirrors
# reconcile.VerifyReport.is_clean. expected_fail (accepted exceptions) and
# incomplete (uneval'd) are non-clean but NOT failures, so trend analysis
# (streaks/delta) excludes them; otherwise a CLEAN run would list accepted
# exceptions under "PERSISTENT FAILURES".
_FAILING_CATEGORIES = frozenset({"new_fail", "regression"})


@dataclass(frozen=True)
class RunRecord:
    host: str
    user: str
    timestamp_utc: str
    # A plain dict (not frozen) on purpose: RunRecord is never hashed or put in a
    # set, and the JSONL store round-trips summary through json.dumps/loads, which
    # needs a real dict. Immutability here would buy nothing and complicate I/O.
    summary: dict[str, int]
    is_clean: bool
    drift: bool
    rows: tuple[tuple[str, str], ...]  # (rule_id, category) for NON-clean rows only

    @property
    def verdict(self) -> Literal["CLEAN", "FAIL"]:
        """CLEAN iff the run had no failures AND no tailoring drift.

        Intentionally drift-aware (unlike report.py's text header, which
        labels on is_clean alone): a drift run exits non-zero, so history
        must not call it CLEAN. Matches the fleet/HTML verdict semantics.
        """
        return "CLEAN" if self.is_clean and not self.drift else "FAIL"

    @property
    def failing_rows(self) -> tuple[tuple[str, str], ...]:
        """(rule_id, category) for rows that are actual failures (new_fail/regression)."""
        return tuple((rid, cat) for rid, cat in self.rows if cat in _FAILING_CATEGORIES)

    @property
    def failing_rule_ids(self) -> frozenset[str]:
        """Rule ids that are actual failures (new_fail/regression) in this run."""
        return frozenset(rid for rid, cat in self.rows if cat in _FAILING_CATEGORIES)


def record_from_report(report: VerifyReport) -> RunRecord:
    """Project a VerifyReport into a slim, storable RunRecord.

    Drops `clean` rows (recoverable from `summary`); keeps the four
    non-clean categories in report order.
    """
    rows = tuple((r.rule_id, r.category) for r in report.rows if r.category != "clean")
    return RunRecord(
        host=report.host,
        user=report.user,
        timestamp_utc=report.timestamp_utc,
        summary=_summary(report),
        is_clean=report.is_clean,
        drift=report.has_tailoring_drift,
        rows=rows,
    )


# ---------------------------------------------------------------------------
# JSONL store — write + read
# ---------------------------------------------------------------------------


def _record_to_dict(record: RunRecord) -> dict[str, object]:
    return {
        "host": record.host,
        "user": record.user,
        "timestamp_utc": record.timestamp_utc,
        "summary": record.summary,
        "is_clean": record.is_clean,
        "drift": record.drift,
        "rows": [[rule_id, category] for rule_id, category in record.rows],
    }


def _record_from_dict(data: object, *, source: Path, lineno: int) -> RunRecord:
    if not isinstance(data, dict):
        raise ConfigError(
            f"{source}:{lineno}: malformed history record: "
            f"expected JSON object, got {type(data).__name__}",
            ExitCode.USAGE,
        )
    try:
        rows = tuple((str(r[0]), str(r[1])) for r in data["rows"])
        summary = {str(k): int(v) for k, v in data["summary"].items()}
        return RunRecord(
            host=str(data["host"]),
            user=str(data["user"]),
            timestamp_utc=str(data["timestamp_utc"]),
            summary=summary,
            is_clean=bool(data["is_clean"]),
            drift=bool(data["drift"]),
            rows=rows,
        )
    except (KeyError, TypeError, IndexError, ValueError, AttributeError) as e:
        raise ConfigError(
            f"{source}:{lineno}: malformed history record: {e}", ExitCode.USAGE
        ) from e


def write_record(record_dir: Path, record: RunRecord) -> None:
    """Append `record` as one JSON line to `<record_dir>/<host>.jsonl`.

    Creates `record_dir` (and parents) if absent. Per-host files are separate,
    so concurrent verify runs against DIFFERENT hosts never cross-contaminate;
    two concurrent runs against the SAME host are not write-safe and should not
    occur in normal operation.

    Raises ConfigError(USAGE) if the path is unusable (e.g. a file where a
    directory is expected, a host name with filesystem-hostile characters, or
    a permission/disk error).
    """
    if record_dir.exists() and not record_dir.is_dir():
        raise ConfigError(f"--record path is not a directory: {record_dir}", ExitCode.USAGE)
    path = record_dir / f"{record.host}.jsonl"
    line = json.dumps(_record_to_dict(record))
    try:
        record_dir.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")
    except OSError as e:
        raise ConfigError(f"cannot write history record to {path}: {e}", ExitCode.USAGE) from e


def read_host_history(path: Path) -> list[RunRecord]:
    """Parse one host's JSONL file, sorted oldest -> newest by timestamp.

    Raises ConfigError(USAGE) on invalid JSON or a record missing required
    keys, naming the file and line number.
    """
    records: list[RunRecord] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"cannot read history file {path}: {e}", ExitCode.USAGE) from e
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as e:
            raise ConfigError(f"{path}:{lineno}: invalid JSON: {e}", ExitCode.USAGE) from e
        records.append(_record_from_dict(data, source=path, lineno=lineno))
    records.sort(key=lambda r: r.timestamp_utc)
    return records


def read_history(record_dir: Path) -> dict[str, list[RunRecord]]:
    """Read every `<host>.jsonl` in `record_dir`, keyed by host (file stem)."""
    if not record_dir.is_dir():
        raise ConfigError(f"history dir not found: {record_dir}", ExitCode.USAGE)
    files = sorted(p for p in record_dir.glob("*.jsonl") if p.is_file())
    if not files:
        raise ConfigError(f"no history records (*.jsonl) found in {record_dir}", ExitCode.USAGE)
    return {path.stem: read_host_history(path) for path in files}


# ---------------------------------------------------------------------------
# Trend analysis — streaks + delta
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Streak:
    rule_id: str
    category: str  # category in the most recent run
    length: int  # consecutive most-recent runs the rule was non-clean


@dataclass(frozen=True)
class Delta:
    since_utc: str | None  # timestamp of the prior run
    added: tuple[tuple[str, str], ...]  # (rule_id, category-in-latest) newly non-clean
    recovered: tuple[tuple[str, str], ...]  # (rule_id, category-in-prior) recovered


def streaks(records: list[RunRecord]) -> list[Streak]:
    """For each rule failing (new_fail/regression) in the latest run, count
    consecutive most-recent runs it stayed failing. Sorted longest streak
    first, then rule_id. Empty when no history or the latest run has no failures.
    """
    if not records:
        return []
    # Precompute each run's failing-rule set once (avoids rebuilding the
    # frozenset per (rule, run) pair in the inner walk).
    failing_sets = [r.failing_rule_ids for r in records]
    latest = records[-1]
    latest_cat = dict(latest.failing_rows)
    result: list[Streak] = []
    for rule_id in latest.failing_rule_ids:
        length = 0
        # walk newest -> oldest; the first run missing this rule ends the streak
        for fset in reversed(failing_sets):
            if rule_id in fset:
                length += 1
            else:
                break
        result.append(Streak(rule_id=rule_id, category=latest_cat[rule_id], length=length))
    result.sort(key=lambda s: (-s.length, s.rule_id))
    return result


def delta(records: list[RunRecord]) -> Delta:
    """Diff the two most recent runs over FAILING rules: newly-failing vs
    recovered. `added` carries each rule's category in the latest run;
    `recovered` its category in the prior run. Empty for 0- or 1-run histories.
    """
    if len(records) < 2:
        return Delta(since_utc=None, added=(), recovered=())
    prev, latest = records[-2], records[-1]
    prev_cat = dict(prev.failing_rows)
    latest_cat = dict(latest.failing_rows)
    added = tuple(sorted((rid, cat) for rid, cat in latest_cat.items() if rid not in prev_cat))
    recovered = tuple(sorted((rid, cat) for rid, cat in prev_cat.items() if rid not in latest_cat))
    return Delta(since_utc=prev.timestamp_utc, added=added, recovered=recovered)


# ---------------------------------------------------------------------------
# Renderers — table + JSON
# ---------------------------------------------------------------------------

_SUMMARY_COLS = ("clean", "expected_fail", "new_fail", "regression", "incomplete")
_COL_HEADERS = ("CLEAN", "EXP", "NEW", "REG", "INC")
_TS_WIDTH = 21  # "YYYY-MM-DDTHH:MM:SSZ" (20 chars) + 1 separator space


def render_history_table(host: str, records: list[RunRecord]) -> str:
    n = len(records)
    lines: list[str] = [f"history host={host}  ({n} run{'s' if n != 1 else ''})", ""]

    # --- timeline ---
    lines.append("  TIMELINE")
    header = (
        f"  {'TIMESTAMP':<{_TS_WIDTH}} " + "  ".join(f"{h:>5}" for h in _COL_HEADERS) + "  VERDICT"
    )
    lines.append(header)
    for rec in records:
        cols = "  ".join(f"{rec.summary.get(c, 0):>5}" for c in _SUMMARY_COLS)
        lines.append(f"  {rec.timestamp_utc:<{_TS_WIDTH}} {cols}  {rec.verdict}")

    # --- streaks ---
    lines.append("")
    st = streaks(records)
    if not st:
        lines.append("  PERSISTENT FAILURES (streaks): none")
    else:
        lines.append("  PERSISTENT FAILURES (streaks)")
        rule_w = max(len(s.rule_id) for s in st)
        cat_w = max(len(s.category) for s in st)
        for s in st:
            runs = "run" if s.length == 1 else "runs"
            lines.append(f"  {s.rule_id:<{rule_w}}  {s.category:<{cat_w}}  last {s.length} {runs}")

    # --- delta ---
    lines.append("")
    d = delta(records)
    if d.since_utc is None:
        lines.append("  SINCE PREVIOUS RUN: n/a (need at least two runs)")
    else:
        lines.append(f"  SINCE {d.since_utc}")
        if not d.added and not d.recovered:
            lines.append("  (no change)")
        if d.added:
            add_cat_w = max(len(cat) for _, cat in d.added)
            for rid, cat in d.added:
                lines.append(f"  + {cat:<{add_cat_w}}  {rid}   (newly failing)")
        for rid, cat in d.recovered:
            lines.append(f"  - recovered   {rid}   (was {cat})")

    return "\n".join(lines) + "\n"


def render_history_json(history: dict[str, list[RunRecord]]) -> str:
    out: dict[str, object] = {}
    for host, records in history.items():
        d = delta(records)
        out[host] = {
            "runs": [
                {
                    "timestamp_utc": r.timestamp_utc,
                    "user": r.user,
                    "summary": r.summary,
                    "verdict": r.verdict,
                    "rows": [[rid, cat] for rid, cat in r.rows],
                }
                for r in records
            ],
            "streaks": [
                {"rule_id": s.rule_id, "category": s.category, "length": s.length}
                for s in streaks(records)
            ],
            "delta": {
                "since_utc": d.since_utc,
                "added": [[rid, cat] for rid, cat in d.added],
                "recovered": [[rid, cat] for rid, cat in d.recovered],
            },
        }
    return json.dumps(out, indent=2)
