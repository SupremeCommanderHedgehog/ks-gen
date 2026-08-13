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
``<out-dir>/<label>-rule-ids.txt`` (one rule ID per line, sorted, deduped),
``<out-dir>/<label>-stig-selected.txt`` (the subset the ``stig`` profile
actually selects), ``<out-dir>/<label>-stig-refine-values.txt`` and
``<out-dir>/<label>-fips-candidates.txt`` (stig-selected rules whose check or
remediation touches FIPS). With 2+ datastreams, also writes
``<out-dir>/cross-distro-rule-id-diff.md`` with set ops (all-in-all, pairwise
intersections, distro-only sets).

The stig-selected list exists because rule *existence* is too weak a guard:
disabling a rule the ``stig`` profile never selects is inert, and looks like
a working exception (see #61).

The fips-candidates list exists for the converse guard (#67): a stig-selected
rule that cannot pass without FIPS stays enabled unless someone notices it, so
every candidate must be explicitly classified by
``tests/test_fips_dependent_rules.py``.
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from itertools import combinations
from pathlib import Path

XCCDF_NS = "http://checklists.nist.gov/xccdf/1.2"

# Deliberately broad: the list is a "classify me" queue, not a disable list.
# False positives (aide_use_fips_hashes wants sha512 in aide.conf and passes
# under any policy) are cheap — an unclassified new rule is not.
_CHECK_MARKERS = re.compile(r"fips|/proc/sys/crypto|crypto-policies/config", re.IGNORECASE)
_FIX_MARKERS = re.compile(r"fips-mode-setup|update-crypto-policies|fips=1|40-fips")


def extract_rule_ids(datastream_path: Path) -> set[str]:
    """Return the set of xccdf:Rule@id values in the given SSG datastream."""
    tree = ET.parse(datastream_path)
    return {elem.attrib["id"] for elem in tree.iter(f"{{{XCCDF_NS}}}Rule") if "id" in elem.attrib}


def extract_stig_selected_rule_ids(datastream_path: Path) -> set[str]:
    """Return the rule IDs the ``stig`` profile selects in the given datastream.

    Profile IDs look like ``xccdf_org.ssgproject.content_profile_stig``; the
    trailing component after ``content_profile_`` is the profile name.
    """
    tree = ET.parse(datastream_path)
    selected: set[str] = set()
    for profile in tree.iter(f"{{{XCCDF_NS}}}Profile"):
        name = profile.attrib.get("id", "").rsplit("content_profile_", 1)[-1]
        if name != "stig":
            continue
        selected |= {
            sel.attrib["idref"]
            for sel in profile.iter(f"{{{XCCDF_NS}}}select")
            if sel.attrib.get("selected") == "true" and "idref" in sel.attrib
        }
    return selected


def extract_stig_refine_values(datastream_path: Path) -> dict[str, str]:
    """Return the ``stig`` profile's refine-value settings, resolved to values.

    A profile picks an XCCDF Value's *selector*; the value itself lives on the
    Value element. ks-gen has to apply the same string the profile expects
    (e.g. `update-crypto-policies --set FIPS:STIG`), and the two are written in
    different places, so this makes the expected side machine-readable (#66).
    """
    tree = ET.parse(datastream_path)

    selectors: dict[str, dict[str, str]] = {}
    for value in tree.iter(f"{{{XCCDF_NS}}}Value"):
        vid = value.attrib.get("id")
        if not vid:
            continue
        by_selector: dict[str, str] = {}
        for child in value:
            if child.tag == f"{{{XCCDF_NS}}}value" and child.attrib.get("selector"):
                by_selector[child.attrib["selector"]] = (child.text or "").strip()
        if by_selector:
            selectors[vid] = by_selector

    resolved: dict[str, str] = {}
    for profile in tree.iter(f"{{{XCCDF_NS}}}Profile"):
        if profile.attrib.get("id", "").rsplit("content_profile_", 1)[-1] != "stig":
            continue
        for refine in profile.iter(f"{{{XCCDF_NS}}}refine-value"):
            idref = refine.attrib.get("idref")
            selector = refine.attrib.get("selector")
            if idref and selector and selector in selectors.get(idref, {}):
                resolved[idref] = selectors[idref][selector]
    return resolved


def _local_tag(elem: ET.Element) -> str:
    return elem.tag.rsplit("}", 1)[-1]


def _index_oval(tree: ET.ElementTree) -> dict[str, dict[str, ET.Element]]:
    """Map OVAL definitions/tests/objects/states by id, from the embedded components."""
    index: dict[str, dict[str, ET.Element]] = {"def": {}, "tst": {}, "obj": {}, "ste": {}}
    for elem in tree.iter():
        eid = elem.get("id")
        if not eid:
            continue
        tag = _local_tag(elem)
        if tag == "definition":
            index["def"][eid] = elem
        elif tag.endswith("_test"):
            index["tst"][eid] = elem
        elif tag.endswith("_object"):
            index["obj"][eid] = elem
        elif tag.endswith("_state"):
            index["ste"][eid] = elem
    return index


def _oval_check_text(rule: ET.Element, index: dict[str, dict[str, ET.Element]]) -> str:
    """The rule's OVAL criteria, tests, objects and states flattened to one string."""
    def_id = None
    for child in rule.iter():
        name = child.get("name") or ""
        if _local_tag(child) == "check-content-ref" and name.startswith("oval:"):
            def_id = name
    definition = index["def"].get(def_id or "")
    if definition is None:
        return ""

    parts: list[str] = []
    for criterion in definition.iter():
        if _local_tag(criterion) != "criterion":
            continue
        parts.append(criterion.get("comment") or "")
        test = index["tst"].get(criterion.get("test_ref") or "")
        if test is None:
            continue
        parts.append(test.get("comment") or "")
        for ref in test:
            target = ref.get("object_ref") or ref.get("state_ref") or ""
            node = index["obj"].get(target)
            if node is None:
                node = index["ste"].get(target)
            if node is not None:
                parts.append(ET.tostring(node, encoding="unicode"))
    return " ".join(parts)


def _shell_fix_text(rule: ET.Element) -> str:
    return "".join(
        "".join(child.itertext())
        for child in rule
        if _local_tag(child) == "fix" and child.get("system", "").endswith("script:sh")
    )


def extract_fips_candidates(datastream_path: Path, selected: set[str]) -> dict[str, str]:
    """Return stig-selected rules whose OVAL check or shell fix touches FIPS.

    Keyed by rule ID, valued by the markers that matched, so a reviewer can see
    *why* a rule is on the queue without re-reading the datastream. A check
    marker means the rule may be unable to pass off FIPS; a fix marker means its
    remediation may reconfigure a deliberately non-FIPS host (#67).
    """
    tree = ET.parse(datastream_path)
    index = _index_oval(tree)

    candidates: dict[str, str] = {}
    for rule in tree.iter(f"{{{XCCDF_NS}}}Rule"):
        rule_id = rule.get("id")
        if not rule_id or rule_id not in selected:
            continue
        check_text = _oval_check_text(rule, index)
        check_hits = sorted({m.group(0).lower() for m in _CHECK_MARKERS.finditer(check_text)})
        fix_hits = sorted({m.group(0) for m in _FIX_MARKERS.finditer(_shell_fix_text(rule))})
        if not check_hits and not fix_hits:
            continue
        markers = [f"check:{h}" for h in check_hits] + [f"fix:{h}" for h in fix_hits]
        candidates[rule_id] = " ".join(markers)
    return candidates


def write_fips_candidates(candidates: dict[str, str], out_path: Path) -> None:
    """One ``<rule-id>\\t<markers>`` per line, sorted."""
    lines = [f"{k}\t{v}" for k, v in sorted(candidates.items())]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_refine_values(values: dict[str, str], out_path: Path) -> None:
    """One ``<value-id>\\t<resolved value>`` per line, sorted."""
    lines = [f"{k}\t{v}" for k, v in sorted(values.items())]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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

        selected = extract_stig_selected_rule_ids(path)
        sel_out = args.out_dir / f"{label}-stig-selected.txt"
        write_rule_id_list(selected, sel_out)
        print(f"{label}: {len(selected)} stig-selected -> {sel_out}")

        fips = extract_fips_candidates(path, selected)
        fips_out = args.out_dir / f"{label}-fips-candidates.txt"
        write_fips_candidates(fips, fips_out)
        print(f"{label}: {len(fips)} fips candidates -> {fips_out}")

        refined = extract_stig_refine_values(path)
        val_out = args.out_dir / f"{label}-stig-refine-values.txt"
        write_refine_values(refined, val_out)
        print(f"{label}: {len(refined)} stig refine-values -> {val_out}")

    if len(per_distro) >= 2:
        diff_out = args.out_dir / "cross-distro-rule-id-diff.md"
        write_cross_distro_diff(per_distro, diff_out)
        print(f"cross-distro diff -> {diff_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
