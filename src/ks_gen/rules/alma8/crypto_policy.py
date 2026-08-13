"""alma8 crypto_policy — diverges from alma9.

First real exercise of the "re-export → divergent implementation" pattern
from #121 phase 2's spec: when a rule's SSG mapping differs between alma8
and alma9, its alma8 file becomes a real implementation. Other ks-gen
rules stay as re-exports until/unless their SSG mappings diverge similarly.

What diverges (re-derived from the datastreams for #61 and #67):
  ssg-almalinux8-ds.xml (0.1.74) still selects
  `sshd_use_approved_kex_ordered_stig`, which ssg-almalinux9-ds.xml (0.1.80)
  dropped entirely, and it does not select `fips_crypto_subpolicy` at all.
  Both distros end up disabling 8 rules, but not the same 8.

  The earlier alma8 set also carried `sshd_use_approved_ciphers` and
  `sshd_use_approved_macs`. Both exist in the AL8 datastream but the stig
  profile selects neither, so disabling them was inert (#61).

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
    _FIPS_ONLY_COMMON,
    _emit_post,
    _emit_tailoring,
    _exception_entry,
)

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_PREFIX = "xccdf_org.ssgproject.content_rule_"
_TAILORED_WHEN_NOT_STIG = [
    *_FIPS_ONLY_COMMON,
    # AL8-only — gone from ssg-almalinux9 in 0.1.80, still stig-selected here:
    f"{_PREFIX}sshd_use_approved_kex_ordered_stig",
    # AL8's remediation for this one runs `fips-mode-setup --enable`, which
    # would add fips=1 to the kernel args of a host that opted out (#67).
    # AL10 does not select it; AL9 selects it without a remediation.
    f"{_PREFIX}enable_dracut_fips_module",
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
