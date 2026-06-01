from ks_gen.config import Crypto, CryptoPolicy
from ks_gen.rules.crypto_policy import RULE


def test_stig_emits_fips(minimal_cfg):
    cfg = minimal_cfg.model_copy(update={"crypto": Crypto(policy=CryptoPolicy.STIG)})
    out = RULE.emit_post(cfg)
    assert "update-crypto-policies --set FIPS" in out


def test_modern_emits_default_and_ed25519(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)  # default MODERN
    assert "update-crypto-policies --set DEFAULT" in out
    assert "ssh-keygen -A" in out


def test_modern_tailoring_disables_fips_and_approved_lists(minimal_cfg):
    ops = RULE.emit_tailoring(minimal_cfg)
    disabled = {o.rule_id for o in ops if o.action == "disable"}
    assert any("enable_fips_mode" in r for r in disabled)
    assert any("sshd_use_approved_ciphers" in r for r in disabled)
    assert any("sshd_use_approved_kex" in r for r in disabled)
    assert any("sshd_use_approved_macs" in r for r in disabled)


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
