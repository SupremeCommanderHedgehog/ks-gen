from ks_gen.rules.ubuntu2404.crypto_policy import RULE


def test_ssh_block_writes_sshd_config_drop_in_at_10_prefix(ubuntu_cfg_factory):
    # Numeric prefix 10- puts this file AFTER phase 3.2's 00-ks-gen.conf,
    # so crypto wins on conflict if any future maintainer adds an overlap.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/ssh/sshd_config.d/10-ks-gen-crypto.conf" in out
