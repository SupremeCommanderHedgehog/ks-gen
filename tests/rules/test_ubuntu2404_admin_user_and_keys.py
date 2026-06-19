from ks_gen.rules.ubuntu2404.admin_user_and_keys import RULE


def test_applies_always(ubuntu_cfg_factory):
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_id_and_summary_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules._meta import admin_user_and_keys as meta

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY


def test_emit_post_returns_empty_on_ubuntu(ubuntu_cfg_factory):
    # Ubuntu admin user creation happens via cloud-init `users:` in the
    # skeleton, not via a late-command. emit_post returns empty so the
    # writer never adds a bash payload for this rule.
    assert RULE.emit_post(ubuntu_cfg_factory()) == ""


def test_emit_tailoring_returns_empty(ubuntu_cfg_factory):
    # Tailoring deferred until ssg-ubuntu2404-ds.xml rule IDs are surveyed.
    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []


def test_emit_packages_returns_empty(ubuntu_cfg_factory):
    assert RULE.emit_packages(ubuntu_cfg_factory()) == []


def test_exception_entry_returns_none(ubuntu_cfg_factory):
    # Exceptions deferred until tailoring lands.
    assert RULE.exception_entry(ubuntu_cfg_factory()) is None
