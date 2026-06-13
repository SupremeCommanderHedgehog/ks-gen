import re

import pytest
from pydantic import ValidationError

from ks_gen.config import (
    AdminUser,
    AuditdActionsCfg,
    AuditdMaxFileAction,
    AuditdSystemAction,
    Banner,
    ContainerVolume,
    Crypto,
    CryptoPolicy,
    Disk,
    DiskPreset,
    ExceptionDecl,
    HostConfig,
    Interface,
    Meta,
    MonthlyFullCfg,
    Network,
    NightlySecurityCfg,
    Overrides,
    Packages,
    PackagesPreset,
    RebootWindowCfg,
    Ssh,
    System,
    Time,
    UnattendedUpdatesCfg,
    User,
)


def test_meta_defaults():
    m = Meta()
    assert m.release == "9"
    assert m.profile == "stig"
    assert m.scap_content == "ssg-almalinux9-ds.xml"


def test_system_requires_hostname():
    with pytest.raises(ValidationError):
        System()


def test_system_defaults():
    s = System(hostname="web01.example.com")
    assert s.timezone == "UTC"
    assert s.locale == "en_US.UTF-8"
    assert s.keyboard == "us"


def test_host_config_partial_ok():
    # meta + system + user are the required fields.
    cfg = HostConfig.model_validate(
        {
            "meta": {},
            "system": {"hostname": "web01.example.com"},
            "user": {
                "admin": {
                    "name": "ops",
                    "authorized_keys": ["ssh-ed25519 A a@b"],
                    "sudo": "nopasswd_yes",
                }
            },
        }
    )
    assert cfg.system.hostname == "web01.example.com"


def test_unknown_top_level_key_rejected():
    with pytest.raises(ValidationError):
        HostConfig.model_validate(
            {
                "meta": {},
                "system": {"hostname": "x"},
                "user": {
                    "admin": {
                        "name": "ops",
                        "authorized_keys": ["ssh-ed25519 A a@b"],
                        "sudo": "nopasswd_yes",
                    }
                },
                "garbage": True,
            }
        )


def test_interface_dhcp_minimum():
    iface = Interface(device="link", bootproto="dhcp")
    assert iface.onboot is True
    assert iface.ip is None


def test_interface_static_requires_ip():
    with pytest.raises(ValidationError, match="ip is required"):
        Interface(device="enp1s0", bootproto="static")


def test_interface_static_complete():
    iface = Interface(
        device="enp1s0",
        bootproto="static",
        ip="10.0.0.10",
        netmask="255.255.255.0",
        gateway="10.0.0.1",
        nameservers=["1.1.1.1"],
    )
    assert iface.ip == "10.0.0.10"


def test_network_defaults():
    net = Network()
    assert net.interfaces[0].device == "link"
    assert net.interfaces[0].bootproto == "dhcp"
    assert net.hostname_from_dhcp is False


def test_disk_preset_default():
    d = Disk()
    assert d.preset == DiskPreset.STIG_SERVER
    assert d.layout is None
    assert d.wipe is True
    assert d.bootloader_password is None


def test_admin_user_requires_keys_when_password_is_none():
    with pytest.raises(ValidationError, match="authorized_keys"):
        AdminUser(name="opsadmin", password=None, authorized_keys=[])


def test_admin_user_with_keys_ok():
    u = AdminUser(
        name="opsadmin",
        authorized_keys=["ssh-ed25519 AAAA... a@b"],
    )
    assert u.password is None
    assert u.groups == ["wheel"]


def test_admin_user_rejects_root():
    with pytest.raises(ValidationError, match="root"):
        AdminUser(name="root", authorized_keys=["ssh-ed25519 AAA a@b"])


def test_user_holds_admin():
    u = User(admin=AdminUser(name="opsadmin", authorized_keys=["ssh-ed25519 A a@b"]))
    assert u.admin.name == "opsadmin"


def test_ssh_defaults():
    s = Ssh()
    assert s.port == 22
    assert s.permit_root_login == "no"
    assert s.password_authentication is False
    assert s.client_alive_interval == 600


def test_banner_default_is_civilian():
    b = Banner()
    assert "U.S. Government" not in b.text
    assert "private" in b.text.lower()
    assert "issue" in b.apply_to


def test_time_defaults_are_not_dod():
    t = Time()
    assert t.servers == ["pool.ntp.org"]
    assert "usno" not in str(t.servers).lower()


