from ks_gen.config import DodRootCaCfg, Overrides
from ks_gen.rules.dod_root_ca import RULE


def test_applies_only_when_install_false(minimal_cfg):
    assert RULE.applies(minimal_cfg)  # default False -> applies (we tailor it out)
    on = minimal_cfg.model_copy(
        update={"overrides": Overrides(dod_root_ca=DodRootCaCfg(install=True))}
    )
    assert not RULE.applies(on)


def test_tailoring_disables_dod_ca_rule(minimal_cfg):
    ops = RULE.emit_tailoring(minimal_cfg)
    assert ops
    assert all(o.action == "disable" for o in ops)
    assert any("dod" in o.rule_id.lower() for o in ops)


def test_post_is_empty(minimal_cfg):
    assert RULE.emit_post(minimal_cfg).strip() == ""


def test_exception_entry_when_disabled(minimal_cfg):
    entry = RULE.exception_entry(minimal_cfg)
    assert entry is not None
    assert "DoD" in entry.summary
