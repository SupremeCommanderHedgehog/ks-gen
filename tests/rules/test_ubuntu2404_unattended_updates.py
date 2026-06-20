from ks_gen.rules.ubuntu2404.unattended_updates import RULE


def test_nightly_writes_20auto_upgrades_path_and_content(ubuntu_cfg_factory):
    # /etc/apt/apt.conf.d/20auto-upgrades is the canonical Debian/Ubuntu
    # file that flips periodic apt-daily logic from "off" to "on" — both
    # keys must be "1" to actually enable unattended-upgrades.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/apt/apt.conf.d/20auto-upgrades" in out
    assert 'APT::Periodic::Update-Package-Lists "1";' in out
    assert 'APT::Periodic::Unattended-Upgrade "1";' in out


def test_applies_when_enabled(ubuntu_cfg_factory):
    # Default cfg.overrides.unattended_updates.enable is True.
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_applies_short_circuits_when_disabled(ubuntu_cfg_factory):
    # When the operator sets the parent enable=False, the rule is
    # excluded from late-commands entirely.
    from ks_gen.config import Overrides, UnattendedUpdatesCfg

    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "overrides": Overrides(
                unattended_updates=UnattendedUpdatesCfg(enable=False),
            )
        }
    )
    assert RULE.applies(cfg) is False


def test_post_includes_nightly_block_by_default(ubuntu_cfg_factory):
    # The "nightly security via stock unattended-upgrades timers" header
    # is a stable marker for the nightly block.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "nightly security via stock unattended-upgrades timers" in out


def test_post_includes_monthly_block_by_default(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "monthly full update via custom ks-gen timer" in out


def test_post_includes_reboot_block_by_default(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "reboot inside maintenance window if /var/run/reboot-required exists" in out


def test_post_omits_nightly_block_when_disabled(ubuntu_cfg_factory):
    from ks_gen.config import (
        MonthlyFullCfg,
        NightlySecurityCfg,
        Overrides,
        RebootWindowCfg,
        UnattendedUpdatesCfg,
    )

    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "overrides": Overrides(
                unattended_updates=UnattendedUpdatesCfg(
                    nightly_security=NightlySecurityCfg(enable=False),
                    monthly_full=MonthlyFullCfg(),
                    reboot_window=RebootWindowCfg(),
                ),
            )
        }
    )
    out = RULE.emit_post(cfg)
    assert "nightly security via stock unattended-upgrades timers" not in out
    # Monthly + reboot still present.
    assert "monthly full update via custom ks-gen timer" in out
    assert "reboot inside maintenance window" in out


def test_post_omits_monthly_block_when_disabled(ubuntu_cfg_factory):
    from ks_gen.config import (
        MonthlyFullCfg,
        NightlySecurityCfg,
        Overrides,
        RebootWindowCfg,
        UnattendedUpdatesCfg,
    )

    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "overrides": Overrides(
                unattended_updates=UnattendedUpdatesCfg(
                    nightly_security=NightlySecurityCfg(),
                    monthly_full=MonthlyFullCfg(enable=False),
                    reboot_window=RebootWindowCfg(),
                ),
            )
        }
    )
    out = RULE.emit_post(cfg)
    assert "monthly full update via custom ks-gen timer" not in out
    # Nightly + reboot still present.
    assert "nightly security via stock unattended-upgrades timers" in out
    assert "reboot inside maintenance window" in out


def test_post_omits_reboot_block_when_disabled(ubuntu_cfg_factory):
    from ks_gen.config import (
        MonthlyFullCfg,
        NightlySecurityCfg,
        Overrides,
        RebootWindowCfg,
        UnattendedUpdatesCfg,
    )

    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "overrides": Overrides(
                unattended_updates=UnattendedUpdatesCfg(
                    nightly_security=NightlySecurityCfg(),
                    monthly_full=MonthlyFullCfg(),
                    reboot_window=RebootWindowCfg(enable=False),
                ),
            )
        }
    )
    out = RULE.emit_post(cfg)
    assert "reboot inside maintenance window" not in out
    # Nightly + monthly still present.
    assert "nightly security via stock unattended-upgrades timers" in out
    assert "monthly full update via custom ks-gen timer" in out


def test_nightly_writes_52ks_gen_unattended_with_mail_and_reboot_off(ubuntu_cfg_factory):
    # 52ks-gen-unattended is layered over the stock 50unattended-upgrades
    # to enforce mail-off (no SMTP fanout) and reboot-off (only our
    # reboot_window block reboots). Numeric prefix 52 sorts after 50 so
    # our values win without overwriting Ubuntu's stock allowed-origins
    # list.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/apt/apt.conf.d/52ks-gen-unattended" in out
    assert 'Unattended-Upgrade::MailReport "never";' in out
    assert 'Unattended-Upgrade::Automatic-Reboot "false";' in out


def test_nightly_drops_in_apt_daily_timer_with_oncalendar(ubuntu_cfg_factory):
    # Drop-in pattern: clear OnCalendar= then set it to our value, plus
    # RandomizedDelaySec=0 to neutralize the default ~12h spread.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/systemd/system/apt-daily.timer.d/ks-gen.conf" in out
    # Default nightly_security.on_calendar = "*-*-* 02:00:00".
    assert "OnCalendar=\nOnCalendar=*-*-* 02:00:00" in out
    assert "RandomizedDelaySec=0" in out


def test_nightly_drops_in_apt_daily_upgrade_timer_with_oncalendar(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/systemd/system/apt-daily-upgrade.timer.d/ks-gen.conf" in out


def test_nightly_enables_both_timers(ubuntu_cfg_factory):
    # daemon-reload + enable both timers — apply waits for fetch via
    # the stock After=apt-daily.service on apt-daily-upgrade.service.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "systemctl daemon-reload" in out
    assert "systemctl enable apt-daily.timer apt-daily-upgrade.timer" in out


def test_nightly_reflects_on_calendar_override(ubuntu_cfg_factory):
    from ks_gen.config import (
        NightlySecurityCfg,
        Overrides,
        UnattendedUpdatesCfg,
    )

    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "overrides": Overrides(
                unattended_updates=UnattendedUpdatesCfg(
                    nightly_security=NightlySecurityCfg(on_calendar="*-*-* 04:00:00"),
                ),
            )
        }
    )
    out = RULE.emit_post(cfg)
    assert "OnCalendar=\nOnCalendar=*-*-* 04:00:00" in out
    # The default time must NOT appear anywhere.
    assert "OnCalendar=*-*-* 02:00:00" not in out
