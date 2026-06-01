from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LintReport:
    ok: bool
    failures: list[str] = field(default_factory=list)


def lint_kickstart(path: Path) -> LintReport:
    """Stub — replaced with full implementation in Task 31."""
    return LintReport(ok=True)
