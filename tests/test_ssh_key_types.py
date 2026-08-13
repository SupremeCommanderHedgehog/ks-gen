import pytest

from ks_gen.ssh_key_types import (
    FIPS_STRIPPED,
    FIPS_USABLE,
    describe_key_types,
    has_fips_usable_key,
    key_type,
)


@pytest.mark.parametrize("algo", FIPS_USABLE)
def test_key_type_reads_every_usable_algorithm(algo):
    assert key_type(f"{algo} AAAAB3Nz ops@bastion") == algo


@pytest.mark.parametrize("algo", FIPS_STRIPPED)
def test_key_type_reads_every_stripped_algorithm(algo):
    assert key_type(f"{algo} AAAAC3Nz ops@bastion") == algo


def test_key_type_skips_an_options_prefix():
    entry = 'from="10.0.0.1",no-agent-forwarding ssh-rsa AAAAB3Nz ops@bastion'
    assert key_type(entry) == "ssh-rsa"


def test_key_type_ignores_a_type_name_in_the_comment():
    # The real type token comes first; a comment mentioning another algorithm
    # must not win, or an Ed25519-only config reads as usable.
    assert key_type("ssh-ed25519 AAAAC3Nz my ssh-rsa backup key") == "ssh-ed25519"


def test_key_type_is_not_fooled_by_an_algorithm_name_inside_an_option_value():
    """The fail-open direction: a quoted option value must not supply the type.

    A plain str.split() reads `ssh-rsa` out of the forced command and calls an
    Ed25519-only key list usable under FIPS — the exact lockout #73 prevents.
    """
    entry = 'command="/usr/local/bin/wrap ssh-rsa mode" ssh-ed25519 AAAAC3Nz a@b'
    assert key_type(entry) == "ssh-ed25519"
    assert not has_fips_usable_key([entry])


def test_key_type_is_not_fooled_by_a_stripped_algorithm_in_an_option_value():
    """The fail-closed direction: a usable key must not be rejected."""
    entry = 'environment="NOTE=my ssh-ed25519 key" ssh-rsa AAAAB3Nz a@b'
    assert key_type(entry) == "ssh-rsa"
    assert has_fips_usable_key([entry])


def test_key_type_handles_an_escaped_quote_inside_an_option_value():
    entry = 'command="echo \\"ssh-rsa\\"" ssh-ed25519 AAAAC3Nz a@b'
    assert key_type(entry) == "ssh-ed25519"


def test_an_unbalanced_quote_fails_closed():
    # The rest of the line is swallowed into one token, so no type is found
    # and the key counts as unusable rather than as whatever it mentions.
    assert key_type('command="unterminated ssh-rsa AAAAB3Nz a@b') is None


def test_cert_authority_prefixed_keys_read_as_their_base_type():
    assert key_type("cert-authority ssh-rsa AAAAB3Nz ca@bastion") == "ssh-rsa"


def test_certificate_key_types_are_not_usable():
    # Deliberate: the STIG PubkeyAcceptedAlgorithms list ks-gen writes on
    # Ubuntu carries no cert forms, so a cert-only list cannot authenticate.
    entry = "ecdsa-sha2-nistp256-cert-v01@openssh.com AAAAB3Nz a@b"
    assert key_type(entry) is None
    assert not has_fips_usable_key([entry])


def test_key_type_returns_none_for_an_unrecognized_type():
    assert key_type("ssh-edd25519 AAAAC3Nz typo@bastion") is None
    assert key_type("") is None


def test_has_fips_usable_key_needs_at_least_one_usable_entry():
    assert not has_fips_usable_key(["ssh-ed25519 AAAAC3Nz a@b"])
    assert not has_fips_usable_key([])
    assert has_fips_usable_key(["ssh-ed25519 AAAAC3Nz a@b", "ssh-rsa AAAAB3Nz a@b"])


def test_has_fips_usable_key_rejects_unknown_types():
    # Allowlist semantics: an unrecognized type cannot appear in sshd's
    # PubkeyAcceptedAlgorithms, so it does not count as a way in.
    assert not has_fips_usable_key(["ssh-edd25519 AAAAC3Nz typo@bastion"])


def test_describe_key_types_dedupes_in_order():
    entries = [
        "ssh-ed25519 A a@b",
        "ssh-ed25519 B b@c",
        "sk-ssh-ed25519@openssh.com C c@d",
        "garbage D d@e",
    ]
    assert describe_key_types(entries) == (
        "ssh-ed25519, sk-ssh-ed25519@openssh.com, <unrecognized>"
    )


def test_describe_key_types_of_nothing():
    assert describe_key_types([]) == "<none>"


def test_ubuntu_stig_pubkey_list_matches_fips_usable():
    """Pin the allowlist against the rule that writes it into sshd_config.

    ks-gen writes PubkeyAcceptedAlgorithms itself on Ubuntu, so if that list
    gains or loses an algorithm the lockout check must learn about it too.
    """
    from ks_gen.rules.ubuntu2404.crypto_policy import _SSH_PUBKEYS

    assert set(_SSH_PUBKEYS["STIG"].split(",")) == set(FIPS_USABLE)
