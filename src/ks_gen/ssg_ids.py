"""SSG rule-id lists per distro, for checking operator-declared exceptions (#69).

An exception's `stig_rules_disabled` ids reach tailoring.xml verbatim and,
since #65, genuinely deselect rules. A mistyped or bare id deselects nothing
while exceptions.md presents it as a documented waiver, so `gen` checks each
id against the lists extracted from the shipping datastreams
(`docs/audit-story/`, see SSG-VERSIONS.md). The wheel force-includes that
directory as `ks_gen/_audit_story` (pinned by tests/test_ssg_ids.py); a source
checkout reads it in place.

What counts, per distro:
- known: in the current pin's datastream, or stig-selected by a media floor
  (older content an offline install still remediates against — see
  tests/test_rule_ids_selected_by_stig.py for the same union). Floors only
  record stig-selected ids, so a non-stig rule that exists solely in older
  media content reads as unknown.
- stig-selected: by the current pin or any floor.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

RULE_PREFIX = "xccdf_org.ssgproject.content_rule_"
PACKAGED_DIR = "_audit_story"


def _data_dir() -> Traversable | None:
    # Traversable, not Path: a zipped install has no real directory to stat.
    packaged = resources.files("ks_gen").joinpath(PACKAGED_DIR)
    if packaged.is_dir():
        return packaged
    checkout = Path(__file__).resolve().parents[2] / "docs" / "audit-story"
    return checkout if checkout.is_dir() else None


def _read(path: Traversable) -> set[str]:
    return set(path.read_text(encoding="utf-8").split())


@cache
def _lists(distro: str) -> tuple[frozenset[str], frozenset[str]] | None:
    """(known, stig-selected) for `distro`, or None when the lists are absent."""
    root = _data_dir()
    if root is None or not root.joinpath(f"{distro}-rule-ids.txt").is_file():
        return None
    floors: set[str] = set()
    floor_dir = root.joinpath("floors")
    if floor_dir.is_dir():
        for path in sorted(floor_dir.iterdir(), key=lambda p: p.name):
            if path.name.startswith(f"{distro}-") and path.name.endswith("-stig-selected.txt"):
                floors |= _read(path)
    selected = _read(root.joinpath(f"{distro}-stig-selected.txt")) | floors
    known = _read(root.joinpath(f"{distro}-rule-ids.txt")) | selected
    return frozenset(known), frozenset(selected)


@dataclass
class ExceptionIdReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _hint(rid: str, known: frozenset[str]) -> str:
    """Suggest the id the operator probably meant: a missing or partial
    prefix, or a near-miss typo of the rule name."""
    name = rid.rsplit("content_rule_", 1)[-1]
    if RULE_PREFIX + name in known:
        return f" — did you mean {RULE_PREFIX + name!r}?"
    names = [k.removeprefix(RULE_PREFIX) for k in known if k.startswith(RULE_PREFIX)]
    close = difflib.get_close_matches(name, names, n=1, cutoff=0.85)
    return f" — did you mean {RULE_PREFIX + close[0]!r}?" if close else ""


def check_exception_ids(cfg: HostConfig) -> ExceptionIdReport:
    """Unknown ids are errors; known but never stig-selected ones are warnings.

    An unknown id deselects nothing, so the bundle would claim a waiver that
    does not exist. A known-but-unselected id is inert under the stig profile
    but may be what the operator means under another profile, so it only warns
    — and only when the profile is stig, the one the selected lists describe.
    Missing lists fail closed: unchecked ids are the bug this guards against.
    """
    report = ExceptionIdReport()
    if not cfg.exceptions:
        return report
    lists = _lists(cfg.distro)
    if lists is None:
        report.errors.append(
            f"no SSG rule-id list for {cfg.distro} in this ks-gen install, so exception "
            "ids cannot be checked — reinstall ks-gen (the package is incomplete)"
        )
        return report
    known, selected = lists
    for ex in cfg.exceptions:
        for rid in ex.stig_rules_disabled:
            where = f"exception {ex.id!r}: {rid!r}"
            if rid not in known:
                report.errors.append(
                    f"{where} is not a rule in the {cfg.distro} SSG datastream, so it "
                    f"would deselect nothing{_hint(rid, known)}"
                )
            elif cfg.meta.profile == "stig" and rid not in selected:
                report.warnings.append(
                    f"{where} is not selected by the {cfg.distro} stig profile, so "
                    "disabling it has no effect"
                )
    return report
