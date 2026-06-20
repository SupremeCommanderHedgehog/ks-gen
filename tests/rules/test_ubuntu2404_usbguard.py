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


def test_emit_tailoring_returns_empty_no_ubuntu_usbguard_rules(ubuntu_cfg_factory):
    # Phase 1 audit confirmed ssg-ubuntu2404-ds.xml has NO usbguard rules
    # — `grep usbguard docs/audit-story/ubuntu2404-rule-ids.txt` is empty.
    # Nothing to select/disable. The exception_entry still applies (audit
    # trail records the operator opt-out) but tailoring stays empty.
    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []


def test_exception_entry_returns_entry_when_disabled(ubuntu_cfg_factory):
    # Default cfg has usbguard.enable=False, so the exception_entry returns
    # a populated record — audit trail captures the opt-out even though
    # there's no Ubuntu SSG rule to record as "disabled".
    from ks_gen.rules._meta import usbguard as meta_mod

    entry = RULE.exception_entry(ubuntu_cfg_factory())
    assert entry is not None
    assert entry.rule_id == meta_mod.ID
    assert entry.summary == meta_mod.EXCEPTION_SUMMARY
    assert entry.reason == meta_mod.EXCEPTION_REASON
    # stig_rules_disabled empty: no Ubuntu usbguard SSG rules exist.
    assert entry.stig_rules_disabled == []


def test_exception_entry_returns_none_when_enabled(ubuntu_cfg_factory):
    from ks_gen.config import Overrides, UsbguardCfg

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(usbguard=UsbguardCfg(enable=True))}
    )
    assert RULE.exception_entry(cfg) is None


def test_id_and_summary_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules._meta import usbguard as meta

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY
    # Mirrors meta's empty DEPENDS_ON.
    assert RULE.depends_on == []
