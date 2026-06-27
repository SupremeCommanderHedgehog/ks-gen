from ks_gen.rules.ubuntu2404.banner_text import RULE


def test_post_writes_issue_files(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/issue" in out
    assert "/etc/issue.net" in out


def test_post_writes_sshd_banner_not_motd(ubuntu_cfg_factory):
    # On ubuntu the motd is dynamic; the canonical SSH banner channel is
    # /etc/ssh/sshd-banner. Spec 2026-06-18 §6 locks this divergence from
    # alma9 (which writes /etc/motd).
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/ssh/sshd-banner" in out
    assert "/etc/motd" not in out


def test_post_writes_default_civilian_banner_text(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "private computer system" in out


def test_post_does_not_contain_dod_text(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "U.S. Government" not in out
    assert "USG" not in out


def test_applies_always_true(ubuntu_cfg_factory):
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_emit_tailoring_disables_six_ubuntu_banner_rules(ubuntu_cfg_factory):
    # ssg-ubuntu2404-ds.xml splits banner checks into CIS + non-CIS variants.
    # Our civilian banner moots all six. sshd_enable_warning_banner_net is
    # intentionally NOT disabled — ssh_config_apply's sshd drop-in enables
    # the Banner directive, so that check is satisfied.
    ops = RULE.emit_tailoring(ubuntu_cfg_factory())
    expected_rule_ids = {
        "xccdf_org.ssgproject.content_rule_banner_etc_issue_cis",
        "xccdf_org.ssgproject.content_rule_banner_etc_issue_net",
        "xccdf_org.ssgproject.content_rule_banner_etc_issue_net_cis",
        "xccdf_org.ssgproject.content_rule_banner_etc_motd_cis",
        "xccdf_org.ssgproject.content_rule_dconf_gnome_banner_enabled",
        "xccdf_org.ssgproject.content_rule_dconf_gnome_login_banner_text",
    }
    assert {op.rule_id for op in ops} == expected_rule_ids
    assert all(op.action == "disable" for op in ops)


def test_exception_entry_carries_meta_summary_and_reason(ubuntu_cfg_factory):
    from ks_gen.rules._meta import banner_text as meta_mod

    entry = RULE.exception_entry(ubuntu_cfg_factory())
    assert entry is not None
    assert entry.rule_id == meta_mod.ID
    assert entry.summary == meta_mod.EXCEPTION_SUMMARY
    assert entry.reason == meta_mod.EXCEPTION_REASON
    # All six tailored rule IDs reproduced in the exception entry's audit list.
    assert len(entry.stig_rules_disabled) == 6


def test_emit_packages_is_empty(ubuntu_cfg_factory):
    # Banner files are written with coreutils (cat, chmod) which subiquity
    # pre-installs. No apt deps.
    assert RULE.emit_packages(ubuntu_cfg_factory()) == []


def test_id_and_summary_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules._meta import banner_text as meta

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY


def test_gdm_target_is_skipped(ubuntu_cfg_factory):
    # cfg.banner.apply_to defaults include "gdm"; ubuntu Server has no GDM
    # so this target must be a no-op (no path appears in the output).
    out = RULE.emit_post(ubuntu_cfg_factory())
    # No gdm-related path appears.
    assert "gdm" not in out
    assert "/etc/dconf" not in out
