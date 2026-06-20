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
