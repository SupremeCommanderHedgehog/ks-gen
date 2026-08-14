"""alma8 crypto_policy — diverges from alma9.

First real exercise of the "re-export → divergent implementation" pattern
from #121 phase 2's spec: when a rule's SSG mapping differs between alma8
and alma9, its alma8 file becomes a real implementation. Other ks-gen
rules stay as re-exports until/unless their SSG mappings diverge similarly.

What no longer diverges (#90):
  ssg-almalinux8 moved a long way between the 8.10 DVD's 0.1.72 and the repos'
  0.1.81 — the stig profile switched `var_system_crypto_policy` from `FIPS` to
  `FIPS:STIG` and dropped most FIPS-only rules. Taken one release at a time
  those look like real divergences from AL9, and pinning to either one alone
  leaves the other kind of install unprotected. Taken as the union over both,
  AL8's disable set is *identical* to AL9's, so this module re-exports it.

  The crypto target is no longer stated here at all: oscap applies whatever the
  installed content refines the value to.

What stays shared:
  - emit_post, emit_tailoring, exception_entry: reuse the alma9 helpers —
    `update-crypto-policies` shipped in RHEL 8.0, same command, same effect,
    and only the disabled-ID list differs.
  - emit_packages, applies, depends_on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import crypto_policy as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

# Reuse the alma9 helpers — the bash invocation and the tailoring shape are
# identical on AL8 and AL9. The alma9 rule module exposes them at module
# level specifically so the siblings can import rather than duplicate.
from ks_gen.rules.alma9.crypto_policy import (
    _TAILORED_WHEN_NOT_STIG,
    _emit_post,
    _emit_tailoring,
    _exception_entry,
)

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=lambda: list(_TAILORED_WHEN_NOT_STIG))

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return _emit_tailoring(cfg, _TAILORED_WHEN_NOT_STIG)

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit_post(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return _exception_entry(cfg, _TAILORED_WHEN_NOT_STIG)


RULE: Rule = cast(Rule, _Rule())
