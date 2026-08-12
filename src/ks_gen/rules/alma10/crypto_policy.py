"""alma10 crypto_policy — diverges from alma9.

ssg-almalinux10-ds.xml (0.1.81) dropped `sshd_use_approved_ciphers` and
splits the same check into two stig-selected rules:

  - harden_sshd_ciphers_openssh_conf_crypto_policy
  - harden_sshd_ciphers_opensshserver_conf_crypto_policy

(alma8 already carries these two names for the same reason — AL8 SSG had
them before AL9 dropped the pair.) `enable_fips_mode` is unchanged.

emit_post is reused from alma9: `update-crypto-policies` behaves the same
on AL10.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import crypto_policy as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp
from ks_gen.rules.alma9.crypto_policy import _emit_post

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_PREFIX = "xccdf_org.ssgproject.content_rule_"
_TAILORED_WHEN_NOT_STIG = [
    f"{_PREFIX}enable_fips_mode",
    f"{_PREFIX}harden_sshd_ciphers_openssh_conf_crypto_policy",
    f"{_PREFIX}harden_sshd_ciphers_opensshserver_conf_crypto_policy",
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
