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


def test_modern_tailoring_disables_fips_and_the_crypto_policy_backend_rules(minimal_cfg):
    # Per #61: the set is derived from what the AL9 stig profile actually
    # selects. sshd_use_approved_ciphers exists in the datastream but is never
    # selected, so disabling it was inert; the four harden_sshd_* rules are
    # the ones that fire, and each asserts a FIPS-only algorithm list in the
    # crypto-policies back-end files that MODERN/FUTURE rewrites.
    ops = RULE.emit_tailoring(minimal_cfg)
    disabled = {o.rule_id for o in ops if o.action == "disable"}
    assert disabled == {
        "xccdf_org.ssgproject.content_rule_enable_fips_mode",
        "xccdf_org.ssgproject.content_rule_harden_sshd_ciphers_openssh_conf_crypto_policy",
        "xccdf_org.ssgproject.content_rule_harden_sshd_ciphers_opensshserver_conf_crypto_policy",
        "xccdf_org.ssgproject.content_rule_harden_sshd_macs_openssh_conf_crypto_policy",
        "xccdf_org.ssgproject.content_rule_harden_sshd_macs_opensshserver_conf_crypto_policy",
    }


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
