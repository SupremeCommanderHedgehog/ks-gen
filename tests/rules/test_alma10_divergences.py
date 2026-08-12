"""alma10's divergence from the alma9 re-export, and the two that collapsed.

`container_host` is the only remaining real divergence: podman-plugins is not
packaged for AL10 (podman 5.x uses netavark), and a missing name in %packages
aborts the install.

`banner_text` and `crypto_policy` *were* divergent, because alma9 referenced
SSG rule IDs that AL10 no longer ships. #61 showed the AL9 stig profile never
selected those IDs either — they were inert on alma9 too. Dropping them from
alma9 left both distros emitting identical tailoring, so the alma10 modules
are re-exports again. The tests below pin that the shared implementation is
still correct *for AL10*, which is the property the divergence used to carry.
"""

from __future__ import annotations

from ks_gen.config import Containers, Crypto, CryptoPolicy
from ks_gen.rules.alma10.banner_text import RULE as BANNER
from ks_gen.rules.alma10.container_host import RULE as CONTAINER
from ks_gen.rules.alma10.crypto_policy import RULE as CRYPTO

_PREFIX = "xccdf_org.ssgproject.content_rule_"


def _al10(cfg, **update):
    return cfg.model_copy(update={"distro": "alma10", **update})


# ---------------- banner_text (shared with alma9 since #61) ----------------


def test_banner_tailoring_is_the_stig_selected_al10_rules(minimal_cfg):
    ops = BANNER.emit_tailoring(_al10(minimal_cfg))
    assert {o.rule_id for o in ops} == {
        f"{_PREFIX}banner_etc_issue",
        f"{_PREFIX}dconf_gnome_banner_enabled",
        # added via #61 — remediation would write DoD text to the GDM login
        # screen on a GUI host otherwise
        f"{_PREFIX}dconf_gnome_login_banner_text",
    }


def test_banner_does_not_reference_rules_absent_from_al10(minimal_cfg):
    ops = BANNER.emit_tailoring(_al10(minimal_cfg))
    ids = {o.rule_id for o in ops}
    assert f"{_PREFIX}banner_etc_issue_net" not in ids
    # The CIS-profile variant exists in AL10 but the stig profile doesn't
    # select it, so disabling it would be a no-op.
    assert f"{_PREFIX}banner_etc_issue_net_cis" not in ids


def test_banner_now_re_exports_alma9(minimal_cfg):
    from ks_gen.rules.alma9.banner_text import RULE as ALMA9

    assert BANNER is ALMA9


# ---------------- crypto_policy (shared with alma9 since #61) ----------------


def test_crypto_tailoring_uses_the_al10_cipher_and_mac_rules(minimal_cfg):
    ops = CRYPTO.emit_tailoring(_al10(minimal_cfg))
    disabled = {o.rule_id for o in ops if o.action == "disable"}
    assert disabled == {
        f"{_PREFIX}enable_fips_mode",
        f"{_PREFIX}harden_sshd_ciphers_openssh_conf_crypto_policy",
        f"{_PREFIX}harden_sshd_ciphers_opensshserver_conf_crypto_policy",
        f"{_PREFIX}harden_sshd_macs_openssh_conf_crypto_policy",
        f"{_PREFIX}harden_sshd_macs_opensshserver_conf_crypto_policy",
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


def test_crypto_now_re_exports_alma9(minimal_cfg):
    from ks_gen.rules.alma9.crypto_policy import RULE as ALMA9

    assert CRYPTO is ALMA9


# ---------------- container_host (the remaining divergence) ----------------


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
