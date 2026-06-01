from __future__ import annotations

import pytest

from ks_gen.config import AdminUser, HostConfig, System, User


@pytest.fixture()
def minimal_cfg() -> HostConfig:
    return HostConfig(
        system=System(hostname="web01.example.com"),
        user=User(admin=AdminUser(name="opsadmin", authorized_keys=["ssh-ed25519 AAAA a@b"])),
    )
