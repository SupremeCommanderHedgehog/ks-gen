"""ubuntu2404 faillock soften-lockout rule.

Writes /etc/security/faillock.conf and wires pam_faillock into the
common-auth/common-account stack via pam-auth-update. Wiring is
required on Ubuntu because the libpam-modules package ships
pam_faillock.so but does not auto-enable it (unlike RHEL).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import faillock_safety as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


def _emit_faillock_conf(cfg: HostConfig) -> str:
    f = cfg.overrides.faillock
    even = "yes" if f.even_deny_root else "no"
    conf = "/etc/security/faillock.conf"
    return (
        "# faillock.conf — soften lockout for remote-safe operation\n"
        f"sed -i -E 's/^[# ]*unlock_time *=.*/unlock_time = {f.unlock_time}/' {conf}\n"
        f"grep -q '^unlock_time' {conf} || echo 'unlock_time = {f.unlock_time}' >> {conf}\n"
        f"sed -i -E 's/^[# ]*deny *=.*/deny = {f.deny}/' {conf}\n"
        f"grep -q '^deny' {conf} || echo 'deny = {f.deny}' >> {conf}\n"
        f"sed -i -E 's/^[# ]*even_deny_root.*/# even_deny_root removed by ks-gen: {even}/' {conf}\n"
    )


def _emit_pam_profile(cfg: HostConfig) -> str:
    return """\
# pam-auth-update profile (wires pam_faillock into common-auth/common-account)
install -d -m 755 /usr/share/pam-configs
cat > /usr/share/pam-configs/ks-gen-faillock <<'__KS_GEN_EOF__'
Name: pam_faillock (ks-gen)
Default: yes
Priority: 1024
Auth-Type: Primary
Auth-Initial:
        [default=die]                  pam_faillock.so authfail
Auth:
        [success=1 default=ignore]     pam_faillock.so preauth
Account-Type: Primary
Account:
        required                       pam_faillock.so
__KS_GEN_EOF__
chmod 644 /usr/share/pam-configs/ks-gen-faillock
"""


def _emit_pam_enable(cfg: HostConfig) -> str:
    return "DEBIAN_FRONTEND=noninteractive pam-auth-update --enable ks-gen-faillock --package\n"


def _emit(cfg: HostConfig) -> str:
    return "".join([_emit_faillock_conf(cfg), _emit_pam_profile(cfg), _emit_pam_enable(cfg)])


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return cfg.overrides.faillock.enable

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        # Deferred: ssg-ubuntu2404-ds.xml faillock rule survey lands in the audit-story PR.
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        # Deferred: paired with emit_tailoring above; see audit-story PR.
        return None


RULE: Rule = cast(Rule, _Rule())
