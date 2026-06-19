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
                authorized_keys=["ssh-ed25519 AAAA a@b"],
                sudo="nopasswd_yes",
            )
        ),
    )


@pytest.fixture()
def ubuntu_cfg_factory():
    """Factory producing a minimal ubuntu2404 HostConfig.

    Returns a callable so tests can override `hostname` and `admin` per
    case. Default values: hostname="u2404-host", admin="ops".
    """
    from ks_gen.config import AdminUser, HostConfig, System, User

    def _make(hostname: str = "u2404-host", admin: str = "ops") -> HostConfig:
        return HostConfig(
            distro="ubuntu2404",
            system=System(hostname=hostname),
            user=User(
                admin=AdminUser(
                    name=admin,
                    authorized_keys=["ssh-ed25519 AAAA a@b"],
                    sudo="nopasswd_yes",
                )
            ),
        )

    return _make
