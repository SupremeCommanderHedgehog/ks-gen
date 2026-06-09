"""Workstation-captured baseline ARF — load, orphan-detect, attach to VerifyReport.

Pure file/parse logic — no SSH, no transport. `read_baseline` loads a
captured ARF; `orphan_rule_ids` computes the rules-in-baseline-but-not-
current set that signals SSG-upgrade staleness.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ks_gen.verify.arf import RuleResult


@dataclass(frozen=True)
class ReadBaseline:
    """A captured ARF loaded from disk.

    `results` is the parsed `{rule_id: RuleResult}`; `captured_utc` is the
    ARF's `<TestResult start-time="...">` attribute, or None if absent;
    `path` is where it was loaded from (kept for reports).
    """

    results: dict[str, RuleResult]
    captured_utc: str | None
    path: Path


@dataclass(frozen=True)
class BaselineReport:
    """Reportable summary of which baseline drove this verify run.

    Attached to `VerifyReport.baseline` when `--baseline` was used.
    `path` is the operator-supplied string (so it survives JSON
    serialization without Path-conversion concerns).
    """

    path: str
    captured_utc: str | None
    orphans: tuple[str, ...]
