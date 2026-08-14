"""Tests for the alma8 crypto_policy divergent implementation.

alma8 is the first rule (per #127 PR B) where the alma8 implementation
diverges from the alma9 re-export. See
src/ks_gen/rules/alma8/crypto_policy.py for the rationale.

Re-derived for #90 against ssg-almalinux8 0.1.81: the AL8 stig profile moved
onto the STIG sub-policy and dropped nearly every FIPS-only rule it used to
select. alma8 is now down to one disabled ID, fips_crypto_subpolicy, which is
a strict subset of alma9's six — the divergence is one-way again, and the
rules alma8 used to add (sshd_use_approved_kex_ordered_stig,
enable_dracut_fips_module) would be inert here now (#61).
"""

from __future__ import annotations

from ks_gen.config import Crypto, CryptoPolicy
from ks_gen.rules.alma8.crypto_policy import RULE

_PREFIX = "xccdf_org.ssgproject.content_rule_"


def test_alma8_diverges_from_alma9_re_export():
    # Confirms the divergence: alma8's RULE singleton is NOT the alma9 one.
    # The registry-level test in tests/test_registry.py pins this generically;
    # this is the per-rule callout.
    from ks_gen.rules.alma9.crypto_policy import RULE as ALMA9_RULE

    assert RULE is not ALMA9_RULE


def test_alma8_modern_tailoring_is_the_one_rule_al8_still_selects(minimal_cfg):
    cfg = minimal_cfg.model_copy(update={"distro": "alma8"})
    disabled = {o.rule_id for o in RULE.emit_tailoring(cfg) if o.action == "disable"}
    assert disabled == {f"{_PREFIX}fips_crypto_subpolicy"}


def test_alma8_disable_set_is_a_strict_subset_of_alma9s(minimal_cfg):
    """ssg 0.1.81 left AL8 selecting far fewer FIPS-only rules than AL9 (#90)."""
    from ks_gen.rules.alma9.crypto_policy import RULE as ALMA9_RULE

    cfg = minimal_cfg.model_copy(update={"distro": "alma8"})
    disabled = {o.rule_id for o in RULE.emit_tailoring(cfg) if o.action == "disable"}
    alma9_disabled = {
        o.rule_id for o in ALMA9_RULE.emit_tailoring(minimal_cfg) if o.action == "disable"
    }
    assert disabled < alma9_disabled


def test_alma8_no_longer_disables_the_rules_0_1_81_stopped_selecting(minimal_cfg):
    """Disabling an unselected rule is inert and misreports in exceptions.md (#61)."""
    cfg = minimal_cfg.model_copy(update={"distro": "alma8"})
    disabled = {o.rule_id for o in RULE.emit_tailoring(cfg) if o.action == "disable"}
    for short in (
        "enable_fips_mode",
        "enable_dracut_fips_module",
        "sysctl_crypto_fips_enabled",
        "sshd_use_approved_kex_ordered_stig",
        "harden_sshd_ciphers_openssh_conf_crypto_policy",
        "harden_sshd_ciphers_opensshserver_conf_crypto_policy",
        "harden_sshd_macs_openssh_conf_crypto_policy",
        "harden_sshd_macs_opensshserver_conf_crypto_policy",
    ):
        assert f"{_PREFIX}{short}" not in disabled


def test_alma8_stig_policy_emits_no_tailoring(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={"distro": "alma8", "crypto": Crypto(policy=CryptoPolicy.STIG)}
    )
    assert RULE.emit_tailoring(cfg) == []


def test_alma8_exception_entry_lists_every_disabled_id_when_not_stig(minimal_cfg):
    cfg = minimal_cfg.model_copy(update={"distro": "alma8"})
    entry = RULE.exception_entry(cfg)
    assert entry is not None
    assert "MODERN" in entry.summary
    # exceptions.md must name exactly what the tailoring suppresses.
    disabled = {o.rule_id for o in RULE.emit_tailoring(cfg) if o.action == "disable"}
    assert set(entry.stig_rules_disabled) == disabled


def test_alma8_exception_entry_returns_none_when_stig(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={"distro": "alma8", "crypto": Crypto(policy=CryptoPolicy.STIG)}
    )
    assert RULE.exception_entry(cfg) is None


def test_alma8_emit_post_reuses_alma9_helper(minimal_cfg):
    # alma8 reuses alma9's _emit_post helper — the bash invocation is
    # identical (update-crypto-policies shipped in RHEL 8.0). Sanity check
    # that the alma8 rule produces the same %post output as alma9 does.
    from ks_gen.rules.alma9.crypto_policy import RULE as ALMA9_RULE

    cfg_al8 = minimal_cfg.model_copy(update={"distro": "alma8"})
    cfg_al9 = minimal_cfg
    assert RULE.emit_post(cfg_al8) == ALMA9_RULE.emit_post(cfg_al9)


def test_alma8_emit_packages_is_empty(minimal_cfg):
    cfg = minimal_cfg.model_copy(update={"distro": "alma8"})
    assert RULE.emit_packages(cfg) == []
