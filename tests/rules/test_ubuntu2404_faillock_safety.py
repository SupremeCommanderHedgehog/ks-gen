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


def test_post_writes_pam_configs_profile_at_ks_gen_faillock(ubuntu_cfg_factory):
    # The "ks-gen-" prefix is unique so the profile name doesn't collide
    # with any future Debian-shipped pam-faillock profile.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/usr/share/pam-configs/ks-gen-faillock" in out


def test_post_profile_contains_preauth_and_authfail_lines(ubuntu_cfg_factory):
    # preauth runs before pam_unix (counts failures), authfail runs
    # after a failure to record it. Both required for pam_faillock to
    # be functional.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "pam_faillock.so preauth" in out
    assert "pam_faillock.so authfail" in out


def test_post_profile_contains_account_required_line(ubuntu_cfg_factory):
    # Account: required pam_faillock.so — runs on every account check
    # and zeroes the counter on success. Without this, the counter
    # would only grow.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "Account-Type: Primary" in out
    assert "required" in out
    assert "pam_faillock.so" in out


def test_post_enables_profile_via_pam_auth_update(ubuntu_cfg_factory):
    # --enable activates the profile we just wrote.
    # --package tells pam-auth-update this is a package-managed,
    # non-interactive run -> survives libpam-runtime upgrades that
    # regenerate the common-* files.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "pam-auth-update --enable ks-gen-faillock --package" in out


def test_post_uses_debian_frontend_noninteractive(ubuntu_cfg_factory):
    # No TTY in late-commands, so any prompt would hang the install.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "DEBIAN_FRONTEND=noninteractive pam-auth-update" in out


def test_emit_packages_returns_empty(ubuntu_cfg_factory):
    # pam_faillock.so ships in libpam-modules, pam-auth-update in
    # libpam-runtime — both Essential: yes. No apt deps.
    assert RULE.emit_packages(ubuntu_cfg_factory()) == []


def test_emit_tailoring_sets_unlock_time_and_deny_vars(ubuntu_cfg_factory):
    # The SSG variables (xccdf:Value) for unlock_time + deny exist verbatim
    # on ubuntu2404 — phase 1 audit confirmed. The alma9-disabled
    # even_deny_root rule does NOT exist on ubuntu, so we just emit the
    # two set_value ops.
    ops = RULE.emit_tailoring(ubuntu_cfg_factory())  # default unlock_time=900, deny=3
    assert len(ops) == 2
    by_id = {op.rule_id: op for op in ops}
    unlock = by_id[
        "xccdf_org.ssgproject.content_value_var_accounts_passwords_pam_faillock_unlock_time"
    ]
    deny = by_id["xccdf_org.ssgproject.content_value_var_accounts_passwords_pam_faillock_deny"]
    assert unlock.action == "set_value"
    assert unlock.value == "900"
    assert deny.action == "set_value"
    assert deny.value == "3"


def test_emit_tailoring_reflects_cfg_overrides(ubuntu_cfg_factory):
    from ks_gen.config import FaillockCfg, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(faillock=FaillockCfg(unlock_time=600, deny=5))}
    )
    ops = RULE.emit_tailoring(cfg)
    by_id = {op.rule_id: op.value for op in ops}
    assert (
        by_id["xccdf_org.ssgproject.content_value_var_accounts_passwords_pam_faillock_unlock_time"]
        == "600"
    )
    assert (
        by_id["xccdf_org.ssgproject.content_value_var_accounts_passwords_pam_faillock_deny"] == "5"
    )


def test_exception_entry_populated_on_default(ubuntu_cfg_factory):
    # Default cfg (unlock_time=900, even_deny_root=False) doesn't match
    # the strict-STIG (unlock_time=0, even_deny_root=True) so the
    # exception_entry returns a populated record.
    entry = RULE.exception_entry(ubuntu_cfg_factory())
    assert entry is not None
    assert "unlock_time=900" in entry.summary
    assert "even_deny_root=False" in entry.summary
    # stig_rules_disabled is empty: no even_deny_root rule on ubuntu2404.
    assert entry.stig_rules_disabled == []


def test_exception_entry_returns_none_for_strict_stig(ubuntu_cfg_factory):
    from ks_gen.config import FaillockCfg, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(faillock=FaillockCfg(unlock_time=0, even_deny_root=True))}
    )
    assert RULE.exception_entry(cfg) is None


def test_depends_on_is_empty(ubuntu_cfg_factory):
    # Mirrors meta's empty DEPENDS_ON.
    assert RULE.depends_on == []


def test_id_and_summary_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules._meta import faillock_safety as meta

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY
