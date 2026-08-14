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


_DISTROS = ("alma8", "alma9", "alma10", "ubuntu2404")


def _admin():
    return User(admin=AdminUser(name="ops", authorized_keys=_KEYS, sudo="nopasswd_yes"))


def _cfg(distro: str = "alma9", **overrides_kwargs):
    overrides_obj = Overrides(**overrides_kwargs) if overrides_kwargs else None
    base = dict(distro=distro, system=System(hostname="x.example"), user=_admin())
    if overrides_obj is not None:
        base["overrides"] = overrides_obj
    return HostConfig(**base)


def _fuzz_configs():
    """9 variants x 4 distros = 36 configs.

    Distro is part of the matrix because rule behaviour is per-distro: pinned
    to the alma9 default, these invariants never covered alma8, alma10 or
    ubuntu2404 — the distros #67 and #84 were about. No variant sets
    install.source, which is the one field a distro rejects (network is
    invalid for ubuntu2404), so every combination below validates.
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
    """The distro's provisioning text: ks.cfg for the RHEL family, autoinstall
    user-data for ubuntu2404. Bundle.__post_init__ guarantees exactly one."""
    bundle = build_bundle(cfg)
    script = bundle.ks_cfg if bundle.ks_cfg is not None else bundle.user_data
    assert script is not None, f"{cfg.distro} bundle carries neither ks_cfg nor user_data"
    return script


# Same lockout invariant, two firewalls: (open-port template, enable pattern).
_UFW = ("ufw allow {port}/tcp", r"ufw\s+enable")
_FIREWALLD = ("--add-port={port}/tcp", r"systemctl\s+(enable|start)\s+firewalld")


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


@pytest.mark.parametrize("cfg", list(_fuzz_configs()))
def test_ssh_port_opened_in_firewall_before_any_firewall_enable_command(cfg):
    script = _provisioning_script(cfg)
    open_tmpl, enable_pat = _UFW if cfg.distro == "ubuntu2404" else _FIREWALLD
    port_idx = script.find(open_tmpl.format(port=cfg.ssh.port))
    enable_idx = re.search(enable_pat, script)
    assert port_idx != -1, "ssh.port must be opened in the firewall during provisioning"
    if enable_idx:
        assert port_idx < enable_idx.start()


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
