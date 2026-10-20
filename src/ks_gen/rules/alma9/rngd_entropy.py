"""alma9 rngd_entropy — nothing to do.

The alma8 hazard (#118) needs both halves: the stig profile applying
sshd_use_strong_rng, and a kernel whose /dev/random blocks on its entropy
estimate. AL9's stig profile does not select sshd_use_strong_rng (it does
select package_rng-tools_installed, which nothing here depends on), and its
5.14 kernel's /dev/random stops blocking once the CRNG is initialised. So the
rule never applies here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import rngd_entropy as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return False

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return ""

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return None


RULE: Rule = cast(Rule, _Rule())
