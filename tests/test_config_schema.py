import pytest
from pydantic import ValidationError

from ks_gen.config import (
    AdminUser,
    Banner,
    Crypto,
    CryptoPolicy,
    Disk,
    DiskPreset,
    HostConfig,
    Interface,
    Meta,
    Network,
    Packages,
    Ssh,
    System,
    Time,
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
            "user": {"admin": {"name": "ops", "authorized_keys": ["ssh-ed25519 A a@b"]}},
        }
    )
    assert cfg.system.hostname == "web01.example.com"


def test_unknown_top_level_key_rejected():
    with pytest.raises(ValidationError):
        HostConfig.model_validate(
            {
                "meta": {},
                "system": {"hostname": "x"},
                "user": {"admin": {"name": "ops", "authorized_keys": ["ssh-ed25519 A a@b"]}},
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
        "oscap-anaconda-addon",
        "aide",
        "firewalld",
        "chrony",
    ):
        assert required in p.required


def test_packages_exclude_known_legacy():
    p = Packages()
    for legacy in ("telnet-server", "rsh-server", "ypserv"):
        assert legacy in p.excluded
