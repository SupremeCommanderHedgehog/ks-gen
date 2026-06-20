"""ubuntu2404 package_purge rule.

Runs an apt-get -y purge late-command for each package in
cfg.packages.excluded. Mirrors the alma9 dnf -y remove rule. The
trailing `|| true` squashes "unable to locate package" (exit 100)
and "already removed" (exit 1) so stale excluded entries don't
fail the install — important because the default excluded list is
RHEL-flavored (telnet-server, rsh-server, etc.) and most entries
don't exist in the Ubuntu archive.

emit_tailoring + exception_entry deferred to audit-story PR per
phase 3.x pattern (alma9 returns [] / None for both).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import package_purge as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


def _emit(cfg: HostConfig) -> str:
    pkgs = " ".join(cfg.packages.excluded)
    return (
        "# Remove disallowed packages (no-op if not installed)\n"
        f"DEBIAN_FRONTEND=noninteractive apt-get -y purge {pkgs} || true\n"
    )


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return cfg.overrides.package_purge.enable and bool(cfg.packages.excluded)

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return None


RULE: Rule = cast(Rule, _Rule())
