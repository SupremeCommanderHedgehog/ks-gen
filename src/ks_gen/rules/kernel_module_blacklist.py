from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


@dataclass(frozen=True)
class _Rule:
    id: str = "kernel_module_blacklist"
    summary: str = "Write modprobe blacklist for unused/disallowed kernel modules."
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return cfg.overrides.kernel_module_blacklist.enable

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        modules = cfg.overrides.kernel_module_blacklist.modules
        body = "\n".join(f"install {m} /bin/true" for m in modules)
        return f"""\
# Disable specific kernel modules via modprobe install-trick
cat > /etc/modprobe.d/ks-gen-blacklist.conf <<'__KS_GEN_EOF__'
{body}
__KS_GEN_EOF__
chmod 644 /etc/modprobe.d/ks-gen-blacklist.conf
"""

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return None


RULE: Rule = cast(Rule, _Rule())
