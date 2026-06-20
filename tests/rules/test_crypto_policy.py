from ks_gen.config import Crypto, CryptoPolicy
from ks_gen.rules.alma9.crypto_policy import RULE


def test_stig_emits_fips(minimal_cfg):
    cfg = minimal_cfg.model_copy(update={"crypto": Crypto(policy=CryptoPolicy.STIG)})
    out = RULE.emit_post(cfg)
    assert "update-crypto-policies --set FIPS" in out


def test_modern_emits_default_and_ed25519(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)  # default MODERN
    assert "update-crypto-policies --set DEFAULT" in out
    assert "ssh-keygen -A" in out


def test_modern_tailoring_disables_fips_and_approved_ciphers(minimal_cfg):
    # Per #127 PR B SSG-drift sweep: alma9's current ssg datastream (0.1.80)
    # has only 2 of the original 5 cipher-related checks our policy override
    # moots. The other 3 (sshd_use_approved_kex, _macs, _mac_ordered) were
    # removed upstream. alma8 has an extra real implementation that adds
    # back _kex_ordered_stig + _macs which alma8 SSG still ships.
    ops = RULE.emit_tailoring(minimal_cfg)
    disabled = {o.rule_id for o in ops if o.action == "disable"}
    assert disabled == {
        "xccdf_org.ssgproject.content_rule_enable_fips_mode",
        "xccdf_org.ssgproject.content_rule_sshd_use_approved_ciphers",
    }


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
