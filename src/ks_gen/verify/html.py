"""Self-contained HTML rendering of verify results.

Mirrors the text/json renderers in `report.py`. Imports the shared
`_summary`/`_outcome_summary` helpers from `report.py` — deliberately
one-directional edges (`report.py` never imports this module) so the
module graph stays acyclic (see #13's cyclic-import lesson). Every
dynamic value is passed through `html.escape`; ARF/tailoring content is
untrusted input.
"""

from __future__ import annotations

import html
from collections.abc import Iterable

from ks_gen.loader import ExitCode
from ks_gen.verify.fleet import FleetReport, HostOutcome
from ks_gen.verify.reconcile import VerifyReport, VerifyRow
from ks_gen.verify.report import _outcome_summary, _summary
from ks_gen.verify.suggest import Suggestion, render_yaml

_esc = html.escape

_CSS = """\
body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; margin: 2rem; color: #1a1a1a; }
h1 { font-size: 1.3rem; margin-bottom: 0.2rem; }
h2 { font-size: 1.05rem; margin-top: 1.5rem; }
.badge { display: inline-block; padding: 0.15rem 0.6rem;
         border-radius: 0.25rem; font-weight: 600; color: #fff; }
.badge.clean { background: #1a7f37; }
.badge.drift { background: #b8860b; }
.badge.fail { background: #c0392b; }
.meta { color: #555; font-size: 0.9rem; }
table { border-collapse: collapse; margin-top: 0.75rem; width: 100%; }
th, td { border: 1px solid #ddd; padding: 0.3rem 0.5rem; text-align: left; font-size: 0.9rem; }
th { background: #f3f3f3; }
tr.regression td { background: #fbe9e7; }
tr.new_fail td, tr.verify_fail td { background: #fff3e0; }
tr.expected_fail td { color: #777; }
tr.incomplete td, tr.drift td { background: #fffde7; }
tr.transport td { background: #fbe9e7; }
pre { background: #f6f8fa; padding: 0.75rem; overflow-x: auto; font-size: 0.85rem; }
.note { background: #fff8e1; border-left: 3px solid #f0ad4e;
        padding: 0.4rem 0.6rem; margin-top: 0.6rem; }
"""


def _doc(title: str, body: str) -> str:
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        f"<title>{_esc(title)}</title>\n"
        f"<style>\n{_CSS}</style>\n"
        "</head>\n<body>\n"
        f"{body}\n"
        "</body>\n</html>\n"
    )


def _badge(css_class: str, label: str) -> str:
    return f'<span class="badge {css_class}">{label}</span>'


def _single_verdict(report: VerifyReport) -> tuple[str, str]:
    """(css_class, label) for a single-host report — drift-aware."""
    if not report.is_clean:
        return "fail", "FAILURES"
    if report.has_tailoring_drift:
        return "drift", "DRIFT"
    return "clean", "CLEAN"


def _fleet_verdict(code: int) -> tuple[str, str]:
    """(css_class, label) for the fleet aggregate exit code."""
    if code == int(ExitCode.OK):
        return "clean", "CLEAN"
    if code == int(ExitCode.TAILORING_DRIFT):
        return "drift", "DRIFT"
    return "fail", "FAILURES"


def _verdict_line(css_class: str, label: str, summary_txt: str, *, suffix: str = "") -> str:
    return (
        f"<p>{_badge(css_class, label)} "
        f'<span class="meta">summary: {_esc(summary_txt)}{suffix}</span></p>'
    )


def _rows_table(rows: Iterable[VerifyRow]) -> str:
    visible = [r for r in rows if r.category != "clean"]
    if not visible:
        return "<p>(no actionable rows)</p>"
    out = [
        "<table>",
        "<tr><th>CATEGORY</th><th>CURRENT</th><th>INSTALL</th><th>EXP</th><th>RULE</th></tr>",
    ]
    for r in visible:
        inst = r.install if r.install is not None else "-"
        exp = "yes" if r.expected else "no"
        out.append(
            f'<tr class="{_esc(r.category)}">'
            f"<td>{_esc(r.category)}</td>"
            f"<td>{_esc(r.current)}</td>"
            f"<td>{_esc(inst)}</td>"
            f"<td>{exp}</td>"
            f"<td>{_esc(r.rule_id)}</td>"
            "</tr>"
        )
    out.append("</table>")
    return "\n".join(out)


def _install_note_section(report: VerifyReport) -> str:
    if report.install_baseline_available:
        return ""
    return (
        '<p class="note">NOTE: drift comparison skipped — install-time ARF not present on host</p>'
    )


def _baseline_section(report: VerifyReport) -> str:
    b = report.baseline
    if b is None:
        return ""
    if b.captured_utc is not None:
        line = f"baseline: {_esc(b.path)} (captured {_esc(b.captured_utc)})"
    else:
        line = f"baseline: {_esc(b.path)} (timestamp unknown)"
    parts = [f'<p class="meta">{line}</p>']
    if b.orphans:
        n = len(b.orphans)
        plural = "rule" if n == 1 else "rules"
        parts.append(
            f'<p class="note">NOTE: {n} {plural} in baseline not present in '
            "current ARF — baseline may be stale (SSG upgraded?)</p>"
        )
    return "\n".join(parts)


