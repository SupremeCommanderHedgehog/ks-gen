"""#73: crypto.policy STIG plus keys FIPS strips is an unrecoverable lockout."""

import pytest
from pydantic import ValidationError

from ks_gen.config import HostConfig

_ED25519 = "ssh-ed25519 AAAAC3Nz ops@bastion"
_RSA = "ssh-rsa AAAAB3Nz ops@bastion"


def _payload(keys, policy="STIG", **admin_extra):
    return {
        "system": {"hostname": "stig01.example.com"},
        "user": {
            "admin": {
                "name": "opsadmin",
                "authorized_keys": keys,
                "sudo": "nopasswd_yes",
                **admin_extra,
            }
        },
        "crypto": {"policy": policy},
    }


def test_stig_with_only_an_ed25519_key_is_rejected():
    with pytest.raises(ValidationError) as e:
        HostConfig.model_validate(_payload([_ED25519]))
    msg = str(e.value)
    assert "user.admin.authorized_keys" in msg
    assert "ssh-ed25519" in msg
    assert "unreachable" in msg


def test_stig_with_an_rsa_key_alongside_ed25519_is_accepted():
    cfg = HostConfig.model_validate(_payload([_ED25519, _RSA]))
    assert cfg.user.admin.authorized_keys == [_ED25519, _RSA]


def test_stig_with_an_ecdsa_key_is_accepted():
    HostConfig.model_validate(_payload(["ecdsa-sha2-nistp384 AAAAE2Vj ops@bastion"]))


def test_stig_with_an_options_prefixed_rsa_key_is_accepted():
    entry = 'from="10.0.0.1",no-pty ssh-rsa AAAAB3Nz ops@bastion'
    HostConfig.model_validate(_payload([entry]))


def test_stig_with_a_typoed_key_type_is_rejected():
    with pytest.raises(ValidationError) as e:
        HostConfig.model_validate(_payload(["ssh-edd25519 AAAAC3Nz ops@bastion"]))
    assert "<unrecognized>" in str(e.value)


def test_stig_is_not_fooled_by_a_key_type_named_in_the_comment():
    entry = "ssh-ed25519 AAAAC3Nz my ssh-rsa backup key"
    with pytest.raises(ValidationError):
        HostConfig.model_validate(_payload([entry]))


def test_stig_with_an_unlocked_admin_is_accepted():
    """A password means the account is not passwd -l'd, so console login and
    (if enabled) password SSH remain. Dead keys are then not a lockout."""
    HostConfig.model_validate(_payload([_ED25519], password="$6$salt$hash", sudo="nopasswd_no"))


@pytest.mark.parametrize("policy", ["MODERN", "FUTURE"])
def test_non_stig_policies_still_accept_ed25519_only(policy):
    HostConfig.model_validate(_payload([_ED25519], policy=policy))


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
