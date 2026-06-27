"""ubuntu2404 system-wide crypto policy.

Pins crypto across SSH (sshd_config drop-in), OpenSSL
(/etc/ssl/openssl.cnf.d/), and GnuTLS (/etc/gnutls/default-priorities)
based on cfg.crypto.policy. FIPS validation is owned by a future
pro_attach rule; this rule writes algorithm lists, not entitlements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import crypto_policy as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


_SSH_CIPHERS = {
    "STIG": "aes256-gcm@openssh.com,aes128-gcm@openssh.com,aes256-ctr,aes192-ctr,aes128-ctr",
    "MODERN": "chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com,aes256-ctr,aes192-ctr,aes128-ctr",  # noqa: E501
    "FUTURE": "chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com,aes256-ctr",  # noqa: E501
}

_SSH_KEX = {
    "STIG": "ecdh-sha2-nistp521,ecdh-sha2-nistp384,ecdh-sha2-nistp256,diffie-hellman-group16-sha512,diffie-hellman-group14-sha256",  # noqa: E501
    "MODERN": "curve25519-sha256,curve25519-sha256@libssh.org,ecdh-sha2-nistp521,ecdh-sha2-nistp384,ecdh-sha2-nistp256,diffie-hellman-group16-sha512,diffie-hellman-group14-sha256",  # noqa: E501
    "FUTURE": "curve25519-sha256,curve25519-sha256@libssh.org,ecdh-sha2-nistp521,ecdh-sha2-nistp384,ecdh-sha2-nistp256,diffie-hellman-group16-sha512",  # noqa: E501
}

_SSH_MACS = {
    "STIG": "hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com,hmac-sha2-512,hmac-sha2-256",  # noqa: E501
    "MODERN": "hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com,hmac-sha2-512,hmac-sha2-256",  # noqa: E501
    "FUTURE": "hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com",
}

_SSH_HOSTKEYS = {
    "STIG": "ssh-rsa,rsa-sha2-512,rsa-sha2-256,ecdsa-sha2-nistp521,ecdsa-sha2-nistp384,ecdsa-sha2-nistp256",  # noqa: E501
    "MODERN": "ssh-ed25519,ssh-rsa,rsa-sha2-512,rsa-sha2-256,ecdsa-sha2-nistp521,ecdsa-sha2-nistp384,ecdsa-sha2-nistp256",  # noqa: E501
    "FUTURE": "ssh-ed25519,rsa-sha2-512,rsa-sha2-256,ecdsa-sha2-nistp521,ecdsa-sha2-nistp384",
}

# PubkeyAcceptedAlgorithms takes the same algorithm set as HostKeyAlgorithms.
_SSH_PUBKEYS = _SSH_HOSTKEYS

_OPENSSL_MIN_PROTO = {"STIG": "TLSv1.2", "MODERN": "TLSv1.2", "FUTURE": "TLSv1.3"}
_OPENSSL_CIPHERSTR = {
    "STIG": "DEFAULT@SECLEVEL=2",
    "MODERN": "DEFAULT@SECLEVEL=2",
    "FUTURE": "DEFAULT@SECLEVEL=3",
}

_GNUTLS_PRIORITY = {"STIG": "SECURE128", "MODERN": "SECURE128", "FUTURE": "SECURE256"}

# ssg-ubuntu2404-ds.xml names the FIPS check `is_fips_mode_enabled` (vs
# alma9's `enable_fips_mode`) and the three sshd cipher checks carry an
# `_ordered_stig` suffix (vs alma9's bare names). Same conceptual targets
# — our crypto_policy override moots them when policy != STIG.
_PREFIX = "xccdf_org.ssgproject.content_rule_"
_TAILORED_WHEN_NOT_STIG = [
    f"{_PREFIX}is_fips_mode_enabled",
    f"{_PREFIX}sshd_use_approved_ciphers_ordered_stig",
    f"{_PREFIX}sshd_use_approved_kex_ordered_stig",
    f"{_PREFIX}sshd_use_approved_macs_ordered_stig",
]


def _emit_ssh(cfg: HostConfig) -> str:
    policy = cfg.crypto.policy.value
    banner = ""
    if policy == "STIG":
        banner = (
            "# WARNING: STIG-aligned algorithms but NOT FIPS-validated. For\n"
            "# FIPS-validated crypto, add the future pro_attach rule to enable\n"
            "# Ubuntu Pro `fips-updates`.\n"
        )
    body = (
        f"{banner}"
        f"Ciphers {_SSH_CIPHERS[policy]}\n"
        f"KexAlgorithms {_SSH_KEX[policy]}\n"
        f"MACs {_SSH_MACS[policy]}\n"
        f"HostKeyAlgorithms {_SSH_HOSTKEYS[policy]}\n"
        f"PubkeyAcceptedAlgorithms {_SSH_PUBKEYS[policy]}\n"
    )
    tail = "sshd -t" if policy == "STIG" else "ssh-keygen -A\nsshd -t"
    return f"""\
# SSH crypto policy ({policy})
install -d -m 755 /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/10-ks-gen-crypto.conf <<'__KS_GEN_EOF__'
{body}__KS_GEN_EOF__
chmod 600 /etc/ssh/sshd_config.d/10-ks-gen-crypto.conf
{tail}
"""


def _emit_openssl(cfg: HostConfig) -> str:
    policy = cfg.crypto.policy.value
    return f"""\
# OpenSSL crypto policy ({policy})
install -d -m 755 /etc/ssl/openssl.cnf.d
cat > /etc/ssl/openssl.cnf.d/10-ks-gen.conf <<'__KS_GEN_EOF__'
[default_sect]
activate = 1
[system_default_sect]
MinProtocol = {_OPENSSL_MIN_PROTO[policy]}
CipherString = {_OPENSSL_CIPHERSTR[policy]}
__KS_GEN_EOF__
chmod 644 /etc/ssl/openssl.cnf.d/10-ks-gen.conf
"""


def _emit_gnutls(cfg: HostConfig) -> str:
    policy = cfg.crypto.policy.value
    return f"""\
# GnuTLS crypto policy ({policy})
install -d -m 755 /etc/gnutls
cat > /etc/gnutls/default-priorities <<'__KS_GEN_EOF__'
{_GNUTLS_PRIORITY[policy]}
__KS_GEN_EOF__
chmod 644 /etc/gnutls/default-priorities
"""


def _emit(cfg: HostConfig) -> str:
    return "".join([_emit_ssh(cfg), _emit_openssl(cfg), _emit_gnutls(cfg)])


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
        return _emit(cfg)

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
