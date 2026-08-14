"""alma8 crypto_policy — diverges from alma9.

First real exercise of the "re-export → divergent implementation" pattern
from #121 phase 2's spec: when a rule's SSG mapping differs between alma8
and alma9, its alma8 file becomes a real implementation. Other ks-gen
rules stay as re-exports until/unless their SSG mappings diverge similarly.

What diverges (re-derived from the shipped datastreams for #90):
  ssg-almalinux8 0.1.81 moved the stig profile onto the STIG sub-policy —
  `var_system_crypto_policy` refines to `FIPS:STIG`, not the plain `FIPS`
  0.1.74 used — and it stopped selecting almost every FIPS-only rule AL9 and
  AL10 still select: `enable_fips_mode`, `enable_dracut_fips_module`,
  `sysctl_crypto_fips_enabled`, all four `harden_sshd_*_crypto_policy` and
  `sshd_use_approved_kex_ordered_stig` are all unselected here now. Only
  `fips_crypto_subpolicy` is left, so AL8's disable set is a single ID
  against AL9's six and AL10's eight.

  Disabling any of the departed IDs would be inert, which is the #61 bug.

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
    _emit_post,
    _emit_tailoring,
    _exception_entry,
)

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_PREFIX = "xccdf_org.ssgproject.content_rule_"

# Stated in full rather than extending alma9's list: as of ssg-almalinux8
# 0.1.81 the two sets no longer overlap beyond this one ID (#90).
# fips_crypto_subpolicy requires /etc/crypto-policies/config to match
# ^FIPS$|^FIPS:(OSPP|NO-SHA1|NO-CAMELLIA|ECDHE-ONLY|STIG)$, which DEFAULT and
# FUTURE cannot.
_TAILORED_WHEN_NOT_STIG = [
    f"{_PREFIX}fips_crypto_subpolicy",
]


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
