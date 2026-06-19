from __future__ import annotations

import pytest
from pydantic import ValidationError

from ks_gen.config import HostConfig


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


def test_distro_defaults_to_alma9():
    cfg = HostConfig(**_minimal_kwargs())
    assert cfg.distro == "alma9"


def test_distro_accepts_ubuntu2404():
    cfg = HostConfig(distro="ubuntu2404", **_minimal_kwargs())
    assert cfg.distro == "ubuntu2404"


def test_distro_rejects_unknown_value():
    with pytest.raises(ValidationError) as ei:
        HostConfig(distro="centos7", **_minimal_kwargs())
    assert "distro" in str(ei.value)


def test_scap_content_default_matches_alma9():
    cfg = HostConfig(**_minimal_kwargs())
    assert cfg.meta.scap_content == "ssg-almalinux9-ds.xml"


def test_scap_content_default_matches_ubuntu2404():
    cfg = HostConfig(distro="ubuntu2404", **_minimal_kwargs())
    assert cfg.meta.scap_content == "ssg-ubuntu2404-ds.xml"


def test_scap_content_explicit_override_must_match_distro_alma9():
    with pytest.raises(ValidationError) as ei:
        HostConfig(
            distro="alma9",
            meta={"scap_content": "ssg-ubuntu2404-ds.xml"},
            **_minimal_kwargs(),
        )
    assert "scap_content" in str(ei.value)


def test_scap_content_explicit_override_must_match_distro_ubuntu2404():
    with pytest.raises(ValidationError) as ei:
        HostConfig(
            distro="ubuntu2404",
            meta={"scap_content": "ssg-almalinux9-ds.xml"},
            **_minimal_kwargs(),
        )
    assert "scap_content" in str(ei.value)
