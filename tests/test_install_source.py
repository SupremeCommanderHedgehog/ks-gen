from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ks_gen.config import HostConfig, Install, InstallSourceKind
from ks_gen.loader import ConfigError, load_host_config
from ks_gen.writer import build_bundle


def _minimal_kwargs() -> dict:
    return {
        "system": {"hostname": "example"},
        "user": {
            "admin": {
                "name": "opsadmin",
                "authorized_keys": ["ssh-ed25519 AAAA test@host"],
                "sudo": "nopasswd_yes",
            }
        },
    }


_GOLDEN8 = Path(__file__).parent / "golden" / "alma8-minimal.host.yaml"
_GOLDEN9 = Path(__file__).parent / "golden" / "minimal-dhcp.host.yaml"


_GOLDEN_UBUNTU = Path(__file__).parent / "golden" / "ubuntu-minimal.host.yaml"


def test_network_default_urls_rejected_on_alma8():
    with pytest.raises(ConfigError, match="do not match distro"):
        load_host_config(_GOLDEN8, sets=["install.source=network"])


def test_network_partial_url_override_rejected_on_alma8():
    with pytest.raises(ConfigError, match="do not match distro"):
        load_host_config(
            _GOLDEN8,
            sets=[
                "install.source=network",
                "install.baseos_url=https://repo.almalinux.org/almalinux/8/BaseOS/x86_64/os/",
            ],
        )


def test_network_source_rejected_on_ubuntu2404():
    with pytest.raises(ConfigError, match="ubuntu2404"):
        load_host_config(_GOLDEN_UBUNTU, sets=["install.source=network"])


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


def test_alma10_network_defaults_to_unpinned_10_stream():
    # AL10 boot media carries no package payload, so network install is the
    # only usable mode there — it gets working defaults rather than an error.
    cfg = HostConfig(distro="alma10", install={"source": "network"}, **_minimal_kwargs())
    assert cfg.install.baseos_url == "https://repo.almalinux.org/almalinux/10/BaseOS/x86_64/os/"
    assert (
        cfg.install.appstream_url == "https://repo.almalinux.org/almalinux/10/AppStream/x86_64/os/"
    )


def test_alma10_network_urls_are_not_point_release_pinned():
    cfg = HostConfig(distro="alma10", install={"source": "network"}, **_minimal_kwargs())
    assert "/10.2/" not in cfg.install.baseos_url
    assert "/10.2/" not in cfg.install.appstream_url


def test_alma10_explicit_urls_win_over_defaults():
    cfg = HostConfig(
        distro="alma10",
        install={"source": "network", "baseos_url": "https://mirror.example/BaseOS/"},
        **_minimal_kwargs(),
    )
    assert cfg.install.baseos_url == "https://mirror.example/BaseOS/"
    # The untouched one still gets the AL10 default, not the AL9 one.
    assert "/10/" in cfg.install.appstream_url


def test_alma10_without_install_block_still_gets_al10_urls():
    # `ks-gen gen` writes the fully-expanded config back out, so whatever
    # lands here becomes explicit in the operator's host.yaml. AL9 URLs
    # under distro=alma10 would then survive a later flip to network.
    cfg = HostConfig(distro="alma10", **_minimal_kwargs())
    assert cfg.install.source == InstallSourceKind.MEDIA
    assert "/almalinux/10/" in cfg.install.baseos_url
    assert "/almalinux/10/" in cfg.install.appstream_url


def test_alma10_rejects_explicit_al9_urls():
    with pytest.raises(ValidationError, match="do not match distro"):
        HostConfig(
            distro="alma10",
            install={
                "source": "network",
                "baseos_url": "https://repo.almalinux.org/almalinux/9.8/BaseOS/x86_64/os/",
                "appstream_url": "https://repo.almalinux.org/almalinux/9.8/AppStream/x86_64/os/",
            },
            **_minimal_kwargs(),
        )


def test_alma9_rejects_explicit_al10_urls():
    with pytest.raises(ValidationError, match="do not match distro"):
        HostConfig(
            distro="alma9",
            install={
                "source": "network",
                "baseos_url": "https://repo.almalinux.org/almalinux/10/BaseOS/x86_64/os/",
                "appstream_url": "https://repo.almalinux.org/almalinux/10/AppStream/x86_64/os/",
            },
            **_minimal_kwargs(),
        )


def test_validator_does_not_mutate_the_callers_install_dict():
    # verify/suggest.py shallow-copies the loaded config and dumps it back
    # over the operator's host.yaml — mutating the nested dict would write
    # keys they never authored.
    install = {"source": "network"}
    HostConfig(distro="alma10", install=install, **_minimal_kwargs())
    assert install == {"source": "network"}


def test_alma10_network_emits_url_and_repo():
    cfg = HostConfig(distro="alma10", install={"source": "network"}, **_minimal_kwargs())
    ks = build_bundle(cfg).ks_cfg
    assert 'url --url="https://repo.almalinux.org/almalinux/10/BaseOS/x86_64/os/"' in ks
    assert (
        "repo --name=AppStream "
        '--baseurl="https://repo.almalinux.org/almalinux/10/AppStream/x86_64/os/"'
    ) in ks


def test_install_urls_overridable():
    ins = Install(source="network", baseos_url="https://mirror.example/BaseOS/")
    assert ins.baseos_url == "https://mirror.example/BaseOS/"


def test_network_source_emits_url_and_repo():
    cfg = load_host_config(_GOLDEN9, sets=["install.source=network"])
    ks = build_bundle(cfg).ks_cfg
    assert 'url --url="https://repo.almalinux.org/almalinux/9.8/BaseOS/x86_64/os/"' in ks
    assert (
        "repo --name=AppStream "
        '--baseurl="https://repo.almalinux.org/almalinux/9.8/AppStream/x86_64/os/"'
    ) in ks


def test_media_source_omits_url():
    cfg = load_host_config(_GOLDEN9, sets=[])
    ks = build_bundle(cfg).ks_cfg
    assert "url --url=" not in ks
