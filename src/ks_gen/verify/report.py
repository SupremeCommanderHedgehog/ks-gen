from __future__ import annotations

import json
from collections import Counter

from ks_gen.verify.reconcile import VerifyReport


def _summary(report: VerifyReport) -> dict[str, int]:
    counts: Counter[str] = Counter(r.category for r in report.rows)
    return {
        "clean": counts.get("clean", 0),
        "expected_fail": counts.get("expected_fail", 0),
        "new_fail": counts.get("new_fail", 0),
        "regression": counts.get("regression", 0),
        "incomplete": counts.get("incomplete", 0),
    }


def render_table(report: VerifyReport) -> str:
    """Plain-text report. Omits `clean` rows by default to keep output focused."""
    lines: list[str] = []
    lines.append(f"verify host={report.host} user={report.user} at={report.timestamp_utc}")
    if not report.install_baseline_available:
        lines.append("  NOTE: drift comparison skipped — install-time ARF not present on host")
    summary = _summary(report)
    lines.append(
        "  summary: "
        + " ".join(f"{k}={v}" for k, v in summary.items())
        + (" — CLEAN" if report.is_clean else " — FAILURES")
    )

    visible = [r for r in report.rows if r.category != "clean"]
    if not visible:
        lines.append("  (no actionable rows)")
        return "\n".join(lines) + "\n"

    rule_w = max(len(r.rule_id) for r in visible)
    cat_w = max(len(r.category) for r in visible)
    lines.append("")
    lines.append(f"  {'CATEGORY':<{cat_w}}  {'CURRENT':<8}  {'INSTALL':<8}  EXP  RULE")
    for r in visible:
        inst = r.install if r.install is not None else "-"
        exp = "yes" if r.expected else "no "
        lines.append(
            f"  {r.category:<{cat_w}}  {r.current:<8}  {inst:<8}  {exp}  {r.rule_id:<{rule_w}}"
        )
    return "\n".join(lines) + "\n"


def render_json(report: VerifyReport) -> str:
    payload = {
        "host": report.host,
        "user": report.user,
        "timestamp_utc": report.timestamp_utc,
        "install_baseline_available": report.install_baseline_available,
        "is_clean": report.is_clean,
        "summary": _summary(report),
        "rows": [
            {
                "rule_id": r.rule_id,
                "current": r.current,
                "install": r.install,
                "expected": r.expected,
                "category": r.category,
            }
            for r in report.rows
        ],
    }
    return json.dumps(payload, indent=2)