def test_crypto_default_is_modern():
    assert Crypto().policy == CryptoPolicy.MODERN


def test_crypto_accepts_stig_and_future():
    assert Crypto(policy=CryptoPolicy.STIG).policy == CryptoPolicy.STIG
    assert Crypto(policy=CryptoPolicy.FUTURE).policy == CryptoPolicy.FUTURE


def test_packages_include_security_baseline():
    p = Packages()
    for required in (
        "scap-security-guide",
        "openscap-scanner",
        "aide",
        "firewalld",
        "chrony",
    ):
        assert required in p.required
    # v0.1.1: oscap-anaconda-addon dropped in favor of %post-driven oscap remediation.
    assert "oscap-anaconda-addon" not in p.required


def test_packages_exclude_known_legacy():
    p = Packages()
    for legacy in ("telnet-server", "rsh-server", "ypserv"):
        assert legacy in p.excluded


def test_packages_include_dnf_automatic_tooling():
    p = Packages()
    assert "dnf-automatic" in p.required
    assert "dnf-utils" in p.required


def test_packages_preset_defaults_to_standard():
    p = Packages()
    assert p.preset == PackagesPreset.STANDARD


def test_packages_preset_accepts_lean():
    p = Packages(preset=PackagesPreset.LEAN)
    assert p.preset == PackagesPreset.LEAN


def test_packages_preset_accepts_string_value():
    p = Packages(preset="lean")
    assert p.preset.value == "lean"


def test_packages_preset_rejects_unknown_value():
    with pytest.raises(ValidationError):
        Packages(preset="ultra-lean")


def test_overrides_safe_defaults():
    o = Overrides()
    assert o.fips_mode is False
    assert o.faillock.unlock_time == 900
    assert o.faillock.even_deny_root is False
    assert o.auditd.disk_full_action == AuditdSystemAction.SUSPEND
    assert o.auditd.max_log_file_action == AuditdMaxFileAction.ROTATE
    assert o.ssh_keep_open.ensure_firewalld_port is True
    assert o.usbguard.enable is False
    assert o.dod_root_ca.install is False
    assert "usb-storage" in o.kernel_module_blacklist.modules


def test_auditd_actions_reject_bogus():
    with pytest.raises(ValidationError):
        AuditdActionsCfg(disk_full_action="BURN")  # type: ignore[arg-type]


def test_custom_post_passes_through():
    cfg = HostConfig.model_validate(
        {
            "system": {"hostname": "x"},
            "user": {
                "admin": {
                    "name": "ops",
                    "authorized_keys": ["ssh-ed25519 A a@b"],
                    "sudo": "nopasswd_yes",
                }
            },
            "custom_post": ["echo hello"],
        }
    )
    assert cfg.custom_post == ["echo hello"]


def test_exception_decl_requires_rule_ids():
    with pytest.raises(ValidationError):
        ExceptionDecl(id="no-luks", reason="x", stig_rules_disabled=[])


def test_modern_crypto_and_fips_mode_rejected():
    payload = {
        "system": {"hostname": "x"},
        "user": {
            "admin": {
                "name": "ops",
                "authorized_keys": ["ssh-ed25519 A a@b"],
                "sudo": "nopasswd_yes",
            }
        },
        "crypto": {"policy": "MODERN"},
        "overrides": {"fips_mode": True},
    }
    with pytest.raises(ValidationError, match=r"MODERN.*fips_mode"):
        HostConfig.model_validate(payload)


def test_stig_crypto_without_fips_allowed():
    cfg = HostConfig.model_validate(
        {
            "system": {"hostname": "x"},
            "user": {
                "admin": {
                    "name": "ops",
                    "authorized_keys": ["ssh-ed25519 A a@b"],
                    "sudo": "nopasswd_yes",
                }
            },
            "crypto": {"policy": "STIG"},
            "overrides": {"fips_mode": False},
        }
    )
    assert cfg.crypto.policy == CryptoPolicy.STIG


def test_locked_admin_with_password_sudo_rejected():
    payload = {
        "system": {"hostname": "x"},
        "user": {
            "admin": {
                "name": "ops",
                "authorized_keys": ["ssh-ed25519 A a@b"],
                # password unset (locked account) AND sudo requires password
                "sudo": "nopasswd_no",
            }
        },
    }
    with pytest.raises(ValidationError, match=r"locked admin.*nopasswd_yes"):
        HostConfig.model_validate(payload)


def test_locked_admin_with_nopasswd_sudo_allowed():
    cfg = HostConfig.model_validate(
        {
            "system": {"hostname": "x"},
            "user": {
                "admin": {
                    "name": "ops",
                    "authorized_keys": ["ssh-ed25519 A a@b"],
                    "sudo": "nopasswd_yes",
                }
            },
        }
    )
    assert cfg.user.admin.password is None
    assert cfg.user.admin.sudo == "nopasswd_yes"


def test_password_admin_with_password_sudo_allowed():
    cfg = HostConfig.model_validate(
        {
            "system": {"hostname": "x"},
            "user": {
                "admin": {
                    "name": "ops",
                    "authorized_keys": ["ssh-ed25519 A a@b"],
                    "password": "$6$salt$hashvalue",
                    "sudo": "nopasswd_no",
                }
            },
        }
    )
    assert cfg.user.admin.password == "$6$salt$hashvalue"
    assert cfg.user.admin.sudo == "nopasswd_no"


def test_unattended_updates_defaults_are_enabled():
    u = UnattendedUpdatesCfg()
    assert u.enable is True
    assert u.nightly_security.enable is True
    assert u.nightly_security.on_calendar == "*-*-* 02:00:00"
    assert u.monthly_full.enable is True
    assert u.monthly_full.on_calendar == "Sun *-*-1..7 02:30:00"
    assert u.reboot_window.enable is True
    assert u.reboot_window.on_calendar == "Sun *-*-* 03:00:00"


def test_unattended_updates_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        UnattendedUpdatesCfg.model_validate({"enable": True, "garbage": 1})


def test_unattended_updates_on_calendar_must_be_nonempty():
    with pytest.raises(ValidationError):
        NightlySecurityCfg(on_calendar="")


def test_overrides_has_unattended_updates_default():
    o = Overrides()
    assert o.unattended_updates.enable is True
    assert o.unattended_updates.nightly_security.enable is True


def test_reboot_window_without_updates_rejected():
    payload = {
        "system": {"hostname": "x"},
        "user": {
            "admin": {
                "name": "ops",
                "authorized_keys": ["ssh-ed25519 A a@b"],
                "sudo": "nopasswd_yes",
            }
        },
        "overrides": {
            "unattended_updates": {
                "nightly_security": {"enable": False},
                "monthly_full": {"enable": False},
                "reboot_window": {"enable": True},
            }
        },
    }
    with pytest.raises(ValidationError, match="reboot_window requires"):
        HostConfig.model_validate(payload)


def test_reboot_window_validator_skipped_when_master_disabled():
    # When the master enable=false, the rule no-ops anyway; the cross-field
    # validator shouldn't raise on otherwise-inconsistent leftover knobs.
    cfg = UnattendedUpdatesCfg(
        enable=False,
        nightly_security=NightlySecurityCfg(enable=False),
        monthly_full=MonthlyFullCfg(enable=False),
        reboot_window=RebootWindowCfg(enable=True),
    )
    assert cfg.enable is False


def test_reboot_window_with_only_monthly_allowed():
    payload = {
        "system": {"hostname": "x"},
        "user": {
            "admin": {
                "name": "ops",
                "authorized_keys": ["ssh-ed25519 A a@b"],
                "sudo": "nopasswd_yes",
            }
        },
        "overrides": {
            "unattended_updates": {
                "nightly_security": {"enable": False},
                "monthly_full": {"enable": True},
                "reboot_window": {"enable": True},
            }
        },
    }
    cfg = HostConfig.model_validate(payload)
    assert cfg.overrides.unattended_updates.reboot_window.enable is True


def test_disk_lv_def_minimal_valid():
    from ks_gen.config import DiskLvDef

    lv = DiskLvDef(name="root", mount="/", size="15G")
    assert lv.name == "root"
    assert lv.mount == "/"
    assert lv.size == "15G"
    assert lv.fstype == "xfs"
    assert lv.fsoptions is None
    assert lv.encrypted is False


def test_disk_lv_def_name_rejects_special_chars():
    from ks_gen.config import DiskLvDef

    with pytest.raises(ValidationError):
        DiskLvDef(name="root/path", mount="/", size="15G")


def test_disk_lv_def_size_rejects_bare_number():
    from ks_gen.config import DiskLvDef

    with pytest.raises(ValidationError):
        DiskLvDef(name="root", mount="/", size="15")


def test_disk_lv_def_size_rejects_unknown_unit():
    from ks_gen.config import DiskLvDef

    with pytest.raises(ValidationError):
        DiskLvDef(name="root", mount="/", size="15K")


def test_disk_lv_def_size_accepts_recommended():
    from ks_gen.config import DiskLvDef

    lv = DiskLvDef(name="swap", size="recommended", fstype="swap")
    assert lv.size == "recommended"


def test_disk_lv_def_size_accepts_omitted():
    from ks_gen.config import DiskLvDef

    lv = DiskLvDef(name="root", mount="/")
    assert lv.size is None


def test_disk_boot_part_defaults():
    from ks_gen.config import DiskBootPart

    b = DiskBootPart()
    assert b.size == "1G"
    assert b.fstype == "xfs"
    assert b.fsoptions == "nodev,nosuid"


def test_disk_boot_part_rejects_T_unit():
    from ks_gen.config import DiskBootPart

    with pytest.raises(ValidationError):
        DiskBootPart(size="2T")


def test_disk_boot_part_accepts_M_and_G_units():
    from ks_gen.config import DiskBootPart

    assert DiskBootPart(size="500M").size == "500M"
    assert DiskBootPart(size="2G").size == "2G"


def test_disk_efi_part_defaults():
    from ks_gen.config import DiskEfiPart

    e = DiskEfiPart()
    assert e.size == "1G"


def test_disk_efi_part_rejects_T_unit():
    from ks_gen.config import DiskEfiPart

    with pytest.raises(ValidationError):
        DiskEfiPart(size="2T")


def _stig_layout_lvs():
    """Helper: returns the minimal STIG LV list (used by several layout tests)."""
    return [
        {"name": "root", "mount": "/"},
        {"name": "home", "mount": "/home"},
        {"name": "tmp", "mount": "/tmp"},
        {"name": "var", "mount": "/var"},
        {"name": "varlog", "mount": "/var/log"},
        {"name": "varlogaudit", "mount": "/var/log/audit"},
        {"name": "vartmp", "mount": "/var/tmp"},
        {"name": "swap", "fstype": "swap"},
    ]


def test_disk_layout_minimal_valid():
    from ks_gen.config import DiskLayout

    layout = DiskLayout.model_validate({"lvs": _stig_layout_lvs()})
    assert layout.vg_name == "vg_root"
    assert len(layout.lvs) == 8
    assert layout.boot.size == "1G"
    assert layout.efi.size == "1G"


def test_disk_target_accepts_plain_basename():
    d = Disk.model_validate({"target": "sda"})
    assert d.target == "sda"


def test_disk_target_accepts_nvme():
    d = Disk.model_validate({"target": "nvme0n1"})
    assert d.target == "nvme0n1"


def test_disk_target_defaults_to_none():
    d = Disk.model_validate({})
    assert d.target is None


def test_disk_target_with_dev_prefix_rejected():
    with pytest.raises(ValidationError):
        Disk.model_validate({"target": "/dev/sda"})


def test_disk_target_with_leading_digit_rejected():
    with pytest.raises(ValidationError):
        Disk.model_validate({"target": "1sda"})


def test_disk_target_empty_rejected():
    with pytest.raises(ValidationError):
        Disk.model_validate({"target": ""})


def test_disk_layout_ondisk_field_removed():
    """Regression-lock the rename: the old field name now hard-fails."""
    from ks_gen.config import DiskLayout

    with pytest.raises(ValidationError):
        DiskLayout.model_validate({"ondisk": "sda", "lvs": _stig_layout_lvs()})


def test_disk_layout_empty_lvs_rejected():
    from ks_gen.config import DiskLayout

    with pytest.raises(ValidationError):
        DiskLayout.model_validate({"lvs": []})


REQUIRED_MOUNTS_FOR_PARAMETRIZE = [
    "/",
    "/home",
    "/tmp",
    "/var",
    "/var/log",
    "/var/log/audit",
    "/var/tmp",
]


@pytest.mark.parametrize("missing_mount", REQUIRED_MOUNTS_FOR_PARAMETRIZE)
def test_disk_layout_missing_required_mountpoint(missing_mount):
    from ks_gen.config import DiskLayout

    lvs = [lv for lv in _stig_layout_lvs() if lv.get("mount") != missing_mount]
    with pytest.raises(
        ValidationError,
        match=rf"disk\.layout missing STIG-required mountpoint: {re.escape(missing_mount)}",
    ):
        DiskLayout.model_validate({"lvs": lvs})


def test_disk_layout_no_swap_rejected():
    from ks_gen.config import DiskLayout

    lvs = [lv for lv in _stig_layout_lvs() if lv["name"] != "swap"]
    with pytest.raises(ValidationError, match=r"exactly one swap"):
        DiskLayout.model_validate({"lvs": lvs})


def test_disk_layout_multiple_swap_rejected():
    from ks_gen.config import DiskLayout

    lvs = [*_stig_layout_lvs(), {"name": "swap2", "fstype": "swap"}]
    with pytest.raises(ValidationError, match=r"exactly one swap"):
        DiskLayout.model_validate({"lvs": lvs})


def test_disk_layout_duplicate_lv_name_rejected():
    from ks_gen.config import DiskLayout

    lvs = _stig_layout_lvs()
    lvs.append({"name": "root", "mount": "/extra"})  # duplicate name
    with pytest.raises(ValidationError, match=r"duplicate LV name"):
        DiskLayout.model_validate({"lvs": lvs})


def test_disk_layout_duplicate_lv_mount_rejected():
    from ks_gen.config import DiskLayout

    lvs = _stig_layout_lvs()
    lvs.append({"name": "extra", "mount": "/var"})  # duplicate mount
    with pytest.raises(ValidationError, match=r"duplicate LV mount"):
        DiskLayout.model_validate({"lvs": lvs})


def test_disk_layout_multiple_swap_lvs_without_mounts_still_caught_by_swap_cardinality():
    # Sanity check: two swap LVs both with mount=None aren't caught by the
    # mount-uniqueness check (mount=None is excluded) but ARE caught by
    # the swap cardinality check.
    from ks_gen.config import DiskLayout

    lvs = [*_stig_layout_lvs(), {"name": "swap2", "fstype": "swap"}]
    with pytest.raises(ValidationError, match=r"exactly one swap"):
        DiskLayout.model_validate({"lvs": lvs})


def test_disk_layout_custom_mount_without_size_rejected():
    from ks_gen.config import DiskLayout

    lvs = _stig_layout_lvs()
    lvs.append({"name": "srv", "mount": "/srv"})  # custom mount, no size
    with pytest.raises(
        ValidationError,
        match=r"disk\.layout\.lvs\[srv\]\.size: required for custom mountpoint /srv",
    ):
        DiskLayout.model_validate({"lvs": lvs})


def test_disk_layout_custom_mount_with_size_ok():
    from ks_gen.config import DiskLayout

    lvs = _stig_layout_lvs()
    lvs.append({"name": "srv", "mount": "/srv", "size": "50G"})
    layout = DiskLayout.model_validate({"lvs": lvs})
    assert layout.lvs[-1].name == "srv"


def test_disk_layout_stig_mount_without_size_ok():
    # /var is in the defaults table -> size may be omitted
    from ks_gen.config import DiskLayout

    layout = DiskLayout.model_validate({"lvs": _stig_layout_lvs()})
    var = next(lv for lv in layout.lvs if lv.mount == "/var")
    assert var.size is None  # validator passes; renderer fills 10G


def test_disk_layout_swap_with_mount_rejected():
    from ks_gen.config import DiskLayout

    lvs = _stig_layout_lvs()
    # Add a "swap" with a mount path — nonsense, must be rejected.
    lvs.append({"name": "weird", "mount": "/foo", "fstype": "swap"})
    with pytest.raises(ValidationError, match=r"swap LV.*mount.*null"):
        DiskLayout.model_validate({"lvs": lvs})


def test_disk_layout_non_swap_without_mount_rejected():
    from ks_gen.config import DiskLayout

    lvs = _stig_layout_lvs()
    lvs.append({"name": "weird", "fstype": "xfs"})  # no mount, no swap
    with pytest.raises(ValidationError, match=r"non-swap LV.*mount"):
        DiskLayout.model_validate({"lvs": lvs})


def test_disk_neither_defaults_to_stig_server():
    # v0.3 backwards compat: empty `disk:` block -> preset=STIG_SERVER
    from ks_gen.config import Disk, DiskPreset

    d = Disk()
    assert d.preset == DiskPreset.STIG_SERVER
    assert d.layout is None


