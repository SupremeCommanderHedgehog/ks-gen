"""#87: the rules verify must never suggest waiving."""

from __future__ import annotations

import pytest

from ks_gen.config import HostConfig
from ks_gen.exceptions_report import expected_failure_rule_ids, managed_rule_ids

_P = "xccdf_org.ssgproject.content_rule_"
_KEYS = ["ssh-ed25519 A a@b", "ssh-rsa B a@b"]


def _cfg(distro: str, policy: str) -> HostConfig:
    return HostConfig.model_validate(
        {
            "distro": distro,
            "system": {"hostname": "x"},
            "crypto": {"policy": policy},
            "user": {"admin": {"name": "o", "authorized_keys": _KEYS, "sudo": "nopasswd_yes"}},
        }
    )


@pytest.mark.parametrize("distro", ["alma8", "alma9", "alma10"])
def test_stig_hosts_manage_the_fips_rules(distro):
    managed = managed_rule_ids(_cfg(distro, "STIG"))
    assert managed[f"{_P}enable_fips_mode"] == "crypto_policy"
    assert managed[f"{_P}sysctl_crypto_fips_enabled"] == "crypto_policy"


@pytest.mark.parametrize("distro", ["alma8", "alma9", "alma10"])
@pytest.mark.parametrize("policy", ["STIG", "MODERN", "FUTURE"])
def test_managed_never_overlaps_expected_failures(distro, policy):
    """A rule ks-gen tailors out is an expected failure, not an enforced one."""
    cfg = _cfg(distro, policy)
    assert not set(managed_rule_ids(cfg)) & expected_failure_rule_ids(cfg)


def test_waived_fips_rules_are_not_managed():
    assert f"{_P}enable_fips_mode" not in managed_rule_ids(_cfg("alma9", "MODERN"))


def test_declared_exception_unmanages_its_rules():
    data = _cfg("alma9", "STIG").model_dump(exclude={"meta", "install"})
    data["exceptions"] = [
        {"id": "x", "reason": "r", "stig_rules_disabled": [f"{_P}enable_fips_mode"]}
    ]
    assert f"{_P}enable_fips_mode" not in managed_rule_ids(HostConfig.model_validate(data))


@pytest.mark.parametrize("distro", ["alma8", "alma9", "alma10"])
@pytest.mark.parametrize("policy", ["STIG", "MODERN", "FUTURE"])
def test_nothing_ks_gen_tailors_out_counts_as_managed(distro, policy):
    """managed_rule_ids trusts exception_entry to name every id a rule
    disables. If a rule disabled an id without declaring it, verify would
    refuse to suggest waiving a rule ks-gen itself chose to waive."""
    from ks_gen.registry import load_rules

    cfg = _cfg(distro, policy)
    disabled = {
        op.rule_id
        for r in load_rules(distro)
        if r.applies(cfg)
        for op in r.emit_tailoring(cfg)
        if op.action == "disable"
    }
    assert not set(managed_rule_ids(cfg)) & disabled
