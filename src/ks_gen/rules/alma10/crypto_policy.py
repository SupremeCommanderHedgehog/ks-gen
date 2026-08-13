"""alma10 crypto_policy — diverges from alma9 in its disabled set only.

Was a re-export until #67, when the FIPS-only sweep showed the AL10 stig
profile selects a different tail than AL9: it drops
`enable_dracut_fips_module` (no dracut FIPS module rule at all in
ssg-almalinux10 0.1.81) and adds `system_booted_in_fips_mode`.

What stays shared: emit_post, emit_tailoring, exception_entry and the
`_FIPS_ONLY_COMMON` head of the disabled set, all from the alma9 module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import crypto_policy as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp
from ks_gen.rules.alma9.crypto_policy import (
    _FIPS_ONLY_COMMON,
    _emit_post,
    _emit_tailoring,
    _exception_entry,
)

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_PREFIX = "xccdf_org.ssgproject.content_rule_"
_TAILORED_WHEN_NOT_STIG = [
    *_FIPS_ONLY_COMMON,
    # Same FIPS-only pattern on /etc/crypto-policies/config as AL9 (#67).
    f"{_PREFIX}fips_crypto_subpolicy",
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
