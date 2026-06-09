from __future__ import annotations

import json
from collections import Counter

from ks_gen.verify.reconcile import VerifyReport
from ks_gen.verify.suggest import Suggestion, render_yaml


def _summary(report: VerifyReport) -> dict[str, int]:
    counts: Counter[str] = Counter(r.category for r in report.rows)
    return {
        "clean": counts.get("clean", 0),
        "expected_fail": counts.get("expected_fail", 0),
        "new_fail": counts.get("new_fail", 0),
        "regression": counts.get("regression", 0),
        "incomplete": counts.get("incomplete", 0),
    }


def render_table(report: VerifyReport, *, suggestions: list[Suggestion] | None = None) -> str:
    """Plain-text report. Omits `clean` rows by default to keep output focused.

    When `suggestions` is a non-None list (including empty), appends a
    rendered suggestions block via `render_yaml`. None means "operator
    didn't ask for suggestions" and output is unchanged.
    """
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
        base = "\n".join(lines) + "\n"
    else:
        rule_w = max(len(r.rule_id) for r in visible)
        cat_w = max(len("CATEGORY"), max(len(r.category) for r in visible))
        cur_w = max(len("CURRENT"), max(len(r.current) for r in visible))
        inst_w = max(
            len("INSTALL"),
            max(len(r.install) if r.install is not None else 1 for r in visible),
        )
        lines.append("")
        header = f"  {'CATEGORY':<{cat_w}}  {'CURRENT':<{cur_w}}  {'INSTALL':<{inst_w}}  EXP  RULE"
        lines.append(header)
        for r in visible:
            inst = r.install if r.install is not None else "-"
            exp = "yes" if r.expected else "no "
            cat = f"{r.category:<{cat_w}}"
            cur = f"{r.current:<{cur_w}}"
            instc = f"{inst:<{inst_w}}"
            rule = f"{r.rule_id:<{rule_w}}"
            lines.append(f"  {cat}  {cur}  {instc}  {exp}  {rule}")
        base = "\n".join(lines) + "\n"

    if suggestions is None:
        return base
    suggestion_block = render_yaml(suggestions, report)
    if not suggestion_block:
        return base
    return base + "\n" + suggestion_block


def render_json(report: VerifyReport, *, suggestions: list[Suggestion] | None = None) -> str:
    payload: dict[str, object] = {
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
    if suggestions is not None:
        payload["suggested_exceptions"] = [
            {"category": s.category, "decl": s.decl.model_dump()} for s in suggestions
        ]
    return json.dumps(payload, indent=2)