def test_disk_preset_explicit_works():
    from ks_gen.config import Disk, DiskPreset

    d = Disk(preset=DiskPreset.MINIMAL)
    assert d.preset == DiskPreset.MINIMAL
    assert d.layout is None


def test_disk_layout_only_leaves_preset_none():
    from ks_gen.config import Disk

    payload = {"layout": {"lvs": _stig_layout_lvs()}}
    d = Disk.model_validate(payload)
    assert d.preset is None
    assert d.layout is not None


def test_disk_preset_and_layout_both_set_rejected():
    from ks_gen.config import Disk

    payload = {
        "preset": "stig_server",
        "layout": {"lvs": _stig_layout_lvs()},
    }
    with pytest.raises(ValidationError, match=r"mutually exclusive"):
        Disk.model_validate(payload)


def test_disk_preset_custom_rejected_with_layout_message():
    from ks_gen.config import Disk

    with pytest.raises(ValidationError, match=r"disk\.layout block"):
        Disk.model_validate({"preset": "custom"})


def test_luks_preset_values():
    from ks_gen.config import LuksPreset

    assert LuksPreset.NONE.value == "none"
    assert LuksPreset.PARTIAL.value == "partial"
    assert LuksPreset.TANG.value == "tang"


def test_tang_server_valid():
    from ks_gen.config import TangServer

    s = TangServer(
        url="https://tang1.example.com",
        thumbprint="xK3HFGm-AVOaJVlA8oFAo7uMcrJBhFCdwq8WX8gqXJU",
    )
    assert s.url == "https://tang1.example.com"


def test_tang_server_rejects_non_http_url():
    from ks_gen.config import TangServer

    with pytest.raises(ValidationError):
        TangServer(
            url="ftp://tang1.example.com",
            thumbprint="xK3HFGm-AVOaJVlA8oFAo7uMcrJBhFCdwq8WX8gqXJU",
        )


def test_tang_server_thumbprint_too_short_rejected():
    from ks_gen.config import TangServer

    with pytest.raises(ValidationError):
        TangServer(url="https://tang1.example.com", thumbprint="short")


def test_tang_server_thumbprint_invalid_chars_rejected():
    from ks_gen.config import TangServer

    with pytest.raises(ValidationError):
        TangServer(
            url="https://tang1.example.com",
            thumbprint="invalid!@#chars in thumbprint here xx",
        )


def _tang_server_dict(n: int = 1) -> list[dict]:
    """Helper: returns n valid tang server dicts."""
    return [
        {
            "url": f"https://tang{i}.example.com",
            "thumbprint": "xK3HFGm-AVOaJVlA8oFAo7uMcrJBhFCdwq8WX8gqXJ" + chr(ord("A") + i),
        }
        for i in range(n)
    ]


def test_tang_default_threshold_is_one():
    from ks_gen.config import Tang

    t = Tang.model_validate({"servers": _tang_server_dict(2)})
    assert t.threshold == 1


def test_tang_rejects_empty_servers():
    from ks_gen.config import Tang

    with pytest.raises(ValidationError):
        Tang.model_validate({"servers": []})


def test_tang_threshold_exceeds_servers_rejected():
    from ks_gen.config import Tang

    with pytest.raises(
        ValidationError,
        match=r"threshold \(2\) exceeds servers count \(1\)",
    ):
        Tang.model_validate({"servers": _tang_server_dict(1), "threshold": 2})


def test_tang_threshold_equal_servers_ok():
    from ks_gen.config import Tang

    t = Tang.model_validate({"servers": _tang_server_dict(2), "threshold": 2})
    assert t.threshold == 2


def test_disk_luks_default_is_none():
    from ks_gen.config import DiskLuks, LuksPreset

    d = DiskLuks()
    assert d.preset == LuksPreset.NONE
    assert d.passphrase is None
    assert d.passphrase_file is None
    assert d.tang is None


def test_disk_luks_none_with_passphrase_rejected():
    from ks_gen.config import DiskLuks

    with pytest.raises(ValidationError, match=r"preset='none' rejects"):
        DiskLuks.model_validate({"preset": "none", "passphrase": "x"})


def test_disk_luks_none_with_passphrase_file_rejected():
    from ks_gen.config import DiskLuks

    with pytest.raises(ValidationError, match=r"preset='none' rejects"):
        DiskLuks.model_validate({"preset": "none", "passphrase_file": "/k"})


