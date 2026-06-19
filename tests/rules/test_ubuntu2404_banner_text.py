def test_post_writes_issue_files(ubuntu_cfg_factory):
    from ks_gen.rules.ubuntu2404.banner_text import RULE

    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/issue" in out
    assert "/etc/issue.net" in out


def test_post_writes_sshd_banner_not_motd(ubuntu_cfg_factory):
    # On ubuntu the motd is dynamic; the canonical SSH banner channel is
    # /etc/ssh/sshd-banner. Spec 2026-06-18 §6 locks this divergence from
    # alma9 (which writes /etc/motd).
    from ks_gen.rules.ubuntu2404.banner_text import RULE

    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/ssh/sshd-banner" in out
    assert "/etc/motd" not in out


def test_post_writes_default_civilian_banner_text(ubuntu_cfg_factory):
    from ks_gen.rules.ubuntu2404.banner_text import RULE

    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "private computer system" in out


def test_post_does_not_contain_dod_text(ubuntu_cfg_factory):
    from ks_gen.rules.ubuntu2404.banner_text import RULE

    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "U.S. Government" not in out
    assert "USG" not in out


def test_applies_always_true(ubuntu_cfg_factory):
    from ks_gen.rules.ubuntu2404.banner_text import RULE

    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_emit_tailoring_returns_empty_deferred(ubuntu_cfg_factory):
    # Deferred until ssg-ubuntu2404-ds.xml survey lands. Future audit-story
    # PR will populate this — when it does, this test gets updated.
    from ks_gen.rules.ubuntu2404.banner_text import RULE

    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []


def test_exception_entry_returns_none_deferred(ubuntu_cfg_factory):
    # Deferred until ssg-ubuntu2404-ds.xml survey lands.
    from ks_gen.rules.ubuntu2404.banner_text import RULE

    assert RULE.exception_entry(ubuntu_cfg_factory()) is None


def test_emit_packages_is_empty(ubuntu_cfg_factory):
    # Banner files are written with coreutils (cat, chmod) which subiquity
    # pre-installs. No apt deps.
    from ks_gen.rules.ubuntu2404.banner_text import RULE

    assert RULE.emit_packages(ubuntu_cfg_factory()) == []


def test_id_and_summary_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules.ubuntu2404.banner_text import RULE

    from ks_gen.rules._meta import banner_text as meta

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY


def test_gdm_target_is_skipped(ubuntu_cfg_factory):
    # cfg.banner.apply_to defaults include "gdm"; ubuntu Server has no GDM
    # so this target must be a no-op (no path appears in the output).
    from ks_gen.rules.ubuntu2404.banner_text import RULE

    out = RULE.emit_post(ubuntu_cfg_factory())
    # No gdm-related path appears.
    assert "gdm" not in out
    assert "/etc/dconf" not in out
