from ks_gen.rules.ubuntu2404.kernel_module_blacklist import RULE


def test_post_writes_modprobe_blacklist_conf_path(ubuntu_cfg_factory):
    # /etc/modprobe.d/ is the canonical drop-in directory on both
    # Debian-family and RHEL-family systems — modprobe reads every
    # *.conf file there at module-load time. The "ks-gen-" prefix
    # avoids collision with Debian-shipped blacklist-*.conf files.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/modprobe.d/ks-gen-blacklist.conf" in out


def test_applies_when_enabled(ubuntu_cfg_factory):
    # Default cfg.overrides.kernel_module_blacklist.enable is True.
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_applies_short_circuits_when_disabled(ubuntu_cfg_factory):
    # When the operator sets enable=False, the rule is excluded from
    # late-commands entirely (the registry's applies() filter drops it).
    from ks_gen.config import KernelModuleBlacklistCfg, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "overrides": Overrides(
                kernel_module_blacklist=KernelModuleBlacklistCfg(enable=False),
            )
        }
    )
    assert RULE.applies(cfg) is False


def test_post_chmods_blacklist_conf_644(ubuntu_cfg_factory):
    # Mirrors alma9 — modprobe reads the file world-readable. The
    # explicit chmod is defensive (Debian's umask 022 would already
    # produce 644) but keeps the rule's surface identical across distros.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "chmod 644 /etc/modprobe.d/ks-gen-blacklist.conf" in out


def test_post_uses_install_trick_with_bin_true(ubuntu_cfg_factory):
    # The install-trick (install <m> /bin/true) is strictly stronger
    # than "blacklist <m>" — modprobe itself refuses to load the
    # module instead of relying on udev to honor a blacklist hint.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "install " in out
    assert " /bin/true" in out
