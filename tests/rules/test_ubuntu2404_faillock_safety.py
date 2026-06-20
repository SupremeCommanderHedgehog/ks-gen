from ks_gen.rules.ubuntu2404.faillock_safety import RULE


def test_post_writes_faillock_conf_path(ubuntu_cfg_factory):
    # Same /etc/security/faillock.conf path as alma9 — file ships in
    # libpam-modules (essential package) so this works in the chroot.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/security/faillock.conf" in out


def test_applies_when_enabled(ubuntu_cfg_factory):
    # Default cfg.overrides.faillock.enable is True.
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_applies_short_circuits_when_disabled(ubuntu_cfg_factory):
    # When the operator sets enable=False, the rule is excluded from
    # late-commands entirely (the registry's applies() filter drops it).
    from ks_gen.config import FaillockCfg, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(faillock=FaillockCfg(enable=False))}
    )
    assert RULE.applies(cfg) is False
