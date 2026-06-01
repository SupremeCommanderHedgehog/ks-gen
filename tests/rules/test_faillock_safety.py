from ks_gen.rules.faillock_safety import RULE


def test_applies_when_enabled(minimal_cfg):
    assert RULE.applies(minimal_cfg)


def test_disabled_short_circuits(minimal_cfg):
    from ks_gen.config import FaillockCfg, Overrides

    cfg = minimal_cfg.model_copy(
        update={"overrides": Overrides(faillock=FaillockCfg(enable=False))}
    )
    assert not RULE.applies(cfg)


def test_tailoring_sets_unlock_time(minimal_cfg):
    ops = RULE.emit_tailoring(minimal_cfg)
    assert any(
        o.action == "set_value"
        and o.rule_id.endswith("var_accounts_passwords_pam_faillock_unlock_time")
        and o.value == "900"
        for o in ops
    )


def test_tailoring_disables_even_deny_root_when_false(minimal_cfg):
    ops = RULE.emit_tailoring(minimal_cfg)
    disabled = {o.rule_id for o in ops if o.action == "disable"}
    assert any("even_deny_root" in r for r in disabled)


def test_post_reasserts_unlock_time(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "unlock_time = 900" in out
    assert "/etc/security/faillock.conf" in out


def test_exception_entry_named_when_disabling_even_deny_root(minimal_cfg):
    entry = RULE.exception_entry(minimal_cfg)
    assert entry is not None
    assert "even_deny_root" in " ".join(entry.stig_rules_disabled)


def test_no_exception_when_strict(minimal_cfg):
    from ks_gen.config import FaillockCfg, Overrides

    cfg = minimal_cfg.model_copy(
        update={
            "overrides": Overrides(
                faillock=FaillockCfg(enable=True, unlock_time=0, even_deny_root=True)
            )
        }
    )
    assert RULE.exception_entry(cfg) is None
