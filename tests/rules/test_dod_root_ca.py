from ks_gen.config import DodRootCaCfg, Overrides
from ks_gen.rules.alma9.dod_root_ca import RULE


def test_applies_only_when_install_false(minimal_cfg):
    assert RULE.applies(minimal_cfg)  # default False -> applies (we tailor it out)
    on = minimal_cfg.model_copy(
        update={"overrides": Overrides(dod_root_ca=DodRootCaCfg(install=True))}
    )
    assert not RULE.applies(on)


def test_tailoring_returns_empty_after_drift_cleanup(minimal_cfg):
    # Per #127 PR B SSG-drift sweep: the
    # install_DoD_intermediate_certificates rule was dropped from current
    # ssg-almalinux9-ds.xml (0.1.80). No equivalent rule to disable on
    # current AL9 SSG, so emit_tailoring returns []. The exception_entry
    # still records the operator's opt-out for the audit trail (with
    # empty stig_rules_disabled — same shape as ubuntu2404's port).
    assert RULE.emit_tailoring(minimal_cfg) == []


def test_exception_entry_records_opt_out_with_empty_disabled_list(minimal_cfg):
    # Even with no SSG rule to disable, the audit trail still records that
    # the operator opted out of installing the DoD CA bundle.
    entry = RULE.exception_entry(minimal_cfg)
    assert entry is not None
    assert entry.stig_rules_disabled == []


def test_post_is_empty(minimal_cfg):
    assert RULE.emit_post(minimal_cfg).strip() == ""


def test_exception_entry_when_disabled(minimal_cfg):
    entry = RULE.exception_entry(minimal_cfg)
    assert entry is not None
    assert "DoD" in entry.summary
