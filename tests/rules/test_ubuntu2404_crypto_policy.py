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


def test_ssh_stig_emits_no_chacha20_no_curve25519(ubuntu_cfg_factory):
    from ks_gen.config import Crypto, CryptoPolicy

    cfg = ubuntu_cfg_factory().model_copy(update={"crypto": Crypto(policy=CryptoPolicy.STIG)})
    out = RULE.emit_post(cfg)
    # STIG = FIPS-aligned algorithm set. chacha20 and curve25519 are
    # excluded under FIPS 140-3.
    assert "chacha20-poly1305" not in out
    assert "curve25519" not in out
    assert "ssh-ed25519" not in out
    # But STIG-approved AES-GCM / ECDH-nistp / hmac-sha2 are present:
    assert "aes256-gcm@openssh.com" in out
    assert "ecdh-sha2-nistp384" in out
    assert "hmac-sha2-512-etm@openssh.com" in out


def test_ssh_modern_emits_chacha20_and_curve25519(ubuntu_cfg_factory):
    # MODERN is the default policy. Adds chacha20-poly1305, curve25519,
    # and ssh-ed25519 to the STIG base.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "chacha20-poly1305@openssh.com" in out
    assert "curve25519-sha256" in out
    assert "ssh-ed25519" in out


def test_ssh_future_drops_sha1_and_short_macs(ubuntu_cfg_factory):
    from ks_gen.config import Crypto, CryptoPolicy

    cfg = ubuntu_cfg_factory().model_copy(update={"crypto": Crypto(policy=CryptoPolicy.FUTURE)})
    out = RULE.emit_post(cfg)
    # FUTURE keeps only the strongest MACs (ETM variants).
    assert "hmac-sha2-512-etm@openssh.com" in out
    assert "hmac-sha2-256-etm@openssh.com" in out
    # Non-ETM hmac-sha2-256 / -512 dropped.
    assert "MACs hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com\n" in out
    # ssh-rsa (without rsa-sha2-* prefix) dropped from HostKeyAlgorithms
    # — the "ssh-rsa," prefix would still appear inside "ssh-rsa-..." so
    # check the canonical form:
    assert "HostKeyAlgorithms ssh-ed25519,rsa-sha2-512" in out


def test_ssh_stig_emits_warning_banner_comment(ubuntu_cfg_factory):
    from ks_gen.config import Crypto, CryptoPolicy

    cfg = ubuntu_cfg_factory().model_copy(update={"crypto": Crypto(policy=CryptoPolicy.STIG)})
    out = RULE.emit_post(cfg)
    # The banner is unambiguous about the FIPS gap so an auditor reading
    # the generated sshd_config drop-in immediately sees that STIG mode
    # without pro_attach is algorithm-aligned, not FIPS-validated.
    assert "STIG-aligned algorithms but NOT FIPS-validated" in out
    assert "pro_attach rule" in out


def test_ssh_modern_does_not_emit_warning_banner_comment(ubuntu_cfg_factory):
    # MODERN is civilian-by-design; no FIPS claim to disclaim.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "NOT FIPS-validated" not in out


def test_ssh_non_stig_emits_ssh_keygen_a(ubuntu_cfg_factory):
    # MODERN/FUTURE may need Ed25519 host keys that wouldn't exist if
    # the host was ever in FIPS mode. Regen any missing keys.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "ssh-keygen -A" in out


def test_ssh_stig_does_not_emit_ssh_keygen_a(ubuntu_cfg_factory):
    # Under STIG/FIPS, host keys are FIPS-approved already; no regen
    # needed and ssh-keygen -A could regenerate non-FIPS keys.
    from ks_gen.config import Crypto, CryptoPolicy

    cfg = ubuntu_cfg_factory().model_copy(update={"crypto": Crypto(policy=CryptoPolicy.STIG)})
    out = RULE.emit_post(cfg)
    assert "ssh-keygen -A" not in out


def test_ssh_block_runs_sshd_t_validation(ubuntu_cfg_factory):
    # sshd -t in the late-command makes the install fail-fast if the
    # generated config is invalid — better than producing a host with
    # broken sshd that can't accept SSH.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "sshd -t" in out


def test_ssh_block_chmod_600(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "chmod 600 /etc/ssh/sshd_config.d/10-ks-gen-crypto.conf" in out


def test_openssl_stig_minproto_tlsv1_2_seclevel_2(ubuntu_cfg_factory):
    # STIG = MinProtocol TLSv1.2 + SECLEVEL=2. Identical to MODERN under
    # this rule (the spec note on OpenSSL explains why).
    from ks_gen.config import Crypto, CryptoPolicy

    cfg = ubuntu_cfg_factory().model_copy(update={"crypto": Crypto(policy=CryptoPolicy.STIG)})
    out = RULE.emit_post(cfg)
    assert "MinProtocol = TLSv1.2" in out
    assert "CipherString = DEFAULT@SECLEVEL=2" in out


def test_openssl_future_minproto_tlsv1_3_seclevel_3(ubuntu_cfg_factory):
    # FUTURE jumps to TLS 1.3 only + SECLEVEL=3 (forces 128-bit symmetric
    # and ECDH-only key agreement).
    from ks_gen.config import Crypto, CryptoPolicy

    cfg = ubuntu_cfg_factory().model_copy(update={"crypto": Crypto(policy=CryptoPolicy.FUTURE)})
    out = RULE.emit_post(cfg)
    assert "MinProtocol = TLSv1.3" in out
    assert "CipherString = DEFAULT@SECLEVEL=3" in out


def test_gnutls_stig_emits_secure128(ubuntu_cfg_factory):
    # STIG = SECURE128 (gnutls28 built-in profile for 128-bit equivalent
    # security). Identical to MODERN under this rule.
    from ks_gen.config import Crypto, CryptoPolicy

    cfg = ubuntu_cfg_factory().model_copy(update={"crypto": Crypto(policy=CryptoPolicy.STIG)})
    out = RULE.emit_post(cfg)
    # The priority appears inside the heredoc body, on its own line.
    assert "SECURE128\n" in out
    assert "SECURE256" not in out


def test_gnutls_future_emits_secure256(ubuntu_cfg_factory):
    from ks_gen.config import Crypto, CryptoPolicy

    cfg = ubuntu_cfg_factory().model_copy(update={"crypto": Crypto(policy=CryptoPolicy.FUTURE)})
    out = RULE.emit_post(cfg)
    assert "SECURE256\n" in out
