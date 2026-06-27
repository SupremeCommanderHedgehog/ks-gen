from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import admin_user_and_keys as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


def _emit(cfg: HostConfig) -> str:
    admin = cfg.user.admin
    name = admin.name
    groups = ",".join(admin.groups)
    home = f"/home/{name}"
    keys = "\n".join(admin.authorized_keys)
    pw_block = (
        f'echo "{name}:{admin.password}" | chpasswd -e\n'
        if admin.password
        else f"passwd -l {name}\n"
    )
    sudo_line = (
        f"{name} ALL=(ALL) NOPASSWD: ALL"
        if admin.sudo == "nopasswd_yes"
        else f"{name} ALL=(ALL) ALL"
    )
    return f"""\
# Create admin user (idempotent)
if ! getent passwd {name} >/dev/null 2>&1; then
  useradd --create-home --shell {admin.shell} --groups {groups} --comment "{admin.gecos}" {name}
fi
{pw_block}
install -d -m 700 -o {name} -g {name} {home}/.ssh
cat > {home}/.ssh/authorized_keys <<'__KS_GEN_EOF__'
{keys}
__KS_GEN_EOF__
chmod 600 {home}/.ssh/authorized_keys
chown {name}:{name} {home}/.ssh/authorized_keys
restorecon -R {home}/.ssh

# Sudoers
cat > /etc/sudoers.d/00-ks-gen-admin <<'__KS_GEN_EOF__'
{sudo_line}
__KS_GEN_EOF__
chmod 440 /etc/sudoers.d/00-ks-gen-admin
visudo -cf /etc/sudoers.d/00-ks-gen-admin
"""


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return None


RULE: Rule = cast(Rule, _Rule())
