"""alma10 container_host — diverges from alma9.

`podman-plugins` is not packaged for AlmaLinux 10 (checked against AL10
BaseOS/AppStream repodata; podman there is 5.8.x, which carries netavark
natively rather than the old CNI dnsname plugin). A name that doesn't
resolve makes anaconda abort on %packages, so the AL10 list drops it.

Everything else — the %post body, the rootless-user helper, the SELinux
handling — is reused from alma9 unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import container_host as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp
from ks_gen.rules.alma9.container_host import RULE as _ALMA9_RULE

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_PACKAGES = [
    "podman",
    "crun",
    "slirp4netns",
    "fuse-overlayfs",
    "containers-common",
    # alma9 also installs podman-plugins here — absent from AL10.
    "policycoreutils-python-utils",
]


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return cfg.containers.enabled

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return _ALMA9_RULE.emit_post(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return list(_PACKAGES)

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return None


RULE: Rule = cast(Rule, _Rule())
