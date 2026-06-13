from __future__ import annotations

from dataclasses import dataclass, field
from importlib.resources import files
from typing import TYPE_CHECKING, cast

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


# Loaded once at import time; embedded verbatim in every %post emission.
_SCRIPT = files("ks_gen.assets").joinpath("create-rootless-user.sh").read_text(encoding="utf-8")


@dataclass(frozen=True)
class _Rule:
    id: str = "container_host"
    summary: str = (
        "Install rootless-container helper, storage.conf, and per-user setup on /srv/containers."
    )
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return cfg.containers.enabled

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        # Task 6 fills this in. For now, return empty — rule still applies()
        # and shows up in the catalog, but the %post block is empty.
        return ""

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return [
            "podman",
            "crun",
            "slirp4netns",
            "fuse-overlayfs",
            "containers-common",
            "podman-plugins",
        ]

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return None


RULE: Rule = cast(Rule, _Rule())
