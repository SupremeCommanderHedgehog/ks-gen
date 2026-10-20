"""alma8 rngd_entropy — install and enable rngd, which SSG never does on AlmaLinux.

The stig profile pairs sshd_use_strong_rng (SSH_USE_STRONG_RNG=32 in
/etc/sysconfig/sshd: sshd reads the blocking /dev/random before it starts)
with package_rng-tools_installed + service_rngd_enabled, which keep that pool
fed. In ssg-almalinux8 the rngd rules carry a RHEL platform whose OVAL check
looks for an RPM *named* redhat-release; AlmaLinux ships almalinux-release, so
they evaluate notapplicable and oscap never remediates them. sshd_use_strong_rng
has no platform and always applies. On AL8's 4.18 kernel, a quiet host (a VM
without virtio-rng, a headless server at first boot) then starves /dev/random,
sshd times out in a restart loop, and the host is unreachable — a lockout, as
console login is locked by design (#118).

So ks-gen does what the two skipped rules would: install rng-tools and enable
rngd. That is the STIG's own intent, not a deviation, so there is no tailoring
and no exception entry. It is applied regardless of FIPS mode: the rngd rules
are also notapplicable under a FIPS kernel, but rngd is harmless there and
sshd_use_strong_rng still applies. Excluding rng-tools in packages.excluded
opts out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import rngd_entropy as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_PREFIX = "xccdf_org.ssgproject.content_rule_"
_RNGD_RULES = [
    f"{_PREFIX}package_rng-tools_installed",
    f"{_PREFIX}service_rngd_enabled",
]


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=lambda: list(_RNGD_RULES))

    def applies(self, cfg: HostConfig) -> bool:
        # An operator who excludes rng-tools has opted out; enabling a unit
        # that was never installed would abort %post under `set -e`.
        return "rng-tools" not in cfg.packages.excluded

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return (
            "# rngd: keep /dev/random fed so SSH_USE_STRONG_RNG cannot hang sshd (#118)\n"
            "systemctl enable rngd.service\n"
        )

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return ["rng-tools"]

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return None


RULE: Rule = cast(Rule, _Rule())
