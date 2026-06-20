#!/usr/bin/env python3
"""Extract xccdf:Rule IDs from one or more SSG datastream files.

Used to produce the per-distro rule ID lists + cross-distro diff under
``docs/audit-story/`` for the cross-distro audit-story PR (#127 phase 1).

Usage:

    python3 scripts/audit_story/extract_ssg_rule_ids.py \\
        --datastream alma8=/tmp/ssg-extract/.../ssg-almalinux8-ds.xml \\
        --datastream alma9=/tmp/ssg-extract/.../ssg-almalinux9-ds.xml \\
        --datastream ubuntu2404=/tmp/ssg-extract/.../ssg-ubuntu2404-ds.xml \\
        --out-dir docs/audit-story/

For each ``--datastream <label>=<path>`` pair, writes
``<out-dir>/<label>-rule-ids.txt`` (one rule ID per line, sorted, deduped).
With 2+ datastreams, also writes ``<out-dir>/cross-distro-rule-id-diff.md``
with set ops (all-in-all, pairwise intersections, distro-only sets).
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from itertools import combinations
from pathlib import Path

XCCDF_NS = "http://checklists.nist.gov/xccdf/1.2"


def extract_rule_ids(datastream_path: Path) -> set[str]:
    """Return the set of xccdf:Rule@id values in the given SSG datastream."""
    tree = ET.parse(datastream_path)
    return {elem.attrib["id"] for elem in tree.iter(f"{{{XCCDF_NS}}}Rule") if "id" in elem.attrib}


def write_rule_id_list(ids: set[str], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(sorted(ids)) + "\n", encoding="utf-8")


def write_cross_distro_diff(per_distro: dict[str, set[str]], out_path: Path) -> None:
    """Write a markdown report comparing the rule-ID sets across distros."""
    distros = sorted(per_distro)
    lines: list[str] = ["# Cross-distro SSG rule-ID diff\n"]

    lines.append("## Totals per distro\n")
    for d in distros:
        lines.append(f"- `{d}`: {len(per_distro[d])} rules")
    lines.append("")

    if len(distros) >= 2:
        in_all = set.intersection(*per_distro.values())
        lines.append(f"## In all {len(distros)} distros\n")
        lines.append(f"- {len(in_all)} rules shared across {', '.join(f'`{d}`' for d in distros)}")
        lines.append("")

    if len(distros) >= 2:
        lines.append("## Pairwise intersections\n")
        for a, b in combinations(distros, 2):
            both = per_distro[a] & per_distro[b]
            lines.append(f"- `{a}` ∩ `{b}`: {len(both)} rules")
        lines.append("")

    lines.append("## Distro-only sets\n")
    for d in distros:
        others: set[str] = set()
        for other_d, ids in per_distro.items():
            if other_d != d:
                others |= ids
        only = per_distro[d] - others
        lines.append(f"### `{d}` only ({len(only)} rules)\n")
        if only:
            for rule_id in sorted(only):
                lines.append(f"- `{rule_id}`")
        else:
            lines.append("_(none)_")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def _parse_datastream_arg(arg: str) -> tuple[str, Path]:
    if "=" not in arg:
        raise argparse.ArgumentTypeError(
            f"expected label=path, got: {arg!r}",
        )
    label, _, path = arg.partition("=")
    return label, Path(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--datastream",
        action="append",
        required=True,
        type=_parse_datastream_arg,
        metavar="LABEL=PATH",
        help="repeatable: distro label and ssg-*-ds.xml path",
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        type=Path,
        help="output directory (created if missing)",
    )
    args = parser.parse_args(argv)

    per_distro: dict[str, set[str]] = {}
    for label, path in args.datastream:
        if not path.is_file():
            print(f"error: {path} not found", file=sys.stderr)
            return 2
        ids = extract_rule_ids(path)
        per_distro[label] = ids
        out = args.out_dir / f"{label}-rule-ids.txt"
        write_rule_id_list(ids, out)
        print(f"{label}: {len(ids)} rules -> {out}")

    if len(per_distro) >= 2:
        diff_out = args.out_dir / "cross-distro-rule-id-diff.md"
        write_cross_distro_diff(per_distro, diff_out)
        print(f"cross-distro diff -> {diff_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
