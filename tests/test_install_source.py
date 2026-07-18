from __future__ import annotations

from ks_gen.config import Install, InstallSourceKind


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