def _drift_section(report: VerifyReport) -> str:
    d = report.tailoring_drift
    # `d is None` also narrows d for the type-checker; has_tailoring_drift is
    # the semantic gate (it returns False when tailoring_drift is None).
    if d is None or not report.has_tailoring_drift:
        return ""
    items: list[str] = []
    for op in d.added:
        items.append(f"<li>+ {_esc(op.action)} {_esc(op.rule_id)}</li>")
    for op in d.removed:
        items.append(f"<li>- {_esc(op.action)} {_esc(op.rule_id)}</li>")
    for c in d.changed:
        items.append(
            f"<li>~ {_esc(c.rule_id)}: {_esc(c.deployed_value)} → {_esc(c.expected_value)}</li>"
        )
    if d.profile_id_expected != d.profile_id_deployed:
        items.append(
            f"<li>(profile changed: {_esc(d.profile_id_deployed)} → "
            f"{_esc(d.profile_id_expected)})</li>"
        )
    header = (
        "<h2>Tailoring drift</h2>\n"
        '<p class="meta">workstation host.yaml differs from '
        "/root/tailoring.xml — re-run <code>ks-gen gen &lt;host.yaml&gt;</code> "
        "and redeploy to align.</p>\n"
    )
    return header + "<ul>\n" + "\n".join(items) + "\n</ul>"


def _suggestions_section(report: VerifyReport, suggestions: list[Suggestion]) -> str:
    block = render_yaml(suggestions, report)
    if not block:
        return ""
    return "<h2>Suggested exceptions</h2>\n<pre>" + _esc(block) + "</pre>"


def _report_body(report: VerifyReport) -> str:
    """The per-host body: meta line, verdict badge + summary, actionable table.

    Deliberately omits the host heading so single-host (`<h1>`) and fleet
    (`<h2>`) callers can supply their own. Optional sections (baseline,
    install note, drift) are appended after the rows table.
    """
    counts = _summary(report)
    summary_txt = " ".join(f"{k}={v}" for k, v in counts.items())
    css_class, label = _single_verdict(report)
    parts = [
        f'<p class="meta">user={_esc(report.user)} at={_esc(report.timestamp_utc)}</p>',
        _verdict_line(css_class, label, summary_txt),
    ]
    # Section order mirrors the text renderer (baseline, install-note, table,
    # drift). The orphan note is grouped inside _baseline_section for cohesion,
    # which places it before the table rather than after it as the text does.
    for section in (
        _baseline_section(report),
        _install_note_section(report),
        _rows_table(report.rows),
        _drift_section(report),
    ):
        if section:
            parts.append(section)
    return "\n".join(parts)


def render_html(report: VerifyReport, *, suggestions: list[Suggestion] | None = None) -> str:
    """Single-host HTML report."""
    body = f"<h1>verify — {_esc(report.host)}</h1>\n" + _report_body(report)
    if suggestions is not None:
        section = _suggestions_section(report, suggestions)
        if section:
            body = body + "\n" + section
    return _doc(f"ks-gen verify — {report.host}", body)


def _fleet_hosts_table(fleet: FleetReport) -> str:
    out = [
        "<table>",
        "<tr><th>HOST</th><th>STATUS</th><th>SUMMARY</th></tr>",
    ]
    for o in fleet.outcomes:
        out.append(
            f'<tr class="{_esc(o.status)}">'
            f"<td>{_esc(o.spec.host)}</td>"
            f"<td>{_esc(o.status)}</td>"
            f"<td>{_esc(_outcome_summary(o))}</td>"
            "</tr>"
        )
    out.append("</table>")
    return "\n".join(out)


def _host_section(o: HostOutcome) -> str:
    header = f"<h2>{_esc(o.spec.host)} — {_esc(o.status)}</h2>"
    if o.error is not None:
        return header + f'\n<p class="note">{_esc(o.error.label)}: {_esc(o.error.message)}</p>'
    assert o.report is not None
    return header + "\n" + _report_body(o.report)


def render_fleet_html(fleet: FleetReport, *, jobs: int) -> str:
    n = len(fleet.outcomes)
    code = fleet.aggregate_exit_code
    counts = fleet.status_counts()
    summary_txt = " ".join(f"{k}={v}" for k, v in counts.items() if v)
    parts = [
        f"<h1>fleet — {n} host{'s' if n != 1 else ''}</h1>",
        f'<p class="meta">jobs={jobs}</p>',
        _verdict_line(*_fleet_verdict(code), summary_txt, suffix=f" (exit {code})"),
        _fleet_hosts_table(fleet),
    ]
    for o in fleet.outcomes:
        parts.append(_host_section(o))
    return _doc(f"ks-gen verify fleet — {n} hosts", "\n".join(parts))
