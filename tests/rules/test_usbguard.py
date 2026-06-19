from ks_gen.config import Overrides, UsbguardCfg
from ks_gen.rules.alma9.usbguard import RULE


def test_disabled_tailoring_disables_oscap_rules(minimal_cfg):
    ops = RULE.emit_tailoring(minimal_cfg)
    disabled = {o.rule_id for o in ops if o.action == "disable"}
    assert any("usbguard" in r for r in disabled)


def test_enabled_tailoring_selects_oscap_rules(minimal_cfg):
    cfg = minimal_cfg.model_copy(update={"overrides": Overrides(usbguard=UsbguardCfg(enable=True))})
    ops = RULE.emit_tailoring(cfg)
    selected = {o.rule_id for o in ops if o.action == "select"}
    assert any("usbguard" in r for r in selected)


def test_exception_entry_only_when_disabled(minimal_cfg):
    assert RULE.exception_entry(minimal_cfg) is not None  # default disabled
    cfg = minimal_cfg.model_copy(update={"overrides": Overrides(usbguard=UsbguardCfg(enable=True))})
    assert RULE.exception_entry(cfg) is None
