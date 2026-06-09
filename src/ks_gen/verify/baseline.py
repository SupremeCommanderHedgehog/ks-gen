"""Workstation-captured baseline ARF — load, orphan-detect, attach to VerifyReport.

Pure file/parse logic — no SSH, no transport. `read_baseline` loads a
captured ARF; `orphan_rule_ids` computes the rules-in-baseline-but-not-
current set that signals SSG-upgrade staleness.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from ks_gen.loader import ConfigError, ExitCode
from ks_gen.verify.arf import RuleResult, parse_arf
from ks_gen.verify.errors import ArfMissingError


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


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _extract_start_time(text: str) -> str | None:
    """Find the first <TestResult> element and return its start-time attribute.

    Returns None if no TestResult exists or the attribute is absent.
    `read_baseline` calls `parse_arf` separately for the rule results, so this
    helper only walks for the timestamp.
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    for elem in root.iter():
        if _localname(elem.tag) == "TestResult":
            return elem.get("start-time")
    return None


def orphan_rule_ids(
    baseline_results: dict[str, RuleResult],
    current_results: dict[str, RuleResult],
) -> tuple[str, ...]:
    """rule_ids present in baseline but absent from current, sorted.

    The 'stale baseline' signal — typically caused by an SSG upgrade
    between capture and verify. Returns a sorted tuple for stable
    rendering and JSON output.
    """
    return tuple(sorted(set(baseline_results) - set(current_results)))


def read_baseline(path: Path) -> ReadBaseline:
    """Read and parse a captured baseline ARF from disk.

    Raises:
        ConfigError(USAGE): path missing, unreadable, or not a regular file.
        ArfMissingError: file exists but is 0 bytes.
        ArfParseError: malformed XML or no <TestResult>.
    """
    if not path.exists():
        raise ConfigError(f"--baseline path does not exist: {path}", ExitCode.USAGE)
    if not path.is_file():
        raise ConfigError(f"--baseline path is not a regular file: {path}", ExitCode.USAGE)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"--baseline path unreadable: {path}: {e}", ExitCode.USAGE) from e
    if not text:
        raise ArfMissingError(f"baseline file is empty: {path}")

    results = parse_arf(text)  # raises ArfParseError on malformed / no-TestResult
    captured_utc = _extract_start_time(text)
    return ReadBaseline(results=results, captured_utc=captured_utc, path=path)
