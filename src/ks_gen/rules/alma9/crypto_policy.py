from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import crypto_policy as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_PREFIX = "xccdf_org.ssgproject.content_rule_"
# Cleaned up via #127 PR B SSG-drift sweep: dropped sshd_use_approved_kex,
# sshd_use_approved_macs, and sshd_use_approved_mac_ordered — none of
# those exist in current ssg-almalinux9-ds.xml (0.1.80). The two surviving
# IDs (enable_fips_mode, sshd_use_approved_ciphers) are the only crypto
# checks our policy override moots on current AL9 SSG.
_TAILORED_WHEN_NOT_STIG = [
    f"{_PREFIX}enable_fips_mode",
    f"{_PREFIX}sshd_use_approved_ciphers",
]

_POLICY_NAME = {"STIG": "FIPS", "MODERN": "DEFAULT", "FUTURE": "FUTURE"}


def _emit_post(cfg: HostConfig) -> str:
    """Render the %post body for the crypto policy.

    Module-level so the alma8 sibling can reuse it (the post body is
    identical on AL8 and AL9 — `update-crypto-policies` shipped in
    RHEL 8.0). alma8's emit_tailoring diverges (extra cipher rules in
    ssg-almalinux8 that ssg-almalinux9 doesn't have) but emit_post is
    byte-for-byte the same.
    """
    policy = cfg.crypto.policy.value
    target = _POLICY_NAME[policy]
    lines = [
        f"# Apply system-wide crypto policy: {policy} ({target})",
        f"update-crypto-policies --set {target}",
    ]
    if policy != "STIG":
        lines.append("# Generate any missing host keys (incl. Ed25519, not produced under FIPS)")
        lines.append("ssh-keygen -A")
    return "\n".join(lines) + "\n"


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
