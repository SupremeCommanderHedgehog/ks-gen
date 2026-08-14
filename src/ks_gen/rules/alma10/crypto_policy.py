"""alma10 crypto_policy — diverges from alma9 in its disabled set only.

Was a re-export until #67, when the FIPS-only sweep showed the AL10 stig
profile selects a strict superset of AL9's FIPS-only rules: every one AL9
selects, plus `enable_fips_mode` and `system_booted_in_fips_mode`. AL9 lost
`enable_fips_mode` in ssg-almalinux9 0.1.81; AL10 0.1.81 still selects it.

What stays shared: emit_post, emit_tailoring, exception_entry and the disabled
set AL9 and AL10 have in common, all from the alma9 module. alma8's set is not
shared — 0.1.81 left it with a single ID (#90).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import crypto_policy as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp
from ks_gen.rules.alma9.crypto_policy import (
    _TAILORED_WHEN_NOT_STIG as _FIPS_ONLY_AL9,
)
from ks_gen.rules.alma9.crypto_policy import (
    _emit_post,
    _emit_tailoring,
    _exception_entry,
)

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_PREFIX = "xccdf_org.ssgproject.content_rule_"
_TAILORED_WHEN_NOT_STIG = [
    # AL10's stig profile selects every FIPS-only rule AL9's does, plus these
    # two. Checked against docs/audit-story/alma10-fips-candidates.txt.
    *_FIPS_ONLY_AL9,
    # Its remediation runs `fips-mode-setup --enable`, which would put fips=1
    # on the kernel command line of a host that opted out (#67). AL9 stopped
    # selecting this in ssg 0.1.81; AL10 0.1.81 still does.
    f"{_PREFIX}enable_fips_mode",
    # AL10-only: reads /proc/sys/crypto/fips_enabled, so it needs a fips=1 boot.
    f"{_PREFIX}system_booted_in_fips_mode",
]


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=lambda: list(_TAILORED_WHEN_NOT_STIG))

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return _emit_tailoring(cfg, _TAILORED_WHEN_NOT_STIG)

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit_post(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return _exception_entry(cfg, _TAILORED_WHEN_NOT_STIG)


RULE: Rule = cast(Rule, _Rule())
