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


def _cfg(**overrides_kwargs):
    overrides_obj = Overrides(**overrides_kwargs) if overrides_kwargs else None
    base = dict(
        system=System(hostname="x.example"),
        user=User(
            admin=AdminUser(name="ops", authorized_keys=["ssh-ed25519 A a@b"], sudo="nopasswd_yes")
        ),
    )
    if overrides_obj is not None:
        base["overrides"] = overrides_obj
    return HostConfig(**base)


def _fuzz_configs():
    yield _cfg()
    yield _cfg(usbguard=UsbguardCfg(enable=True))
    for port in (22, 2222):
        for pw in (True, False):
            yield HostConfig(
                system=System(hostname="x"),
                user=User(
                    admin=AdminUser(
                        name="ops", authorized_keys=["ssh-ed25519 A a@b"], sudo="nopasswd_yes"
                    )
                ),
                ssh=Ssh(port=port, password_authentication=pw),
            )
    for policy in CryptoPolicy:
        yield HostConfig(
            system=System(hostname="x"),
            user=User(
                admin=AdminUser(
                    name="ops", authorized_keys=["ssh-ed25519 A a@b"], sudo="nopasswd_yes"
                )
            ),
            crypto=Crypto(policy=policy),
        )


@pytest.mark.parametrize("cfg", list(_fuzz_configs()))
def test_authorized_keys_always_before_sshd_touches(cfg):
    ks = build_bundle(cfg).ks_cfg
    keys_idx = ks.find("authorized_keys")
    sshd_idx = ks.find("sshd_config.d/00-ks-gen.conf")
    assert keys_idx != -1, "authorized_keys must be written in %post"
    assert sshd_idx != -1, "sshd drop-in must be written in %post"
    assert keys_idx < sshd_idx, (
        "lockout-resistance invariant: authorized_keys must precede sshd config"
    )


@pytest.mark.parametrize("cfg", list(_fuzz_configs()))
def test_ssh_port_opened_in_firewalld_before_any_firewalld_enable_command(cfg):
    ks = build_bundle(cfg).ks_cfg
    port_idx = ks.find(f"--add-port={cfg.ssh.port}/tcp")
    enable_idx = re.search(r"systemctl\s+(enable|start)\s+firewalld", ks)
    assert port_idx != -1, "ssh.port must be added to firewalld in %post"
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
