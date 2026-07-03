from __future__ import annotations

import json
from collections import Counter

from ks_gen.verify.fleet import FleetReport, HostOutcome
from ks_gen.verify.reconcile import VerifyReport
from ks_gen.verify.suggest import Suggestion, render_yaml
from ks_gen.verify.tailoring_drift import render_drift_section


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
    didn't ask for suggestions" and that section is omitted.

    When `report.tailoring_drift` is populated and non-empty, appends a
    drift section between the table and any suggestions block.
    """
    lines: list[str] = []
    lines.append(f"verify host={report.host} user={report.user} at={report.timestamp_utc}")
    if report.baseline is not None:
        ts = report.baseline.captured_utc
        if ts is not None:
            lines.append(f"  baseline: {report.baseline.path} (captured {ts})")
        else:
            lines.append(f"  baseline: {report.baseline.path} (timestamp unknown)")
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

    if report.baseline is not None and report.baseline.orphans:
        n = len(report.baseline.orphans)
        plural = "rule" if n == 1 else "rules"
        base = (
            base + f"  NOTE: {n} {plural} in baseline not present in current ARF "
            "— baseline may be stale (SSG upgraded?)\n"
        )

    if report.tailoring_drift is not None:
        drift_section = render_drift_section(report.tailoring_drift)
        if drift_section:
            base = base + "\n" + drift_section

    if suggestions is None:
        return base
    suggestion_block = render_yaml(suggestions, report)
    if not suggestion_block:
        return base
    return base + "\n" + suggestion_block


def _report_payload(report: VerifyReport) -> dict[str, object]:
    """The single-host JSON body, sans suggestions. Reused by fleet JSON."""
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
    drift = report.tailoring_drift
    if drift is not None:
        payload["tailoring_drift"] = {
            "profile_id_expected": drift.profile_id_expected,
            "profile_id_deployed": drift.profile_id_deployed,
            "added": [
                {"action": op.action, "rule_id": op.rule_id, "value": op.value}
                for op in drift.added
            ],
            "removed": [
                {"action": op.action, "rule_id": op.rule_id, "value": op.value}
                for op in drift.removed
            ],
            "changed": [
                {
                    "rule_id": c.rule_id,
                    "action": c.action,
                    "expected_value": c.expected_value,
                    "deployed_value": c.deployed_value,
                }
                for c in drift.changed
            ],
        }
    baseline = report.baseline
    if baseline is not None:
        payload["baseline"] = {
            "path": baseline.path,
            "captured_utc": baseline.captured_utc,
            "orphans": list(baseline.orphans),
        }
    return payload


def render_json(report: VerifyReport, *, suggestions: list[Suggestion] | None = None) -> str:
    payload = _report_payload(report)
    if suggestions is not None:
        payload["suggested_exceptions"] = [
            {"category": s.category, "decl": s.decl.model_dump()} for s in suggestions
        ]
    return json.dumps(payload, indent=2)


def _outcome_summary(outcome: HostOutcome) -> str:
    if outcome.error is not None:
        first = outcome.error.message.splitlines()[0] if outcome.error.message else ""
        return f"{outcome.error.label}: {first}"
    assert outcome.report is not None
    counts = _summary(outcome.report)
    nonzero = " ".join(f"{k}={v}" for k, v in counts.items() if v)
    if outcome.status == "drift":
        nonzero = (nonzero + " (tailoring drift)").strip()
    return nonzero or "(no rows)"


def render_fleet_table(fleet: FleetReport, *, jobs: int) -> str:
    n = len(fleet.outcomes)
    lines: list[str] = [f"fleet: {n} host{'s' if n != 1 else ''}  jobs={jobs}"]
    host_w = max((len(o.spec.host) for o in fleet.outcomes), default=len("HOST"))
    host_w = max(host_w, len("HOST"))
    status_w = max((len(o.status) for o in fleet.outcomes), default=len("STATUS"))
    status_w = max(status_w, len("STATUS"))
    lines.append(f"  {'HOST':<{host_w}}  {'STATUS':<{status_w}}  SUMMARY")
    for o in fleet.outcomes:
        lines.append(f"  {o.spec.host:<{host_w}}  {o.status:<{status_w}}  {_outcome_summary(o)}")
    lines.append("  " + "-" * 6)
    counts = fleet.status_counts()
    code = fleet.aggregate_exit_code
    verdict = "CLEAN" if code == 0 else "FAILURES"
    summary = " ".join(f"{k}={v}" for k, v in counts.items() if v)
    lines.append(f"  summary: {summary} -> {verdict} (exit {code})")
    return "\n".join(lines) + "\n"


def render_fleet_json(fleet: FleetReport) -> str:
    hosts: list[dict[str, object]] = []
    for o in fleet.outcomes:
        entry: dict[str, object] = {
            "host": o.spec.host,
            "user": o.user or o.spec.user,
            "status": o.status,
        }
        if o.error is not None:
            entry["error"] = {
                "label": o.error.label,
                "message": o.error.message,
                "exit_code": o.error.exit_code,
            }
        else:
            assert o.report is not None
            entry["report"] = _report_payload(o.report)
        hosts.append(entry)
    payload = {
        "hosts": hosts,
        "summary": fleet.status_counts(),
        "aggregate_exit_code": fleet.aggregate_exit_code,
    }
    return json.dumps(payload, indent=2)
