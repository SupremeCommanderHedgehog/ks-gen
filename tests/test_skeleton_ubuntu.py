import pytest
import yaml

from ks_gen.skeleton import render_meta_data, render_user_data


def test_render_user_data_starts_with_cloud_config_header(ubuntu_cfg_factory):
    text = render_user_data(ubuntu_cfg_factory())
    assert text.splitlines()[0] == "#cloud-config"


def test_render_user_data_parses_as_yaml_with_autoinstall_v1(ubuntu_cfg_factory):
    text = render_user_data(ubuntu_cfg_factory())
    doc = yaml.safe_load(text)
    assert isinstance(doc, dict)
    assert "autoinstall" in doc
    assert doc["autoinstall"]["version"] == 1


def test_render_user_data_carries_hostname_and_admin_username(ubuntu_cfg_factory):
    text = render_user_data(ubuntu_cfg_factory(hostname="u24-test", admin="opsadmin"))
    doc = yaml.safe_load(text)
    identity = doc["autoinstall"]["identity"]
    assert identity["hostname"] == "u24-test"
    assert identity["username"] == "opsadmin"


def test_render_user_data_password_is_locked(ubuntu_cfg_factory):
    # Locked password ("*") forces SSH-key-only — matches the alma9 path's
    # rootpw --lock / user --lock convention. Phase 3 will derive this
    # from cfg.user.admin.password (None => locked, otherwise hash).
    text = render_user_data(ubuntu_cfg_factory())
    doc = yaml.safe_load(text)
    assert doc["autoinstall"]["identity"]["password"] == "*"


def test_render_user_data_late_commands_is_empty_list(ubuntu_cfg_factory):
    # Phase 2 emits a placeholder bundle: no rules yet, no late-commands.
    # Phase 3 will populate this list from the ubuntu2404 rule registry.
    text = render_user_data(ubuntu_cfg_factory())
    doc = yaml.safe_load(text)
    assert doc["autoinstall"]["late-commands"] == []


def test_render_meta_data_carries_hostname(ubuntu_cfg_factory):
    text = render_meta_data(ubuntu_cfg_factory(hostname="u24-meta-test"))
    doc = yaml.safe_load(text)
    assert doc["instance-id"] == "u24-meta-test"
    assert doc["local-hostname"] == "u24-meta-test"


@pytest.mark.parametrize(
    "hostname",
    [
        "true",  # YAML implicit bool
        "null",  # YAML implicit None
        "2026-06-19",  # YAML implicit date
        "host:with:colons",
        'host"with"quotes',
    ],
)
def test_render_user_data_yaml_reserved_hostname_round_trips_as_string(
    ubuntu_cfg_factory, hostname
):
    text = render_user_data(ubuntu_cfg_factory(hostname=hostname))
    doc = yaml.safe_load(text)
    assert isinstance(doc["autoinstall"]["identity"]["hostname"], str)
    assert doc["autoinstall"]["identity"]["hostname"] == hostname


@pytest.mark.parametrize(
    "hostname",
    [
        "true",
        "null",
        "2026-06-19",
        "host:with:colons",
        'host"with"quotes',
    ],
)
def test_render_meta_data_yaml_reserved_hostname_round_trips_as_string(
    ubuntu_cfg_factory, hostname
):
    text = render_meta_data(ubuntu_cfg_factory(hostname=hostname))
    doc = yaml.safe_load(text)
    assert isinstance(doc["instance-id"], str)
    assert doc["instance-id"] == hostname
    assert doc["local-hostname"] == hostname
