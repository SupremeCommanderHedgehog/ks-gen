from ks_gen.config import Overrides, UnattendedUpdatesCfg
from ks_gen.rules.unattended_updates import RULE


def test_rule_metadata():
    assert RULE.id == "unattended_updates"
    assert RULE.depends_on == []
    assert RULE.stig_rules_affected == []
    assert "dnf-automatic" in RULE.summary or "unattended" in RULE.summary.lower()


def test_applies_when_enabled(minimal_cfg):
    assert RULE.applies(minimal_cfg) is True


def test_does_not_apply_when_disabled(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={"overrides": Overrides(unattended_updates=UnattendedUpdatesCfg(enable=False))}
    )
    assert RULE.applies(cfg) is False


def test_emit_tailoring_is_empty(minimal_cfg):
    assert RULE.emit_tailoring(minimal_cfg) == []


def test_exception_entry_is_none(minimal_cfg):
    assert RULE.exception_entry(minimal_cfg) is None
