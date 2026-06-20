"""alma8 crypto_policy — diverges from alma9.

First real exercise of the "re-export → divergent implementation" pattern
from #121 phase 2's spec: when a rule's SSG mapping differs between alma8
and alma9, its alma8 file becomes a real implementation. Other ks-gen
rules stay as re-exports until/unless their SSG mappings diverge similarly.

What diverges (per #127 PR B audit):
  ssg-almalinux8-ds.xml (0.1.74) has two sshd cipher checks that
  ssg-almalinux9-ds.xml (0.1.80) does not have today:
    - sshd_use_approved_kex_ordered_stig
    - sshd_use_approved_macs

  When the operator chooses a non-STIG crypto policy, our drop-in moots
  these on AL8 (same as AL9's surviving two checks). So alma8 disables
  4 IDs total vs alma9's 2.

What stays shared:
  - emit_post: byte-identical to alma9 — `update-crypto-policies` shipped
    in RHEL 8.0, same command, same effect. We reuse the alma9 helper.
  - emit_packages, applies, depends_on, exception_entry shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import crypto_policy as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

# Reuse the alma9 emit_post helper — the bash invocation is identical on
# AL8 and AL9. The alma9 rule module exposes _emit_post as a module-level
# function specifically so alma8 can import it without duplicating bash.
from ks_gen.rules.alma9.crypto_policy import _emit_post

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_PREFIX = "xccdf_org.ssgproject.content_rule_"
_TAILORED_WHEN_NOT_STIG = [
    f"{_PREFIX}enable_fips_mode",
    f"{_PREFIX}sshd_use_approved_ciphers",
    # AL8-only — gone from ssg-almalinux9 in 0.1.80:
    f"{_PREFIX}sshd_use_approved_kex_ordered_stig",
    f"{_PREFIX}sshd_use_approved_macs",
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
        if cfg.crypto.policy.value == "STIG":
            return []
        return [TailoringOp(rule_id=r, action="disable") for r in _TAILORED_WHEN_NOT_STIG]

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit_post(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        if cfg.crypto.policy.value == "STIG":
            return None
        return ExceptionEntry(
            rule_id=meta.ID,
            summary=f"{cfg.crypto.policy.value} crypto policy",
            stig_rules_disabled=list(_TAILORED_WHEN_NOT_STIG),
            reason=(
                f"{cfg.crypto.policy.value} accepts loss of FIPS 140-3 certification "
                "in exchange for Curve25519 / Ed25519 / ChaCha20-Poly1305 support."
            ),
        )


RULE: Rule = cast(Rule, _Rule())
