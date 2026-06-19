import pytest
import yaml

from ks_gen.skeleton import PostBlock, render_meta_data, render_user_data


def test_render_user_data_starts_with_cloud_config_header(ubuntu_cfg_factory):
    text = render_user_data(ubuntu_cfg_factory(), post_blocks=[])
    assert text.splitlines()[0] == "#cloud-config"


def test_render_user_data_parses_as_yaml_with_autoinstall_v1(ubuntu_cfg_factory):
    text = render_user_data(ubuntu_cfg_factory(), post_blocks=[])
    doc = yaml.safe_load(text)
    assert isinstance(doc, dict)
    assert "autoinstall" in doc
    assert doc["autoinstall"]["version"] == 1


def test_render_user_data_carries_hostname_and_admin_username(ubuntu_cfg_factory):
    text = render_user_data(
        ubuntu_cfg_factory(hostname="u24-test", admin="opsadmin"), post_blocks=[]
    )
    doc = yaml.safe_load(text)
    identity = doc["autoinstall"]["identity"]
    assert identity["hostname"] == "u24-test"
    assert identity["username"] == "opsadmin"


def test_render_user_data_password_is_locked(ubuntu_cfg_factory):
    # Locked password ("*") forces SSH-key-only — matches the alma9 path's
    # rootpw --lock / user --lock convention. Phase 3 will derive this
    # from cfg.user.admin.password (None => locked, otherwise hash).
    text = render_user_data(ubuntu_cfg_factory(), post_blocks=[])
    doc = yaml.safe_load(text)
    assert doc["autoinstall"]["identity"]["password"] == "*"


def test_render_user_data_late_commands_is_empty_list(ubuntu_cfg_factory):
    # Phase 2 emits a placeholder bundle: no rules yet, no late-commands.
    # Phase 3 will populate this list from the ubuntu2404 rule registry.
    text = render_user_data(ubuntu_cfg_factory(), post_blocks=[])
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
    text = render_user_data(ubuntu_cfg_factory(hostname=hostname), post_blocks=[])
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


def test_render_user_data_empty_post_blocks_emits_inline_empty_list(ubuntu_cfg_factory):
    text = render_user_data(ubuntu_cfg_factory(), post_blocks=[])
    doc = yaml.safe_load(text)
    assert doc["autoinstall"]["late-commands"] == []


def test_render_user_data_one_post_block_emits_curtin_bash_entry(ubuntu_cfg_factory):
    block = PostBlock(rule_id="dummy_rule", body="echo hi")
    text = render_user_data(ubuntu_cfg_factory(), post_blocks=[block])
    doc = yaml.safe_load(text)
    late = doc["autoinstall"]["late-commands"]
    assert len(late) == 1
    entry = late[0]
    assert entry.startswith("curtin in-target --target=/target -- bash -c '")
    assert "# rule:dummy_rule" in entry
    assert "echo hi" in entry


def test_render_user_data_multi_line_post_block_round_trips_through_yaml(ubuntu_cfg_factory):
    body = "set -euxo pipefail\ncat > /etc/foo <<'__EOF__'\nhello\n__EOF__"
    block = PostBlock(rule_id="multi", body=body)
    text = render_user_data(ubuntu_cfg_factory(), post_blocks=[block])
    doc = yaml.safe_load(text)
    entry = doc["autoinstall"]["late-commands"][0]
    assert "set -euxo pipefail" in entry
    # shlex.quote converts single-quoted <<'__EOF__' to <<'"'"'__EOF__'"'"'
    assert "cat > /etc/foo <<" in entry
    assert "__EOF__" in entry
    assert "hello" in entry


def test_render_user_data_post_block_with_single_quotes_survives_shlex_quote(ubuntu_cfg_factory):
    block = PostBlock(rule_id="quoty", body="echo 'hello world'")
    text = render_user_data(ubuntu_cfg_factory(), post_blocks=[block])
    doc = yaml.safe_load(text)
    entry = doc["autoinstall"]["late-commands"][0]
    assert "echo" in entry
    # shlex.quote uses '"'"' style (not backslash) to escape single quotes
    assert '"\'"' in entry
    assert "hello world" in entry


def test_render_user_data_emits_cloud_init_users_block(ubuntu_cfg_factory):
    text = render_user_data(ubuntu_cfg_factory(admin="opsadmin"), post_blocks=[])
    doc = yaml.safe_load(text)
    users = doc["autoinstall"]["users"]
    assert isinstance(users, list) and len(users) == 1
    assert users[0]["name"] == "opsadmin"
    assert users[0]["shell"] == "/bin/bash"


def test_render_user_data_users_block_nopasswd_sudo(ubuntu_cfg_factory):
    text = render_user_data(ubuntu_cfg_factory(), post_blocks=[])
    doc = yaml.safe_load(text)
    assert doc["autoinstall"]["users"][0]["sudo"] == "ALL=(ALL) NOPASSWD:ALL"


def test_render_user_data_users_block_carries_authorized_keys(ubuntu_cfg_factory):
    cfg = ubuntu_cfg_factory()
    text = render_user_data(cfg, post_blocks=[])
    doc = yaml.safe_load(text)
    keys = doc["autoinstall"]["users"][0]["ssh_authorized_keys"]
    assert keys == cfg.user.admin.authorized_keys


def test_render_user_data_users_block_no_keys_emits_empty_list(ubuntu_cfg_factory):
    from ks_gen.config import AdminUser, HostConfig, System, User

    cfg = HostConfig(
        distro="ubuntu2404",
        system=System(hostname="u24-nokeys"),
        user=User(
            admin=AdminUser(
                name="ops",
                authorized_keys=[],
                sudo="nopasswd_yes",
                password="$6$abc$hash",
            )
        ),
    )
    text = render_user_data(cfg, post_blocks=[])
    doc = yaml.safe_load(text)
    assert doc["autoinstall"]["users"][0]["ssh_authorized_keys"] == []


def test_render_user_data_users_block_password_sudo_no(ubuntu_cfg_factory):
    from ks_gen.config import AdminUser, HostConfig, System, User

    cfg = HostConfig(
        distro="ubuntu2404",
        system=System(hostname="u24-pwsudo"),
        user=User(
            admin=AdminUser(
                name="ops",
                authorized_keys=["ssh-ed25519 AAAA a@b"],
                password="$6$abc$hash",
                sudo="nopasswd_no",
            )
        ),
    )
    text = render_user_data(cfg, post_blocks=[])
    doc = yaml.safe_load(text)
    assert doc["autoinstall"]["users"][0]["sudo"] == "ALL=(ALL) ALL"
