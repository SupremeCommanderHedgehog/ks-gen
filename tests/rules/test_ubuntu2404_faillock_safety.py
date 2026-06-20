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


def test_post_reasserts_unlock_time_from_cfg(ubuntu_cfg_factory):
    # Default unlock_time is 900 (FaillockCfg in src/ks_gen/config.py).
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "unlock_time = 900" in out


def test_post_reasserts_deny_from_cfg(ubuntu_cfg_factory):
    # Default deny is 3.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "deny = 3" in out


def test_post_comments_out_even_deny_root_with_no_marker(ubuntu_cfg_factory):
    # Default even_deny_root=False -> the line is commented out with a
    # trailing "no" marker so an auditor reads the cfg intent.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "# even_deny_root removed by ks-gen: no" in out


def test_post_comments_out_even_deny_root_with_yes_marker(ubuntu_cfg_factory):
    # When operator opts into even_deny_root=True, the directive is STILL
    # commented out (we never assert it positively), but the marker
    # reflects the cfg.
    from ks_gen.config import FaillockCfg, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(faillock=FaillockCfg(even_deny_root=True))}
    )
    out = RULE.emit_post(cfg)
    assert "# even_deny_root removed by ks-gen: yes" in out


def test_post_reflects_unlock_time_override(ubuntu_cfg_factory):
    from ks_gen.config import FaillockCfg, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(faillock=FaillockCfg(unlock_time=300))}
    )
    out = RULE.emit_post(cfg)
    assert "unlock_time = 300" in out
    assert "unlock_time = 900" not in out


def test_post_reflects_deny_override(ubuntu_cfg_factory):
    from ks_gen.config import FaillockCfg, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(faillock=FaillockCfg(deny=5))}
    )
    out = RULE.emit_post(cfg)
    assert "deny = 5" in out
    assert "deny = 3" not in out