def test_disk_luks_none_with_tang_rejected():
    from ks_gen.config import DiskLuks

    with pytest.raises(ValidationError, match=r"preset='none' rejects"):
        DiskLuks.model_validate({"preset": "none", "tang": {"servers": _tang_server_dict(1)}})


def test_disk_luks_partial_without_passphrase_rejected():
    from ks_gen.config import DiskLuks

    with pytest.raises(ValidationError, match=r"requires passphrase or passphrase_file"):
        DiskLuks.model_validate({"preset": "partial"})


def test_disk_luks_partial_with_passphrase_ok():
    from ks_gen.config import DiskLuks, LuksPreset

    d = DiskLuks.model_validate({"preset": "partial", "passphrase": "hunter2"})
    assert d.preset == LuksPreset.PARTIAL
    assert d.passphrase == "hunter2"


def test_disk_luks_partial_with_passphrase_file_ok():
    from ks_gen.config import DiskLuks

    d = DiskLuks.model_validate({"preset": "partial", "passphrase_file": "/etc/ks-gen/luks.key"})
    assert d.passphrase_file == "/etc/ks-gen/luks.key"


def test_disk_luks_passphrase_and_file_both_set_rejected():
    from ks_gen.config import DiskLuks

    with pytest.raises(ValidationError, match=r"mutually exclusive"):
        DiskLuks.model_validate(
            {
                "preset": "partial",
                "passphrase": "x",
                "passphrase_file": "/k",
            }
        )


def test_disk_luks_partial_with_tang_block_rejected():
    from ks_gen.config import DiskLuks

    with pytest.raises(ValidationError, match=r"rejects tang block"):
        DiskLuks.model_validate(
            {
                "preset": "partial",
                "passphrase": "x",
                "tang": {"servers": _tang_server_dict(1)},
            }
        )


def test_disk_luks_tang_without_tang_block_rejected():
    from ks_gen.config import DiskLuks

    with pytest.raises(ValidationError, match=r"preset='tang' requires disk\.luks\.tang"):
        DiskLuks.model_validate({"preset": "tang", "passphrase": "x"})


def test_disk_luks_tang_with_passphrase_ok():
    from ks_gen.config import DiskLuks, LuksPreset

    d = DiskLuks.model_validate(
        {
            "preset": "tang",
            "passphrase": "fallback",
            "tang": {"servers": _tang_server_dict(2)},
        }
    )
    assert d.preset == LuksPreset.TANG
    assert d.tang is not None
    assert len(d.tang.servers) == 2


def test_disk_default_has_luks_none():
    from ks_gen.config import Disk, LuksPreset

    d = Disk()
    assert d.luks.preset == LuksPreset.NONE


def test_disk_minimal_plus_luks_partial_rejected():
    payload = {
        "system": {"hostname": "x"},
        "user": {
            "admin": {
                "name": "ops",
                "authorized_keys": ["ssh-ed25519 A a@b"],
                "sudo": "nopasswd_yes",
            }
        },
        "disk": {
            "preset": "minimal",
            "luks": {"preset": "partial", "passphrase": "x"},
        },
    }
    with pytest.raises(ValidationError, match=r"disk\.preset='minimal' has no LVM PV"):
        HostConfig.model_validate(payload)


def test_disk_minimal_plus_luks_tang_rejected():
    payload = {
        "system": {"hostname": "x"},
        "user": {
            "admin": {
                "name": "ops",
                "authorized_keys": ["ssh-ed25519 A a@b"],
                "sudo": "nopasswd_yes",
            }
        },
        "disk": {
            "preset": "minimal",
            "luks": {
                "preset": "tang",
                "passphrase": "fallback",
                "tang": {"servers": _tang_server_dict(1)},
            },
        },
    }
    with pytest.raises(ValidationError, match=r"disk\.preset='minimal' has no LVM PV"):
        HostConfig.model_validate(payload)


def test_disk_stig_server_plus_luks_partial_ok():
    payload = {
        "system": {"hostname": "x"},
        "user": {
            "admin": {
                "name": "ops",
                "authorized_keys": ["ssh-ed25519 A a@b"],
                "sudo": "nopasswd_yes",
            }
        },
        "disk": {
            "preset": "stig_server",
            "luks": {"preset": "partial", "passphrase": "hunter2"},
        },
    }
    cfg = HostConfig.model_validate(payload)
    assert cfg.disk.luks.preset.value == "partial"


