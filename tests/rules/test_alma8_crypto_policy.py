"""Tests for the alma8 crypto_policy divergent implementation.

alma8 is the first rule (per #127 PR B) where the alma8 implementation
diverges from the alma9 re-export. See
src/ks_gen/rules/alma8/crypto_policy.py for the rationale: alma8 SSG
(0.1.74) has 2 sshd cipher checks (sshd_use_approved_kex_ordered_stig
and sshd_use_approved_macs) that alma9 SSG (0.1.80) dropped. alma8's
emit_tailoring disables 4 IDs total vs alma9's 2.
"""

from __future__ import annotations

from ks_gen.config import Crypto, CryptoPolicy
from ks_gen.rules.alma8.crypto_policy import RULE


def test_alma8_diverges_from_alma9_re_export():
    # Confirms the divergence: alma8's RULE singleton is NOT the alma9 one.
    # The registry-level test in tests/test_registry.py pins this generically;
    # this is the per-rule callout.
    from ks_gen.rules.alma9.crypto_policy import RULE as ALMA9_RULE

    assert RULE is not ALMA9_RULE


def test_alma8_modern_tailoring_disables_four_cipher_rules(minimal_cfg):
    cfg = minimal_cfg.model_copy(update={"distro": "alma8"})
    ops = RULE.emit_tailoring(cfg)
    disabled = {o.rule_id for o in ops if o.action == "disable"}
    assert disabled == {
        "xccdf_org.ssgproject.content_rule_enable_fips_mode",
        "xccdf_org.ssgproject.content_rule_sshd_use_approved_ciphers",
        # AL8-only additions (alma9 SSG dropped these):
        "xccdf_org.ssgproject.content_rule_sshd_use_approved_kex_ordered_stig",
        "xccdf_org.ssgproject.content_rule_sshd_use_approved_macs",
    }


def test_alma8_stig_policy_emits_no_tailoring(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={"distro": "alma8", "crypto": Crypto(policy=CryptoPolicy.STIG)}
    )
    assert RULE.emit_tailoring(cfg) == []


def test_alma8_exception_entry_lists_four_ids_when_not_stig(minimal_cfg):
    cfg = minimal_cfg.model_copy(update={"distro": "alma8"})
    entry = RULE.exception_entry(cfg)
    assert entry is not None
    assert "MODERN" in entry.summary
    # 4 IDs (alma9's 2 + alma8-only 2) — see test above for the full set.
    assert len(entry.stig_rules_disabled) == 4


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
