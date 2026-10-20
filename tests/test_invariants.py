from __future__ import annotations

import re

import pytest

from ks_gen.config import (
    AdminUser,
    Crypto,
    CryptoPolicy,
    HostConfig,
    Overrides,
    Ssh,
    System,
    UsbguardCfg,
    User,
)
from ks_gen.writer import build_bundle

# Two types so these fixtures stay valid under every crypto.policy: STIG
# strips Ed25519 from PubkeyAcceptedAlgorithms (#73).
_KEYS = ["ssh-ed25519 A a@b", "ssh-rsa B a@b"]


_DISTROS = ("alma8", "alma9", "alma10")


def _admin():
    return User(admin=AdminUser(name="ops", authorized_keys=_KEYS, sudo="nopasswd_yes"))


def _cfg(distro: str = "alma9", **overrides_kwargs):
    overrides_obj = Overrides(**overrides_kwargs) if overrides_kwargs else None
    base = dict(distro=distro, system=System(hostname="x.example"), user=_admin())
    if overrides_obj is not None:
        base["overrides"] = overrides_obj
    return HostConfig(**base)


def _fuzz_configs():
    """9 variants x 3 distros = 27 configs.

    Distro is part of the matrix because rule behaviour is per-distro: pinned
    to the alma9 default, these invariants never covered alma8 or alma10 —
    distros #67 and #84 were about.
    """
    for distro in _DISTROS:
        yield _cfg(distro)
        yield _cfg(distro, usbguard=UsbguardCfg(enable=True))
        for port in (22, 2222):
            for pw in (True, False):
                yield HostConfig(
                    distro=distro,
                    system=System(hostname="x"),
                    user=_admin(),
                    ssh=Ssh(port=port, password_authentication=pw),
                )
        for policy in CryptoPolicy:
            yield HostConfig(
                distro=distro,
                system=System(hostname="x"),
                user=_admin(),
                crypto=Crypto(policy=policy),
            )


def _provisioning_script(cfg) -> str:
    return build_bundle(cfg).ks_cfg


@pytest.mark.parametrize("cfg", list(_fuzz_configs()))
def test_authorized_keys_always_before_sshd_touches(cfg):
    script = _provisioning_script(cfg)
    keys_idx = script.find("authorized_keys")
    sshd_idx = script.find("sshd_config.d/00-ks-gen.conf")
    assert keys_idx != -1, "authorized_keys must be written during provisioning"
    assert sshd_idx != -1, "sshd drop-in must be written during provisioning"
    assert keys_idx < sshd_idx, (
        "lockout-resistance invariant: authorized_keys must precede sshd config"
    )


def _services(script: str) -> tuple[set[str], set[str]]:
    """(enabled, disabled) across every kickstart `services` line."""
    enabled: set[str] = set()
    disabled: set[str] = set()
    for line in re.findall(r"^services\s+(.*)$", script, re.MULTILINE):
        for flag, value in re.findall(r"--(enabled|disabled)=(\S+)", line):
            names = {n for n in value.strip("\"'").split(",") if n}
            (enabled if flag == "enabled" else disabled).update(names)
    return enabled, disabled


def _firewall_lockout_violations(script: str, port: int) -> list[str]:
    """Why `script` could leave firewalld up without `port` open, or [] (#88).

    Ordering inside the kickstart is not what protects ssh: %post runs in a
    chroot where systemd is not PID 1, so nothing there can start firewalld
    (`systemctl start` is ignored, `firewall-cmd` has no daemon to reach).
    `services --enabled=firewalld` enables the unit during install and the
    daemon first starts at first boot. What matters is that the port is in
    firewalld's permanent config by then. So assert the mechanism that puts it
    there: a real `firewall-offline-cmd --add-port` line (not a comment or an
    echo), in a chrooted %post (a --nochroot one edits the installer, not the
    target), marked --erroronfail (a failed write aborts the install instead
    of shipping an unreachable host). And firewalld must actually be enabled,
    or there is nothing to assert.
    """
    open_cmd = f"firewall-offline-cmd --add-port={port}/tcp"
    m = re.search(rf"^[ \t]*{re.escape(open_cmd)}[ \t]*$", script, re.MULTILINE)
    if m is None:
        return [f"missing: a {open_cmd!r} command line"]
    open_idx = m.start()
    problems: list[str] = []
    header_start = script.rfind("\n%post", 0, open_idx)
    if header_start == -1 or script.rfind("\n%end", 0, open_idx) > header_start:
        problems.append(f"{open_cmd} is not inside a %post section")
    else:
        header_end = script.find("\n", header_start + 1)
        header = script[header_start + 1 : header_end if header_end != -1 else None]
        if "--nochroot" in header:
            problems.append(f"{open_cmd} runs in a --nochroot %post: {header!r}")
        if "--erroronfail" not in header:
            problems.append(f"{open_cmd} runs in a %post without --erroronfail: {header!r}")
    enabled, disabled = _services(script)
    if "firewalld" not in enabled or "firewalld" in disabled:
        problems.append("firewalld is not enabled via `services --enabled`")
    return problems


