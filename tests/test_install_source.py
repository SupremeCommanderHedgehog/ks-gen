from __future__ import annotations

from pathlib import Path

import pytest

from ks_gen.config import Install, InstallSourceKind
from ks_gen.loader import ConfigError, load_host_config

_GOLDEN8 = Path(__file__).parent / "golden" / "alma8-minimal.host.yaml"
_GOLDEN9 = Path(__file__).parent / "golden" / "minimal-dhcp.host.yaml"


def test_network_default_urls_rejected_on_alma8():
    with pytest.raises(ConfigError, match="do not match distro"):
        load_host_config(_GOLDEN8, sets=["install.source=network"])


def test_network_custom_urls_accepted_on_alma8():
    cfg = load_host_config(
        _GOLDEN8,
        sets=[
            "install.source=network",
            "install.baseos_url=https://repo.almalinux.org/almalinux/8/BaseOS/x86_64/os/",
            "install.appstream_url=https://repo.almalinux.org/almalinux/8/AppStream/x86_64/os/",
        ],
    )
    assert cfg.install.source == InstallSourceKind.NETWORK
    assert cfg.install.baseos_url == "https://repo.almalinux.org/almalinux/8/BaseOS/x86_64/os/"


def test_network_default_urls_accepted_on_alma9():
    cfg = load_host_config(_GOLDEN9, sets=["install.source=network"])
    assert cfg.install.source == InstallSourceKind.NETWORK


def test_media_source_default_urls_accepted_on_alma8():
    cfg = load_host_config(_GOLDEN8, sets=[])
    assert cfg.install.source == InstallSourceKind.MEDIA


def test_install_defaults_to_media():
    ins = Install()
    assert ins.source == InstallSourceKind.MEDIA


def test_install_network_source_parses():
    ins = Install(source="network")
    assert ins.source == InstallSourceKind.NETWORK


def test_install_default_urls_pin_9_8():
    ins = Install()
    assert ins.baseos_url == "https://repo.almalinux.org/almalinux/9.8/BaseOS/x86_64/os/"
    assert ins.appstream_url == "https://repo.almalinux.org/almalinux/9.8/AppStream/x86_64/os/"


def test_install_urls_overridable():
    ins = Install(source="network", baseos_url="https://mirror.example/BaseOS/")
    assert ins.baseos_url == "https://mirror.example/BaseOS/"
