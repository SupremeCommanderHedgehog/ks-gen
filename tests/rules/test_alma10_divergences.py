"""Tests for the three rules where alma10 diverges from the alma9 re-export.

Each divergence was established against the real
ssg-almalinux10-ds.xml (scap-security-guide 0.1.81) and AlmaLinux 10
BaseOS/AppStream repodata, not by assuming the alma9 mapping carries over:

  banner_text    banner_etc_issue_net no longer exists in AL10 SSG; the
                 surviving banner_etc_issue_net_cis is not selected by the
                 stig profile, so disabling it would be inert.
  crypto_policy  sshd_use_approved_ciphers is gone; AL10 splits the same
                 check into two harden_sshd_ciphers_* rules, both selected
                 by the stig profile.
  container_host podman-plugins is not packaged for AL10 (podman 5.x), and
                 a missing name in %packages aborts the install.
"""

from __future__ import annotations

from ks_gen.config import Containers, Crypto, CryptoPolicy
from ks_gen.rules.alma10.banner_text import RULE as BANNER
from ks_gen.rules.alma10.container_host import RULE as CONTAINER
from ks_gen.rules.alma10.crypto_policy import RULE as CRYPTO

_PREFIX = "xccdf_org.ssgproject.content_rule_"


def _al10(cfg, **update):
    return cfg.model_copy(update={"distro": "alma10", **update})


# ---------------- banner_text ----------------


def test_banner_tailoring_drops_the_issue_net_rule(minimal_cfg):
    ops = BANNER.emit_tailoring(_al10(minimal_cfg))
    assert {o.rule_id for o in ops} == {
        f"{_PREFIX}banner_etc_issue",
        f"{_PREFIX}dconf_gnome_banner_enabled",
    }


def test_banner_does_not_reference_rules_absent_from_al10(minimal_cfg):
    ops = BANNER.emit_tailoring(_al10(minimal_cfg))
    ids = {o.rule_id for o in ops}
    assert f"{_PREFIX}banner_etc_issue_net" not in ids
    # The CIS-profile variant exists in AL10 but the stig profile doesn't
    # select it, so disabling it would be a no-op.
    assert f"{_PREFIX}banner_etc_issue_net_cis" not in ids


def test_banner_post_matches_alma9(minimal_cfg):
    from ks_gen.rules.alma9.banner_text import RULE as ALMA9

    assert BANNER.emit_post(_al10(minimal_cfg)) == ALMA9.emit_post(minimal_cfg)


def test_banner_exception_entry_lists_the_two_disabled_ids(minimal_cfg):
    entry = BANNER.exception_entry(_al10(minimal_cfg))
    assert entry is not None
    assert len(entry.stig_rules_disabled) == 2


# ---------------- crypto_policy ----------------


def test_crypto_tailoring_uses_al10_cipher_rules(minimal_cfg):
    ops = CRYPTO.emit_tailoring(_al10(minimal_cfg))
    assert {o.rule_id for o in ops} == {
        f"{_PREFIX}enable_fips_mode",
        f"{_PREFIX}harden_sshd_ciphers_openssh_conf_crypto_policy",
        f"{_PREFIX}harden_sshd_ciphers_opensshserver_conf_crypto_policy",
    }


def test_crypto_drops_the_rule_al10_no_longer_ships(minimal_cfg):
    ops = CRYPTO.emit_tailoring(_al10(minimal_cfg))
    assert f"{_PREFIX}sshd_use_approved_ciphers" not in {o.rule_id for o in ops}


def test_crypto_stig_policy_emits_no_tailoring(minimal_cfg):
    cfg = _al10(minimal_cfg, crypto=Crypto(policy=CryptoPolicy.STIG))
    assert CRYPTO.emit_tailoring(cfg) == []


def test_crypto_exception_entry_returns_none_when_stig(minimal_cfg):
    cfg = _al10(minimal_cfg, crypto=Crypto(policy=CryptoPolicy.STIG))
    assert CRYPTO.exception_entry(cfg) is None


def test_crypto_post_reuses_alma9_helper(minimal_cfg):
    from ks_gen.rules.alma9.crypto_policy import RULE as ALMA9

    assert CRYPTO.emit_post(_al10(minimal_cfg)) == ALMA9.emit_post(minimal_cfg)


# ---------------- container_host ----------------


def test_container_packages_omit_podman_plugins(minimal_cfg):
    cfg = _al10(minimal_cfg, containers=Containers(enabled=True))
    assert "podman-plugins" not in CONTAINER.emit_packages(cfg)


def test_container_packages_otherwise_match_alma9(minimal_cfg):
    from ks_gen.rules.alma9.container_host import RULE as ALMA9

    cfg = _al10(minimal_cfg, containers=Containers(enabled=True))
    al9 = [p for p in ALMA9.emit_packages(cfg) if p != "podman-plugins"]
    assert CONTAINER.emit_packages(cfg) == al9


def test_container_post_matches_alma9(minimal_cfg):
    from ks_gen.rules.alma9.container_host import RULE as ALMA9

    cfg = _al10(minimal_cfg, containers=Containers(enabled=True))
    assert CONTAINER.emit_post(cfg) == ALMA9.emit_post(cfg)
