"""ubuntu2404 kernel_module_blacklist rule.

Writes /etc/modprobe.d/ks-gen-blacklist.conf with modprobe
install-trick entries (install <module> /bin/true) for each
operator-configured kernel module. Prevents the kernel from loading
disallowed/unused modules at boot or on hot-plug.

`modprobe` ships in the `kmod` package (Essential: yes on Ubuntu
Server), so no apt deps are required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import kernel_module_blacklist as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


def _emit(cfg: HostConfig) -> str:
    modules = cfg.overrides.kernel_module_blacklist.modules
    body = "\n".join(f"install {m} /bin/true" for m in modules)
    return f"""\
# Disable specific kernel modules via modprobe install-trick
cat > /etc/modprobe.d/ks-gen-blacklist.conf <<'__KS_GEN_EOF__'
{body}
__KS_GEN_EOF__
chmod 644 /etc/modprobe.d/ks-gen-blacklist.conf
"""


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return cfg.overrides.kernel_module_blacklist.enable

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        # Deferred: ssg-ubuntu2404-ds.xml kernel-module-disablement rule
        # IDs land in the audit-story PR.
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        # `modprobe` ships in `kmod` (Essential: yes on Ubuntu).
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        # Deferred: paired with emit_tailoring above; see audit-story PR.
        return None


RULE: Rule = cast(Rule, _Rule())
