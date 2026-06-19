from ks_gen.rules.ubuntu2404.time_servers import RULE


def test_post_writes_chrony_conf_at_ubuntu_path(ubuntu_cfg_factory):
    # Ubuntu's chrony package owns /etc/chrony/ as a directory; the
    # config file lives at /etc/chrony/chrony.conf (not /etc/chrony.conf
    # as on RHEL). Strict path assertion catches drift.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/chrony/chrony.conf" in out
    # Bare /etc/chrony.conf (no subdirectory) is the alma9 path — must
    # not appear in the ubuntu output.
    assert "/etc/chrony.conf\n" not in out
    assert "/etc/chrony.conf " not in out


def test_post_writes_server_lines_for_default_pool(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "server pool.ntp.org iburst" in out


def test_post_handles_multiple_servers(ubuntu_cfg_factory):
    from ks_gen.config import Time

    cfg = ubuntu_cfg_factory().model_copy(update={"time": Time(servers=["a.example", "b.example"])})
    out = RULE.emit_post(cfg)
    assert "server a.example iburst" in out
    assert "server b.example iburst" in out


def test_post_no_dod_servers_in_output(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "usno" not in out.lower()
    assert "navy.mil" not in out.lower()


def test_post_emits_drift_logdir_rtcsync(ubuntu_cfg_factory):
    # Ubuntu's chrony package default driftfile is /var/lib/chrony/chrony.drift,
    # which is what its apparmor profile (usr.sbin.chronyd) allows. alma uses
    # /var/lib/chrony/drift (no extension) — diverges by design.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "driftfile /var/lib/chrony/chrony.drift" in out
    assert "logdir /var/log/chrony" in out
    assert "rtcsync" in out


def test_post_uses_configured_makestep_threshold(ubuntu_cfg_factory):
    from ks_gen.config import Time

    cfg = ubuntu_cfg_factory().model_copy(
        update={"time": Time(servers=["pool.ntp.org"], chrony_makestep_threshold=2.5)}
    )
    out = RULE.emit_post(cfg)
    assert "makestep 2.5 3" in out


def test_post_chmod_644(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "chmod 644 /etc/chrony/chrony.conf" in out


def test_post_uses_install_dir_for_chrony_dir(ubuntu_cfg_factory):
    # Idempotent safety belt: when the late-command re-runs (rare but
    # possible during install debugging), `install -d` no-ops if the
    # directory already exists. chrony's apt postinst creates it during
    # package install, so on a fresh run this is a no-op.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "install -d -m 755 /etc/chrony" in out


def test_applies_always_true(ubuntu_cfg_factory):
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_emit_tailoring_returns_empty_deferred(ubuntu_cfg_factory):
    # Deferred until ssg-ubuntu2404-ds.xml NTP rule survey lands in the
    # audit-story PR.
    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []


def test_exception_entry_returns_none_deferred(ubuntu_cfg_factory):
    # Deferred until ssg-ubuntu2404-ds.xml NTP rule survey lands.
    assert RULE.exception_entry(ubuntu_cfg_factory()) is None


def test_emit_packages_returns_chrony(ubuntu_cfg_factory):
    # chrony is NOT in Ubuntu Server's minimal install. This rule is the
    # first ubuntu2404 rule to actually contribute a package to
    # autoinstall.packages via the rule_packages plumbing from PR #99.
    assert RULE.emit_packages(ubuntu_cfg_factory()) == ["chrony"]


def test_depends_on_is_empty(ubuntu_cfg_factory):
    # Mirrors meta's empty DEPENDS_ON.
    assert RULE.depends_on == []


def test_id_and_summary_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules._meta import time_servers as meta

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY
