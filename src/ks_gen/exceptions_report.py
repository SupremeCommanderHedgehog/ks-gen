from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from ks_gen.config import HostConfig
from ks_gen.rules._types import Rule


def expected_failure_rule_ids(cfg: HostConfig) -> set[str]:
    """Return the set of XCCDF rule ids tailored out by host.yaml.

    Sources: each applicable rule's exception_entry().stig_rules_disabled,
    plus every declared exception in cfg.exceptions. Used by both the
    exceptions.md renderer and `ks-gen verify` (to know which oscap failures
    are expected vs. actionable).
    """
    from ks_gen.registry import load_rules
    from ks_gen.topo import topo_sort

    # The applies() guard here must mirror writer.build_bundle's pre-filter
    # of applicable = [r for r in rules if r.applies(cfg)]; if the two diverge,
    # the exceptions.md report and the verify reconciliation will disagree.
    ids: set[str] = set()
    for r in topo_sort(load_rules(cfg.distro)):
        if not r.applies(cfg):
            continue
        entry = r.exception_entry(cfg)
        if entry is None:
            continue
        ids.update(entry.stig_rules_disabled)
    for ex in cfg.exceptions:
        ids.update(ex.stig_rules_disabled)
    return ids


def render_exceptions_md(cfg: HostConfig, rules: Iterable[Rule]) -> str:
    rules_list = list(rules)
    entries = [(r, r.exception_entry(cfg)) for r in rules_list]
    disabled_xccdf: list[tuple[str, str]] = []
    for r, entry in entries:
        if entry is None:
            continue
        for rid in entry.stig_rules_disabled:
            disabled_xccdf.append((rid, r.id))

    lines: list[str] = []
    lines.append("# Exceptions report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    lines.append(f"Host: `{cfg.system.hostname}`")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- Applied rules: {len(rules_list)}")
    lines.append(f"- Tailored XCCDF rules: {len(disabled_xccdf)}")
    lines.append(f"- Declared exceptions: {len(cfg.exceptions)}")
    lines.append("")

    lines.append("## Applied rules")
    for r in rules_list:
        lines.append(f"- `{r.id}` — {r.summary}")
    lines.append("")

    lines.append("## Tailored XCCDF rules (oscap rules disabled or value-tailored)")
    if not disabled_xccdf:
        lines.append("_(none)_")
    else:
        lines.append("| XCCDF rule | Tailored by |")
        lines.append("|---|---|")
        for rid, owner in disabled_xccdf:
            lines.append(f"| `{rid}` | `{owner}` |")
    lines.append("")

    lines.append("## Rule exception details")
    for _r, entry in entries:
        if entry is None:
            continue
        lines.append(f"### `{entry.rule_id}` — {entry.summary}")
        lines.append("")
        if entry.reason:
            lines.append(f"_Reason:_ {entry.reason}")
            lines.append("")
        if entry.stig_rules_disabled:
            lines.append("Disabled XCCDF rules:")
            for rid in entry.stig_rules_disabled:
                lines.append(f"- `{rid}`")
            lines.append("")

    lines.append("## Declared exceptions (from host.yaml)")
    if not cfg.exceptions:
        lines.append("_(none)_")
    else:
        for ex in cfg.exceptions:
            lines.append(f"### `{ex.id}`")
            lines.append("")
            lines.append(f"_Reason:_ {ex.reason}")
            lines.append("")
            lines.append("Disabled XCCDF rules:")
            for rid in ex.stig_rules_disabled:
                lines.append(f"- `{rid}`")
            lines.append("")

    return "\n".join(lines) + "\n"
