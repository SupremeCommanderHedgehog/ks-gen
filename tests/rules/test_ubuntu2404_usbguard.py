from ks_gen.rules.ubuntu2404.usbguard import RULE


def test_applies_always_returns_true(ubuntu_cfg_factory):
    # Mirrors alma9 unconditional applies. The meaningful
    # enable/disable distinction lives in deferred methods.
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_emit_post_returns_empty(ubuntu_cfg_factory):
    # Empty body — writer's `if body:` guard skips this rule for
    # late-commands. The rule still increments Applied-rules count.
    assert RULE.emit_post(ubuntu_cfg_factory()) == ""


def test_emit_packages_returns_empty(ubuntu_cfg_factory):
    # Deferred: usbguard package install lands when the audit-story
    # PR wires up the enable=True branch.
    assert RULE.emit_packages(ubuntu_cfg_factory()) == []


def test_emit_tailoring_returns_empty_deferred(ubuntu_cfg_factory):
    # Deferred: ssg-ubuntu2404-ds.xml usbguard rule IDs land in
    # the audit-story PR.
    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []


def test_exception_entry_returns_none_deferred(ubuntu_cfg_factory):
    # Deferred: paired with emit_tailoring above.
    assert RULE.exception_entry(ubuntu_cfg_factory()) is None


def test_id_and_summary_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules._meta import usbguard as meta

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY
    # Mirrors meta's empty DEPENDS_ON.
    assert RULE.depends_on == []
