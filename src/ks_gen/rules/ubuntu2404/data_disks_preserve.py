"""ubuntu2404 data_disks_preserve rule.

Direct port of the alma9 rule. Writes one /etc/fstab line per data
disk with wipe=False (resolved via partition / partition_uuid /
partition_label), creates the mount points, and runs `mount -a`.

The only difference vs. alma9 is the dropped trailing
`restorecon -R <mounts>` line: SELinux file labels have no Ubuntu
analog. AppArmor confines processes (not files) and has no
per-path relabel operation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import data_disks_preserve as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import DataDisk, HostConfig


def _fstab_spec(d: DataDisk) -> str:
    if d.partition is not None:
        # Validator restricts partition= to disk/by-id/... or disk/by-path/...
        # targets, so prepending /dev/ produces a real path in both cases.
        return f"/dev/{d.target}-part{d.partition}"
    if d.partition_uuid is not None:
        return f"UUID={d.partition_uuid}"
    if d.partition_label is not None:
        return f"LABEL={d.partition_label}"
    raise AssertionError("DataDisk validator guarantees one identifier when wipe=False")


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return any(not d.wipe for d in cfg.disk.data_disks)

    def emit_post(self, cfg: HostConfig) -> str:
        preserved = [d for d in cfg.disk.data_disks if not d.wipe]
        lines: list[str] = []
        for d in preserved:
            spec = _fstab_spec(d)
            opts = d.fsoptions or "defaults"
            lines.append(f"mkdir -p {d.mount}")
            lines.append(f'echo "{spec} {d.mount} {d.fstype} {opts} 0 2" >> /etc/fstab')
        lines.append("mount -a")
        return "\n".join(lines)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return None


RULE: Rule = cast(Rule, _Rule())