def test_disk_layout_plus_luks_partial_ok():
    payload = {
        "system": {"hostname": "x"},
        "user": {
            "admin": {
                "name": "ops",
                "authorized_keys": ["ssh-ed25519 A a@b"],
                "sudo": "nopasswd_yes",
            }
        },
        "disk": {
            "layout": {"lvs": _stig_layout_lvs()},
            "luks": {"preset": "partial", "passphrase": "hunter2"},
        },
    }
    cfg = HostConfig.model_validate(payload)
    assert cfg.disk.luks.preset.value == "partial"
    assert cfg.disk.layout is not None


def test_disk_lv_def_encrypted_true_rejected_with_pv_level_message():
    from ks_gen.config import DiskLvDef

    with pytest.raises(
        ValidationError,
        match=r"per-LV encryption is not supported; use disk\.luks\.preset",
    ):
        DiskLvDef(name="root", mount="/", size="15G", encrypted=True)


def test_effective_base_groups_standard_passthrough():
    p = Packages()
    assert p.effective_base_groups == ["@^minimal-environment", "@standard"]


def test_effective_base_groups_lean_strips_standard():
    p = Packages(preset="lean")
    assert p.effective_base_groups == ["@^minimal-environment"]


def test_effective_base_groups_lean_preserves_user_custom_groups():
    p = Packages(preset="lean", base_groups=["@^minimal-environment", "@standard", "@development"])
    assert p.effective_base_groups == ["@^minimal-environment", "@development"]


def test_effective_required_standard_passthrough():
    p = Packages()
    assert p.effective_required == list(p.required)


def test_effective_required_lean_adds_compensating_packages():
    p = Packages(preset="lean")
    for pkg in ("logrotate", "postfix", "cronie", "crontabs", "parted"):
        assert pkg in p.effective_required


def test_effective_required_lean_preserves_required_order_and_dedupes():
    # User already lists logrotate explicitly; should appear once, in its
    # original position relative to the rest of `required`.
    p = Packages(preset="lean", required=["scap-security-guide", "logrotate", "aide"])
    assert p.effective_required.count("logrotate") == 1
    # Original entries come first; lean extras append after, with already-
    # present ones skipped.
    assert p.effective_required[:3] == ["scap-security-guide", "logrotate", "aide"]
    for pkg in ("postfix", "cronie", "crontabs", "parted"):
        assert pkg in p.effective_required[3:]


def test_effective_properties_are_not_serialized():
    """Pin the plain-@property (not @computed_field) choice.

    If these properties ever leak into model_dump(), host.yaml round-trips
    change shape and downstream golden snapshots will silently drift.
    """
    p = Packages(preset="lean")
    dumped = p.model_dump()
    assert "effective_base_groups" not in dumped
    assert "effective_required" not in dumped


def test_container_volume_defaults():
    v = ContainerVolume()
    assert v.size == "20G"
    assert v.fsoptions == "nodev,nosuid"
    assert v.size_mib == 20480


def test_container_volume_size_mib_megabytes():
    assert ContainerVolume(size="500M").size_mib == 500


def test_container_volume_size_mib_terabytes():
    assert ContainerVolume(size="1T").size_mib == 1048576


def test_container_volume_rejects_invalid_size_pattern():
    with pytest.raises(ValidationError):
        ContainerVolume(size="20GB")  # only M|G|T allowed, no double-letter
    with pytest.raises(ValidationError):
        ContainerVolume(size="big")


def test_container_volume_rejects_noexec_fsoption():
    with pytest.raises(ValidationError):
        ContainerVolume(fsoptions="nodev,nosuid,noexec")


def test_container_volume_rejects_noexec_with_spaces():
    with pytest.raises(ValidationError):
        ContainerVolume(fsoptions="nodev, noexec , nosuid")


def test_container_volume_accepts_other_options():
    v = ContainerVolume(fsoptions="nodev,nosuid,noatime")
    assert v.fsoptions == "nodev,nosuid,noatime"


def test_container_volume_size_mib_not_serialized():
    """Pin the plain-@property (not @computed_field) choice.

    If size_mib ever leaks into model_dump(), host.yaml round-trips change
    shape and downstream golden snapshots will silently drift.
    """
    v = ContainerVolume(size="500M")
    dumped = v.model_dump()
    assert "size_mib" not in dumped
    assert dumped == {"size": "500M", "fsoptions": "nodev,nosuid"}
