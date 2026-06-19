from ks_gen.rules.ubuntu2404.crypto_policy import RULE


def test_ssh_block_writes_sshd_config_drop_in_at_10_prefix(ubuntu_cfg_factory):
    # Numeric prefix 10- puts this file AFTER phase 3.2's 00-ks-gen.conf,
    # so crypto wins on conflict if any future maintainer adds an overlap.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/ssh/sshd_config.d/10-ks-gen-crypto.conf" in out


def test_openssl_block_writes_under_openssl_cnf_d(ubuntu_cfg_factory):
    # Ubuntu 24.04's /etc/ssl/openssl.cnf .include's openssl.cnf.d/*.cnf,
    # so dropping a file here applies system-wide without editing the
    # main config.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/ssl/openssl.cnf.d/10-ks-gen.conf" in out


def test_gnutls_block_writes_default_priorities(ubuntu_cfg_factory):
    # Debian/Ubuntu convention for system-wide GnuTLS priority.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/gnutls/default-priorities" in out
