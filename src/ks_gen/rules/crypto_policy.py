from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_PREFIX = "xccdf_org.ssgproject.content_rule_"
_TAILORED_WHEN_NOT_STIG = [
    f"{_PREFIX}enable_fips_mode",
    f"{_PREFIX}sshd_use_approved_ciphers",
    f"{_PREFIX}sshd_use_approved_kex",
    f"{_PREFIX}sshd_use_approved_macs",
    f"{_PREFIX}sshd_use_approved_mac_ordered",
]

_POLICY_NAME = {"STIG": "FIPS", "MODERN": "DEFAULT", "FUTURE": "FUTURE"}


@dataclass(frozen=True)
class _Rule:
    id: str = "crypto_policy"
    summary: str = "Apply system crypto-policy; optionally generate Ed25519 host keys."
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=lambda: list(_TAILORED_WHEN_NOT_STIG))

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        if cfg.crypto.policy.value == "STIG":
            return []
        return [TailoringOp(rule_id=r, action="disable") for r in _TAILORED_WHEN_NOT_STIG]

    def emit_post(self, cfg: HostConfig) -> str:
        policy = cfg.crypto.policy.value
        target = _POLICY_NAME[policy]
        lines = [
            f"# Apply system-wide crypto policy: {policy} ({target})",
            f"update-crypto-policies --set {target}",
        ]
        if policy != "STIG":
            lines.append(
                "# Generate any missing host keys (incl. Ed25519, not produced under FIPS)"
            )
            lines.append("ssh-keygen -A")
        return "\n".join(lines) + "\n"

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        if cfg.crypto.policy.value == "STIG":
            return None
        return ExceptionEntry(
            rule_id="crypto_policy",
            summary=f"{cfg.crypto.policy.value} crypto policy",
            stig_rules_disabled=list(_TAILORED_WHEN_NOT_STIG),
            reason=(
                f"{cfg.crypto.policy.value} accepts loss of FIPS 140-3 certification "
                "in exchange for Curve25519 / Ed25519 / ChaCha20-Poly1305 support."
            ),
        )


RULE: Rule = cast(Rule, _Rule())
