import yaml

from ks_gen.config import AdminUser, HostConfig, System, User
from ks_gen.skeleton import render_meta_data, render_user_data


def _ubuntu_cfg(hostname: str = "u2404-host", admin: str = "ops") -> HostConfig:
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


def test_render_user_data_starts_with_cloud_config_header():
    text = render_user_data(_ubuntu_cfg())
    assert text.splitlines()[0] == "#cloud-config"


def test_render_user_data_parses_as_yaml_with_autoinstall_v1():
    text = render_user_data(_ubuntu_cfg())
    doc = yaml.safe_load(text)
    assert isinstance(doc, dict)
    assert "autoinstall" in doc
    assert doc["autoinstall"]["version"] == 1


def test_render_user_data_carries_hostname_and_admin_username():
    text = render_user_data(_ubuntu_cfg(hostname="u24-test", admin="opsadmin"))
    doc = yaml.safe_load(text)
    identity = doc["autoinstall"]["identity"]
    assert identity["hostname"] == "u24-test"
    assert identity["username"] == "opsadmin"


def test_render_user_data_password_is_locked():
    # Locked password ("*") forces SSH-key-only — matches the alma9 path's
    # rootpw --lock / user --lock convention. Phase 3 will derive this
    # from cfg.user.admin.password (None => locked, otherwise hash).
    text = render_user_data(_ubuntu_cfg())
    doc = yaml.safe_load(text)
    assert doc["autoinstall"]["identity"]["password"] == "*"


def test_render_user_data_late_commands_is_empty_list():
    # Phase 2 emits a placeholder bundle: no rules yet, no late-commands.
    # Phase 3 will populate this list from the ubuntu2404 rule registry.
    text = render_user_data(_ubuntu_cfg())
    doc = yaml.safe_load(text)
    assert doc["autoinstall"]["late-commands"] == []


def test_render_meta_data_carries_hostname():
    text = render_meta_data(_ubuntu_cfg(hostname="u24-meta-test"))
    doc = yaml.safe_load(text)
    assert doc["instance-id"] == "u24-meta-test"
    assert doc["local-hostname"] == "u24-meta-test"
