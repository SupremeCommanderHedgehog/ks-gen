import pytest
from pydantic import ValidationError

from ks_gen.config import (
    AdminUser,
    AuditdActionsCfg,
    AuditdMaxFileAction,
    AuditdSystemAction,
    Banner,
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
