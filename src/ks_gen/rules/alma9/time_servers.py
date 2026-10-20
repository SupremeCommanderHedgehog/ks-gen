from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import time_servers as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp
from ks_gen.ssg_ids import RULE_PREFIX

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

# Stig-selected chronyd rules this rule satisfies. It writes chrony.conf after
# oscap remediates it, so the file must pass them itself or every host
# regresses fixed -> fail (#50). The checks are the same on every supported
# distro and media floor (SSG 0.1.72-0.1.82):
# - chronyd_or_ntpd_set_maxpoll: every server/pool/peer line carries
#   `maxpoll N`, N <= var_time_service_set_maxpoll (16 in the stig profile);
# - chronyd_client_only: `port 0` (never serve NTP);
# - chronyd_no_chronyc_network: `cmdport 0` (chronyc over the local socket only);
# - chronyd_server_directive: sources as `server` lines, never `pool`.
# AL10 also selects chrony_set_nts (`nts` on every source line): see the
# alma10 module, which passes it as `nts_rule` (#125).
_MAXPOLL_RULE = f"{RULE_PREFIX}chronyd_or_ntpd_set_maxpoll"
_CLIENT_ONLY_RULE = f"{RULE_PREFIX}chronyd_client_only"
_NO_CMDPORT_RULE = f"{RULE_PREFIX}chronyd_no_chronyc_network"
CHRONY_RULES = [
    _MAXPOLL_RULE,
    _CLIENT_ONLY_RULE,
    _NO_CMDPORT_RULE,
    f"{RULE_PREFIX}chronyd_server_directive",
]
# Not in CHRONY_RULES: SSG 0.1.82 selects it on AL8/AL9 only (AL10 and every
# media floor lack it), and stig_rules_affected must be selected everywhere
# this rule is re-exported. Its check wants /etc/systemd/system/
# chrony-wait.service with an ExecStart free of `-h`; SSG ships no bash fix
# for it, so oscap never remediates it. ks-gen writes it on every distro
# anyway: with `cmdport 0` the packaged unit's `chronyc -h 127.0.0.1,::1`
# cannot connect, and anything wanting time-sync.target would stall on it.
_LOCAL_SOCKET_RULE = f"{RULE_PREFIX}chronyd_configure_local_socket"
# The stig profile's var_time_service_set_maxpoll, as DISA's fix text writes it.
# tests/rules/test_time_servers.py pins it against every pin's refine value.
MAXPOLL = 16
# SSG's own unit for chronyd_configure_local_socket (KCS 7064388): the packaged
# one minus `-h`, so chronyc uses the local Unix socket.
_CHRONY_WAIT_UNIT = """\
[Unit]
Description=Wait for chrony to synchronize system clock (KCS 7064388)
Documentation=man:chronyc(1)
After=chronyd.service
Requires=chronyd.service
Before=time-sync.target
Wants=time-sync.target

[Service]
Type=oneshot
ExecStart=/usr/bin/chronyc waitsync 0 0.1 0.0 1
TimeoutStartSec=180
RemainAfterExit=yes
StandardOutput=null

[Install]
WantedBy=multi-user.target
"""


def _excepted(cfg: HostConfig) -> set[str]:
    """Rule ids the operator waived. Their directives are left out rather than
    enforced anyway — an exception that changes nothing would be inert."""
    return {rid for ex in cfg.exceptions for rid in ex.stig_rules_disabled}


def _emit(cfg: HostConfig) -> str:
    waived = _excepted(cfg)
    maxpoll = "" if _MAXPOLL_RULE in waived else f" maxpoll {MAXPOLL}"
    nts = " nts" if cfg.time.nts else ""
    # An NTS source with a certificate that looks expired or not yet valid is
    # unusable, and chrony won't fall back to plain NTP, so a host whose RTC is
    # far off would never get time. nocerttimecheck skips the date check for
    # the first clock update only (#125).
    nts_conf = "ntsdumpdir /var/lib/chrony\nnocerttimecheck 1\n" if cfg.time.nts else ""
    servers = "\n".join(f"server {s} iburst{maxpoll}{nts}" for s in cfg.time.servers)
    hardening = [
        line
        for rule, line in (
            (_CLIENT_ONLY_RULE, "port 0"),
            (_NO_CMDPORT_RULE, "cmdport 0"),
        )
        if rule not in waived
    ]
    stig = (
        "# STIG: client only, no chronyc over the network (#50)\n" + "\n".join(hardening) + "\n"
        if hardening
        else ""
    )
    out = f"""\
# Chrony configuration (servers from host.yaml; STIG-compliant base)
cat > /etc/chrony.conf <<'__KS_GEN_EOF__'
{servers}
driftfile /var/lib/chrony/drift
makestep {cfg.time.chrony_makestep_threshold} 3
rtcsync
logdir /var/log/chrony
{nts_conf}{stig}__KS_GEN_EOF__
chmod 644 /etc/chrony.conf
"""
    if _LOCAL_SOCKET_RULE not in waived:
        out += f"""\
# chrony-wait over the local socket, not 127.0.0.1:323 (#50, KCS 7064388)
if [ -f /usr/lib/systemd/system/chrony-wait.service ]; then
  cat > /etc/systemd/system/chrony-wait.service <<'__KS_GEN_EOF__'
{_CHRONY_WAIT_UNIT}__KS_GEN_EOF__
  chmod 644 /etc/systemd/system/chrony-wait.service
fi
"""
    return out


@dataclass(frozen=True)
class TimeServers:
    """`nts_rule`: the distro's stig NTS rule, when its profile selects one.
    With time.nts off, that rule is tailored out and declared as an exception
    rather than left failing unexplained (#125)."""

    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=lambda: list(CHRONY_RULES))
    nts_rule: str | None = None

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def _waived_nts_rule(self, cfg: HostConfig) -> str | None:
        """The NTS rule this rule tailors out and declares, or None: none when
        the distro selects no NTS rule, NTS is on, or the operator already
        declared it in cfg.exceptions (no duplicate entry)."""
        rule = self.nts_rule
        if rule is None or cfg.time.nts or rule in _excepted(cfg):
            return None
        return rule

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        rule = self._waived_nts_rule(cfg)
        return [] if rule is None else [TailoringOp(rule_id=rule, action="disable")]

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        rule = self._waived_nts_rule(cfg)
        if rule is None:
            return None
        return ExceptionEntry(
            rule_id=meta.ID,
            summary=meta.NTS_EXCEPTION_SUMMARY,
            stig_rules_disabled=[rule],
            reason=meta.NTS_EXCEPTION_REASON_FIPS if cfg.kernel_fips else meta.NTS_EXCEPTION_REASON,
        )


RULE: Rule = cast(Rule, TimeServers())
