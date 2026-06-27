from ks_gen.rules.ubuntu2404.dod_root_ca import RULE


def test_applies_when_install_is_false(ubuntu_cfg_factory):
    # Default DodRootCaCfg.install is False → applies returns True
    # (the rule "fires" when NOT installing DoD CA, mirroring alma9).
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_applies_short_circuits_when_install_is_true(ubuntu_cfg_factory):
    # When the operator opts INTO installing the DoD bundle, the rule
    # no longer needs to mark the SSG check disabled — so applies=False.
    from ks_gen.config import DodRootCaCfg, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "overrides": Overrides(
                dod_root_ca=DodRootCaCfg(install=True),
            )
        }
    )
    assert RULE.applies(cfg) is False


def test_emit_post_returns_empty(ubuntu_cfg_factory):
    # Empty body — writer's `if body:` guard skips this rule for
    # late-commands. The rule still increments Applied-rules count.
    # (Mirrors alma9 — the install-the-bundle branch was never
    # implemented in either distro.)
    assert RULE.emit_post(ubuntu_cfg_factory()) == ""


def test_emit_packages_returns_empty(ubuntu_cfg_factory):
    assert RULE.emit_packages(ubuntu_cfg_factory()) == []


def test_emit_tailoring_returns_empty_no_ubuntu_dod_ca_rule(ubuntu_cfg_factory):
    # Phase 1 audit confirmed ssg-ubuntu2404-ds.xml has no
    # install_DoD_intermediate_certificates equivalent. The closest hits
    # (only_allow_dod_certs, install_smartcard_packages) check different
    # things. Nothing to disable; the exception_entry below still records
    # the operator's opt-out for the audit trail.
    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []


def test_exception_entry_populated_on_default(ubuntu_cfg_factory):
    # Default cfg has dod_root_ca.install=False, so applies() is True and
    # the exception_entry returns a populated record.
    from ks_gen.rules._meta import dod_root_ca as meta_mod

    entry = RULE.exception_entry(ubuntu_cfg_factory())
    assert entry is not None
    assert entry.rule_id == meta_mod.ID
    assert entry.summary == meta_mod.EXCEPTION_SUMMARY
    assert entry.reason == meta_mod.EXCEPTION_REASON
    # stig_rules_disabled empty: no Ubuntu DoD-CA SSG rule exists.
    assert entry.stig_rules_disabled == []


def test_id_and_summary_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules._meta import dod_root_ca as meta

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY
    # Mirrors meta's empty DEPENDS_ON.
    assert RULE.depends_on == []