@pytest.mark.parametrize("cfg", list(_fuzz_configs()))
def test_ssh_port_in_firewalld_config_before_first_boot(cfg):
    """Lockout resistance: firewalld must never come up without ssh.port open."""
    script = _provisioning_script(cfg)
    assert _firewall_lockout_violations(script, cfg.ssh.port) == []


_GOOD_KS = """\
services --enabled=chronyd,firewalld,sshd
%post --erroronfail
firewall-offline-cmd --add-port=2222/tcp
%end
"""
_OPEN = "firewall-offline-cmd --add-port=2222/tcp\n"


@pytest.mark.parametrize(
    ("script", "expected"),
    [
        (_GOOD_KS, None),
        (_GOOD_KS.replace("2222", "22"), "missing:"),
        (_GOOD_KS.replace(_OPEN, "# was: " + _OPEN), "missing:"),
        (_GOOD_KS.replace(_OPEN, "echo " + _OPEN), "missing:"),
        (_GOOD_KS.replace("%post --erroronfail", "%post --nochroot --erroronfail"), "--nochroot"),
        (_GOOD_KS.replace("%post --erroronfail", "%post"), "without --erroronfail"),
        (_OPEN + _GOOD_KS.replace(_OPEN, ""), "not inside a %post"),
        (_GOOD_KS.replace(_OPEN, "") + _OPEN, "not inside a %post"),
        (_GOOD_KS.replace("firewalld,", ""), "not enabled"),
        (_GOOD_KS + "services --disabled=firewalld\n", "not enabled"),
        (_GOOD_KS.replace("=chronyd,firewalld,sshd", '="chronyd,firewalld,sshd"'), None),
        ("services --enabled=firewalld\n%post --nochroot\n" + _OPEN.rstrip("\n"), "--nochroot"),
    ],
    ids=[
        "good",
        "port-never-opened",
        "comment-only",
        "echo-only",
        "nochroot",
        "no-erroronfail",
        "before-any-post",
        "after-end",
        "not-enabled",
        "disabled-later",
        "quoted-services",
        "no-trailing-newline",
    ],
)
def test_firewall_lockout_check_fires(script, expected):
    """#88: the old ordering half was guarded by a pattern that never matched,
    so it never ran. Prove every branch of this check can fail."""
    problems = _firewall_lockout_violations(script, 2222)
    if expected is None:
        assert problems == []
    else:
        assert any(expected in p for p in problems), problems


@pytest.mark.parametrize("cfg", list(_fuzz_configs()))
def test_no_disabled_xccdf_rule_without_exception_entry(cfg):
    from ks_gen.registry import load_rules

    for r in load_rules(cfg.distro):
        if not r.applies(cfg):
            continue
        ops = r.emit_tailoring(cfg)
        disabled = [o.rule_id for o in ops if o.action == "disable"]
        if not disabled:
            continue
        entry = r.exception_entry(cfg)
        assert entry is not None, (
            f"rule {r.id} disabled XCCDF rules {disabled} without an exception_entry"
        )
        for rid in disabled:
            assert rid in entry.stig_rules_disabled, (
                f"rule {r.id} disabled {rid} but didn't name it in exception_entry"
            )
