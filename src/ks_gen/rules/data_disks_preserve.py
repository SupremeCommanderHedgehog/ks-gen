from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import DataDisk, HostConfig


def _fstab_spec(d: DataDisk) -> str:
    if d.partition is not None:
        # Strip a leading "disk/by-id/" prefix if the target is already a
        # by-id path (e.g. "disk/by-id/ata-FOO") so we don't double-embed it.
        bare = d.target.removeprefix("disk/by-id/")
        return f"/dev/disk/by-id/{bare}-part{d.partition}"
    if d.partition_uuid is not None:
        return f"UUID={d.partition_uuid}"
    if d.partition_label is not None:
        return f"LABEL={d.partition_label}"
    raise AssertionError("DataDisk validator guarantees one identifier when wipe=False")


@dataclass(frozen=True)
class _Rule:
    id: str = "data_disks_preserve"
    summary: str = "Mount preserved data disks via fstab from %post."
    depends_on: list[str] = field(default_factory=list)
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
        mounts = " ".join(d.mount for d in preserved)
        lines.append(f"restorecon -R {mounts}")
        return "\n".join(lines)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return None


RULE: Rule = cast(Rule, _Rule())
