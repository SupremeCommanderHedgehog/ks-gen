from __future__ import annotations

import pytest

from ks_gen.config import AdminUser, HostConfig, System, User


@pytest.fixture()
def minimal_cfg() -> HostConfig:
    return HostConfig(
        system=System(hostname="web01.example.com"),
        user=User(
            admin=AdminUser(
                name="opsadmin",
                # Two types so the fixture is valid under every crypto.policy:
                # STIG strips Ed25519 from PubkeyAcceptedAlgorithms (#73).
                authorized_keys=["ssh-ed25519 AAAA a@b", "ssh-rsa BBBB a@b"],
                sudo="nopasswd_yes",
            )
        ),
    )
