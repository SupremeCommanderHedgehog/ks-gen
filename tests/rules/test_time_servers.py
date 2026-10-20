import re
from pathlib import Path

import pytest

from ks_gen.config import ExceptionDecl, Time
from ks_gen.rules.alma9.time_servers import _CHRONY_WAIT_UNIT, MAXPOLL, RULE

_P = "xccdf_org.ssgproject.content_rule_"
_DOCS = Path(__file__).resolve().parents[2] / "docs" / "audit-story"


def test_post_writes_chrony_conf(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "/etc/chrony.conf" in out
    assert "server pool.ntp.org iburst" in out


def test_post_handles_multiple_servers(minimal_cfg):
    cfg = minimal_cfg.model_copy(update={"time": Time(servers=["a.example", "b.example"])})
    out = RULE.emit_post(cfg)
    assert "server a.example iburst" in out
    assert "server b.example iburst" in out


def test_no_dod_servers_in_output(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "usno" not in out.lower()
    assert "navy.mil" not in out.lower()


def _chrony_conf(out: str) -> str:
    m = re.search(r"cat > /etc/chrony.conf <<'__KS_GEN_EOF__'\n(.*?)__KS_GEN_EOF__", out, re.S)
    assert m, "chrony.conf heredoc not found"
    return m.group(1)


def _with(minimal_cfg, *, waive: tuple[str, ...] = ()):
    update: dict = {"time": Time(servers=["a.example", "b.example"])}
    if waive:
        update["exceptions"] = [
            ExceptionDecl(id="w", reason="r", stig_rules_disabled=[_P + r for r in waive])
        ]
    return minimal_cfg.model_copy(update=update)


def test_chrony_conf_satisfies_the_stig_chronyd_checks(minimal_cfg):
    """#50: this file is written after oscap remediates, so it must pass the
    stig-selected chronyd checks itself. The patterns are the OVAL ones, the
    same in SSG 0.1.72 through 0.1.82 on every distro."""
    conf = _chrony_conf(RULE.emit_post(_with(minimal_cfg)))

    # chronyd_or_ntpd_set_maxpoll: every source line carries maxpoll <= 16.
    sources = re.findall(r"^(?:server|pool|peer)[\s]+[\S]+[\s]+(.*)", conf, re.MULTILINE)
    assert len(sources) == 2
    for rest in sources:
        m = re.search(r"maxpoll (\d+)", rest)
        assert m and int(m.group(1)) <= 16, rest
    # chronyd_client_only / chronyd_no_chronyc_network: every match is 0.
    for directive in ("port", "cmdport"):
        assert re.findall(rf"^\s*{directive}[\s]+(\S+)", conf, re.MULTILINE) == ["0"]
    # chronyd_server_directive: server lines, never pool ones. (Its OVAL uses
    # `^[\s]+pool`, which misses a column-0 pool line; this is stricter.)
    assert re.search(r"^\s*server\s", conf, re.MULTILINE)
    assert not re.search(r"^\s*pool\s", conf, re.MULTILINE)


def test_writes_chrony_wait_override_for_the_local_socket(minimal_cfg):
    """chronyd_configure_local_socket: SSG has no bash fix, and with cmdport 0
    the packaged unit's `chronyc -h 127.0.0.1,::1` can't connect."""
    out = RULE.emit_post(_with(minimal_cfg))
    assert "cat > /etc/systemd/system/chrony-wait.service" in out
    (execstart,) = re.findall(r"^ExecStart=(.*)$", _CHRONY_WAIT_UNIT, re.MULTILINE)
    # The OVAL state the override must match.
    assert re.match(r"^/usr/bin/chronyc\s+waitsync\s+\d+\s+[\d.]+\s+[\d.]+\s+\d+\s*$", execstart)


# What each waivable rule's hardening looks like in the emitted %post.
_DIRECTIVES = {
    "chronyd_client_only": lambda out: "port 0" in out.splitlines(),
    "chronyd_no_chronyc_network": lambda out: "cmdport 0" in out.splitlines(),
    "chronyd_or_ntpd_set_maxpoll": lambda out: "maxpoll" in out,
    "chronyd_configure_local_socket": lambda out: "chrony-wait.service" in out,
}


@pytest.mark.parametrize("waived", sorted(_DIRECTIVES))
def test_a_waived_rule_drops_only_its_directive(minimal_cfg, waived):
    """An exception must change what the host gets, or it is inert: the rule
    reads as waived while the hardening stays applied."""
    full = RULE.emit_post(_with(minimal_cfg))
    out = RULE.emit_post(_with(minimal_cfg, waive=(waived,)))
    for rule, present in _DIRECTIVES.items():
        assert present(full), rule
        assert present(out) == (rule != waived), rule


def test_maxpoll_matches_every_stig_refine_value():
    """MAXPOLL must not exceed what any supported content refines
    var_time_service_set_maxpoll to, or that rule fails on every host."""
    paths = [
        *_DOCS.glob("*-stig-refine-values.txt"),
        *_DOCS.glob("floors/*-stig-refine-values.txt"),
    ]
    found = {}
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("\t")
            if key.endswith("_value_var_time_service_set_maxpoll"):
                found[path.name] = int(value)
    assert found, "no var_time_service_set_maxpoll refine value found"
    assert all(MAXPOLL <= v for v in found.values()), found


def test_declares_the_chronyd_rules_it_satisfies():
    assert sorted(r.removeprefix(_P) for r in RULE.stig_rules_affected) == [
        "chronyd_client_only",
        "chronyd_no_chronyc_network",
        "chronyd_or_ntpd_set_maxpoll",
        "chronyd_server_directive",
    ]
