from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import banner_text as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_PREFIX = "xccdf_org.ssgproject.content_rule_"
# banner_etc_issue_net dropped via #61: it exists in the AL8 and AL9
# datastreams but the stig profile selects neither, so disabling it was
# inert. AL10 doesn't ship it at all.
# dconf_gnome_login_banner_text added via #61: stig-selected on all three
# Alma distros, and its remediation writes the DoD text into the GDM login
# screen — the exact text this rule exists to replace.
_TAILORED = [
    f"{_PREFIX}banner_etc_issue",
    f"{_PREFIX}dconf_gnome_banner_enabled",
    f"{_PREFIX}dconf_gnome_login_banner_text",
]

_TARGET = {
    "issue": "/etc/issue",
    "issue_net": "/etc/issue.net",
    "motd": "/etc/motd",
}

_GDM_DB = "/etc/dconf/db/gdm.d"
_GDM_KEYFILE = f"{_GDM_DB}/01-ks-gen-banner"


def _gdm_banner_lines(text: str) -> list[str]:
    """Write the GDM greeter banner via dconf.

    Single-line value: dconf keyfile syntax has no multi-line form, so the
    banner's newlines are escaped into the string literal.
    """
    escaped = text.rstrip("\n").replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
    return [
        f"if [ -d /etc/dconf ]; then  # GDM greeter banner ({_GDM_KEYFILE})",
        f"  mkdir -p {_GDM_DB}",
        f"  cat > {_GDM_KEYFILE} <<'__KS_GEN_EOF__'",
        "[org/gnome/login-screen]",
        "banner-message-enable=true",
        f"banner-message-text='{escaped}'",
        "__KS_GEN_EOF__",
        f"  chmod 0644 {_GDM_KEYFILE}",
        "  dconf update || true",
        "fi",
    ]


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=lambda: list(_TAILORED))

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return [TailoringOp(rule_id=r, action="disable") for r in _TAILORED]

    def emit_post(self, cfg: HostConfig) -> str:
        text = cfg.banner.text.rstrip("\n") + "\n"
        lines = ["# Civilian-equivalent login banner"]
        for target in cfg.banner.apply_to:
            if target == "gdm":
                # We disable the two dconf banner rules, so oscap no longer
                # writes the GDM greeter text — we must write it ourselves or
                # a GUI host ends up with no login banner at all.
                lines.extend(_gdm_banner_lines(text))
                continue
            path = _TARGET[target]
            lines.append(f"cat > {path} <<'__KS_GEN_EOF__'")
            lines.append(text.rstrip("\n"))
            lines.append("__KS_GEN_EOF__")
            lines.append(f"chmod 644 {path}")
        return "\n".join(lines) + "\n"

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return ExceptionEntry(
            rule_id=meta.ID,
            summary=meta.EXCEPTION_SUMMARY,
            stig_rules_disabled=list(_TAILORED),
            reason=meta.EXCEPTION_REASON,
        )


RULE: Rule = cast(Rule, _Rule())
