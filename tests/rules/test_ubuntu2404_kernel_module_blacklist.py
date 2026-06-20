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


def test_post_includes_all_eight_default_modules(ubuntu_cfg_factory):
    # Default list comes from KernelModuleBlacklistCfg.modules — eight
    # filesystem/removable-media modules required disabled by the STIG
    # profile. Each must appear as a full install-trick line.
    out = RULE.emit_post(ubuntu_cfg_factory())
    for module in (
        "usb-storage",
        "cramfs",
        "freevxfs",
        "jffs2",
        "hfs",
        "hfsplus",
        "squashfs",
        "udf",
    ):
        assert f"install {module} /bin/true" in out


def test_post_reflects_modules_override_replaces_default_list(ubuntu_cfg_factory):
    # Override is a full replacement, NOT a merge — operator gets
    # exactly the modules they specified, no implicit defaults.
    from ks_gen.config import KernelModuleBlacklistCfg, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "overrides": Overrides(
                kernel_module_blacklist=KernelModuleBlacklistCfg(modules=["dccp", "rds"]),
            )
        }
    )
    out = RULE.emit_post(cfg)
    assert "install dccp /bin/true" in out
    assert "install rds /bin/true" in out
    # Default modules MUST NOT leak in.
    assert "install usb-storage /bin/true" not in out
    assert "install cramfs /bin/true" not in out


def test_post_reflects_empty_modules_override(ubuntu_cfg_factory):
    # Operator can configure modules=[] to keep the rule applied
    # (file exists, audit checks pass) but disable any specific
    # module. The heredoc still runs; just no install lines.
    from ks_gen.config import KernelModuleBlacklistCfg, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "overrides": Overrides(
                kernel_module_blacklist=KernelModuleBlacklistCfg(modules=[]),
            )
        }
    )
    out = RULE.emit_post(cfg)
    # File still created + chmod'd.
    assert "/etc/modprobe.d/ks-gen-blacklist.conf" in out
    assert "chmod 644 /etc/modprobe.d/ks-gen-blacklist.conf" in out
    # But no install-trick line lands.
    assert "install " not in out


def test_emit_packages_returns_empty(ubuntu_cfg_factory):
    # `modprobe` ships in `kmod` (Essential: yes on Ubuntu Server) —
    # always present, no apt deps required.
    assert RULE.emit_packages(ubuntu_cfg_factory()) == []


def test_emit_tailoring_returns_empty_deferred(ubuntu_cfg_factory):
    # Deferred: ssg-ubuntu2404-ds.xml kernel_module_<m>_disabled
    # rule IDs land in the audit-story PR.
    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []


def test_exception_entry_returns_none_deferred(ubuntu_cfg_factory):
    # Deferred: paired with emit_tailoring above. May remain None
    # permanently if there's no operator-facing exception story.
    assert RULE.exception_entry(ubuntu_cfg_factory()) is None


def test_depends_on_is_empty(ubuntu_cfg_factory):
    # Mirrors meta's empty DEPENDS_ON.
    assert RULE.depends_on == []


def test_id_and_summary_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules._meta import kernel_module_blacklist as meta

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY
