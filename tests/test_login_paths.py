"""#73/#76: a host must leave at least one admin login path open.

Root is always `rootpw --lock`, so the admin account is the only way in.
The three paths and their preconditions are restated in `_expected_ok`
below — deliberately independent of the validator, so adding a path to
`config.py` without updating the table fails here.
"""

import itertools

import pytest
import yaml
from pydantic import ValidationError

from ks_gen.config import HostConfig
from ks_gen.loader import ConfigError, ExitCode, load_host_config
from ks_gen.ssh_key_types import has_fips_usable_key

_ED25519 = "ssh-ed25519 AAAAC3Nz ops@bastion"
_RSA = "ssh-rsa AAAAB3Nz ops@bastion"
_HASH = "$6$salt$hash"


def _payload(
    keys,
    policy="STIG",
    password=None,
    password_authentication=False,
    console_login_only=False,
):
    return {
        "system": {"hostname": "stig01.example.com"},
        "user": {
            "admin": {
                "name": "opsadmin",
                "authorized_keys": keys,
                # Always nopasswd_yes: _admin_credential_mutex requires it for
                # a locked admin and permits it for an unlocked one, so it
                # keeps that validator out of this table.
                "sudo": "nopasswd_yes",
                **({"password": password} if password is not None else {}),
            }
        },
        "crypto": {"policy": policy},
        "ssh": {"password_authentication": password_authentication},
        "overrides": {"console_login_only": console_login_only},
    }


def _expected_ok(policy, keys, password, password_authentication, console_login_only):
    """The three-path table, restated independently of the implementation."""
    if password is None and not keys:
        return False  # AdminUser._keys_or_password
    if console_login_only and password is None:
        return False  # a passwd -l'd admin cannot log in at a console either
    pubkey = has_fips_usable_key(keys) if policy == "STIG" else bool(keys)
    ssh_password = password is not None and password_authentication
    console = password is not None and console_login_only
    return pubkey or ssh_password or console


_POLICIES = ["STIG", "MODERN", "FUTURE"]
_KEY_SETS = [[], [_ED25519], [_RSA], [_ED25519, _RSA]]
_PASSWORDS = [None, _HASH]
_CASES = list(itertools.product(_POLICIES, _KEY_SETS, _PASSWORDS, [False, True], [False, True]))


@pytest.mark.parametrize("policy,keys,password,password_authentication,console", _CASES)
def test_login_path_table(policy, keys, password, password_authentication, console):
    payload = _payload(
        keys,
        policy=policy,
        password=password,
        password_authentication=password_authentication,
        console_login_only=console,
    )
    expected = _expected_ok(policy, keys, password, password_authentication, console)
    if expected:
        HostConfig.model_validate(payload)
    else:
        with pytest.raises(ValidationError):
            HostConfig.model_validate(payload)


def test_locked_admin_with_stig_stripped_keys_names_the_key_types():
    with pytest.raises(ValidationError) as e:
        HostConfig.model_validate(_payload([_ED25519]))
    msg = str(e.value)
    assert "unreachable" in msg
    assert "user.admin.authorized_keys" in msg
    assert "ssh-ed25519" in msg
    assert "passwd -l" in msg


def test_password_with_no_keys_names_every_closed_path():
    """#76 proper: the path this used to let through."""
    with pytest.raises(ValidationError) as e:
        HostConfig.model_validate(_payload([], policy="MODERN", password=_HASH))
    msg = str(e.value)
    assert "user.admin.authorized_keys is empty" in msg
    assert "ssh.password_authentication is false" in msg
    assert "overrides.console_login_only is false" in msg


def test_password_with_stig_stripped_keys_is_rejected():
    """The variant #76 omits: a password does not rescue unusable keys when
    password SSH is off and no console is declared."""
    with pytest.raises(ValidationError) as e:
        HostConfig.model_validate(_payload([_ED25519], password=_HASH))
    assert "crypto.policy=STIG" in str(e.value)


def test_console_login_only_without_a_password_is_rejected():
    with pytest.raises(ValidationError) as e:
        HostConfig.model_validate(_payload([_ED25519], console_login_only=True))
    msg = str(e.value)
    assert "overrides.console_login_only" in msg
    assert "user.admin.password" in msg


def test_lockout_surfaces_as_config_invalid_not_rule_conflict(tmp_path):
    """load_host_config picks the exit code by string-matching the message, so
    a lockout that happened to name MODERN and fips_mode would exit 3."""
    path = tmp_path / "host.yaml"
    path.write_text(yaml.safe_dump(_payload([], policy="MODERN", password=_HASH)), encoding="utf-8")
    with pytest.raises(ConfigError) as e:
        load_host_config(path, sets=[])
    assert e.value.exit_code == ExitCode.CONFIG_INVALID


def test_console_login_only_opens_the_console_path():
    cfg = HostConfig.model_validate(_payload([], password=_HASH, console_login_only=True))
    assert cfg.overrides.console_login_only


def test_password_authentication_opens_the_password_path():
    HostConfig.model_validate(_payload([], password=_HASH, password_authentication=True))


def test_console_login_only_defaults_off():
    cfg = HostConfig.model_validate(_payload([_RSA]))
    assert cfg.overrides.console_login_only is False


def test_stig_with_an_ecdsa_key_is_accepted():
    HostConfig.model_validate(_payload(["ecdsa-sha2-nistp384 AAAAE2Vj ops@bastion"]))


def test_stig_with_an_options_prefixed_rsa_key_is_accepted():
    entry = 'from="10.0.0.1",no-pty ssh-rsa AAAAB3Nz ops@bastion'
    HostConfig.model_validate(_payload([entry]))


def test_stig_is_not_fooled_by_an_algorithm_name_in_a_forced_command():
    """End-to-end guard against the fail-open parse: the option value mentions
    ssh-rsa, but the only real key is Ed25519, so the host is unreachable."""
    entry = 'command="/usr/local/bin/wrap ssh-rsa mode" ssh-ed25519 AAAAC3Nz a@b'
    with pytest.raises(ValidationError) as e:
        HostConfig.model_validate(_payload([entry]))
    assert "ssh-ed25519" in str(e.value)


def test_stig_with_a_typoed_key_type_is_rejected():
    with pytest.raises(ValidationError) as e:
        HostConfig.model_validate(_payload(["ssh-edd25519 AAAAC3Nz ops@bastion"]))
    assert "<unrecognized>" in str(e.value)


def test_stig_is_not_fooled_by_a_key_type_named_in_the_comment():
    entry = "ssh-ed25519 AAAAC3Nz my ssh-rsa backup key"
    with pytest.raises(ValidationError):
        HostConfig.model_validate(_payload([entry]))


def _containers_payload(user_keys, enabled=True, policy="STIG"):
    payload = _payload([_RSA], policy=policy)
    payload["containers"] = {
        "enabled": enabled,
        "users": [{"name": "webapp", "authorized_keys": user_keys}],
    }
    return payload


def test_stig_container_user_with_only_ed25519_is_rejected():
    with pytest.raises(ValidationError) as e:
        HostConfig.model_validate(_containers_payload([_ED25519]))
    msg = str(e.value)
    assert "containers.users[0]" in msg
    assert "webapp" in msg
    assert "ssh-ed25519" in msg


def test_stig_container_user_with_an_rsa_key_is_accepted():
    HostConfig.model_validate(_containers_payload([_ED25519, _RSA]))


def test_disabled_containers_are_not_checked():
    """`containers.enabled: false` provisions no accounts, matching how
    _validate_users_distinct short-circuits."""
    HostConfig.model_validate(_containers_payload([_ED25519], enabled=False))


def test_non_stig_container_users_still_accept_ed25519_only():
    HostConfig.model_validate(_containers_payload([_ED25519], policy="MODERN"))
