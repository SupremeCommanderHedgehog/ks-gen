from __future__ import annotations

import pytest

from ks_gen.config import Crypto, CryptoPolicy, HostConfig
from ks_gen.registry import load_rules
from ks_gen.rules.alma9.crypto_policy import RULE


def test_stig_emits_fips(minimal_cfg):
    cfg = minimal_cfg.model_copy(update={"crypto": Crypto(policy=CryptoPolicy.STIG)})
    out = RULE.emit_post(cfg)
    assert "update-crypto-policies --set FIPS" in out


def test_modern_emits_default_and_ed25519(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)  # default MODERN
    assert "update-crypto-policies --set DEFAULT" in out
    assert "ssh-keygen -A" in out


def test_modern_tailoring_disables_fips_and_the_crypto_policy_backend_rules(minimal_cfg):
    # Per #61: the set is derived from what the AL9 stig profile actually
    # selects. sshd_use_approved_ciphers exists in the datastream but is never
    # selected, so disabling it was inert; the four harden_sshd_* rules are
    # the ones that fire, and each asserts a FIPS-only algorithm list in the
    # crypto-policies back-end files that MODERN/FUTURE rewrites.
    # Per #67: the three FIPS-only rules below can never pass off FIPS either.
    ops = RULE.emit_tailoring(minimal_cfg)
    disabled = {o.rule_id for o in ops if o.action == "disable"}
    assert disabled == {
        "xccdf_org.ssgproject.content_rule_enable_fips_mode",
        "xccdf_org.ssgproject.content_rule_harden_sshd_ciphers_openssh_conf_crypto_policy",
        "xccdf_org.ssgproject.content_rule_harden_sshd_ciphers_opensshserver_conf_crypto_policy",
        "xccdf_org.ssgproject.content_rule_harden_sshd_macs_openssh_conf_crypto_policy",
        "xccdf_org.ssgproject.content_rule_harden_sshd_macs_opensshserver_conf_crypto_policy",
        "xccdf_org.ssgproject.content_rule_sysctl_crypto_fips_enabled",
        "xccdf_org.ssgproject.content_rule_enable_dracut_fips_module",
        "xccdf_org.ssgproject.content_rule_fips_crypto_subpolicy",
    }


def test_modern_tailoring_leaves_the_rules_that_pass_off_fips_enabled(minimal_cfg):
    """#67's care rule: only rules that cannot pass get disabled.

    aide_use_fips_hashes wants sha512 in aide.conf and fips_custom_stig_sub_policy
    checks a file its own remediation writes — both pass under DEFAULT, so
    disabling them would put a misleading line in exceptions.md.
    """
    disabled = {o.rule_id for o in RULE.emit_tailoring(minimal_cfg) if o.action == "disable"}
    assert "xccdf_org.ssgproject.content_rule_aide_use_fips_hashes" not in disabled
    assert "xccdf_org.ssgproject.content_rule_fips_custom_stig_sub_policy" not in disabled


def test_modern_tailoring_retunes_the_crypto_policy_variable(minimal_cfg):
    ops = RULE.emit_tailoring(minimal_cfg)
    set_values = [o for o in ops if o.action == "set_value"]
    assert len(set_values) == 1
    assert set_values[0].rule_id == ("xccdf_org.ssgproject.content_value_var_system_crypto_policy")
    assert set_values[0].value == "DEFAULT"


def test_stig_emits_no_tailoring(minimal_cfg):
    cfg = minimal_cfg.model_copy(update={"crypto": Crypto(policy=CryptoPolicy.STIG)})
    assert RULE.emit_tailoring(cfg) == []


def test_exception_entry_named_for_non_stig(minimal_cfg):
    entry = RULE.exception_entry(minimal_cfg)
    assert entry is not None
    assert "MODERN" in entry.summary


def test_no_exception_for_stig(minimal_cfg):
    cfg = minimal_cfg.model_copy(update={"crypto": Crypto(policy=CryptoPolicy.STIG)})
    assert RULE.exception_entry(cfg) is None


# ---- #84: STIG must put the kernel in FIPS mode, not just the crypto policy ----

_ALMA = ["alma8", "alma9", "alma10"]


def _post(minimal_cfg, distro: str, policy: str) -> str:
    base = minimal_cfg.model_dump(exclude={"meta", "install"})
    cfg = HostConfig.model_validate({**base, "distro": distro, "crypto": {"policy": policy}})
    rule = next(r for r in load_rules(distro) if r.id == "crypto_policy")
    return rule.emit_post(cfg)


@pytest.mark.parametrize("distro", _ALMA)
def test_stig_enables_kernel_fips(minimal_cfg, distro):
    body = _post(minimal_cfg, distro, "STIG")
    assert "fips-mode-setup --enable" in body
    assert "dracut -f --regenerate-all" in body


@pytest.mark.parametrize("distro", _ALMA)
def test_fips_enablement_precedes_the_policy_set(minimal_cfg, distro):
    """fips-mode-setup resets the policy to plain FIPS, so it must run first (#66)."""
    body = _post(minimal_cfg, distro, "STIG")
    assert body.index("fips-mode-setup --enable") < body.index("update-crypto-policies --set")


@pytest.mark.parametrize("distro", _ALMA)
def test_fips_enablement_failure_aborts_the_install(minimal_cfg, distro):
    """A silent fallback would re-create #84: a host claiming FIPS without it."""
    body = _post(minimal_cfg, distro, "STIG")
    assert "fips-mode-setup --enable || true" not in body
    assert "exit 1" in body


@pytest.mark.parametrize("distro", _ALMA)
@pytest.mark.parametrize("policy", ["MODERN", "FUTURE"])
def test_non_stig_never_touches_fips(minimal_cfg, distro, policy):
    body = _post(minimal_cfg, distro, policy)
    assert "fips-mode-setup" not in body
    assert "dracut" not in body


@pytest.mark.parametrize("distro", _ALMA)
@pytest.mark.parametrize("policy", ["STIG", "MODERN", "FUTURE"])
def test_policy_header_line_stays_first(minimal_cfg, distro, policy):
    """run.sh parses this line to learn the expected policy — keep it line 1."""
    body = _post(minimal_cfg, distro, policy)
    assert body.splitlines()[0].startswith("# Apply system-wide crypto policy:")
