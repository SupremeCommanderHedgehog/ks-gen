import pytest
from pydantic import ValidationError

from ks_gen.config import Disk, DiskPreset, HostConfig, Interface, Meta, Network, System


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
    # Only meta + system are required at this stage.
    cfg = HostConfig.model_validate({"meta": {}, "system": {"hostname": "web01.example.com"}})
    assert cfg.system.hostname == "web01.example.com"


def test_unknown_top_level_key_rejected():
    with pytest.raises(ValidationError):
        HostConfig.model_validate({"meta": {}, "system": {"hostname": "x"}, "garbage": True})


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
