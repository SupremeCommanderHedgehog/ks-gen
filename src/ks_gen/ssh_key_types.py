"""Which SSH public-key algorithms survive a FIPS/STIG crypto policy.

A STIG host runs a FIPS-derived policy whose `PubkeyAcceptedAlgorithms` is an
allowlist, and ks-gen hosts have no console fallback — a key whose type is off
that list is a permanent lockout, not an inconvenience (#73).
"""

from __future__ import annotations

from collections.abc import Iterable

# Ordered as sshd's PubkeyAcceptedAlgorithms preference list so
# rules/ubuntu2404/crypto_policy.py's STIG string can be pinned against it.
FIPS_USABLE: tuple[str, ...] = (
    "ssh-rsa",
    "rsa-sha2-512",
    "rsa-sha2-256",
    "ecdsa-sha2-nistp521",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp256",
)

# Types a FIPS policy strips. Named so key_type() recognises them as the type
# token instead of falling through to a later one.
FIPS_STRIPPED: tuple[str, ...] = (
    "ssh-ed25519",
    "sk-ssh-ed25519@openssh.com",
    "sk-ecdsa-sha2-nistp256@openssh.com",
    "ssh-dss",
)

_USABLE = frozenset(FIPS_USABLE)
_KNOWN = _USABLE | frozenset(FIPS_STRIPPED)


def key_type(entry: str) -> str | None:
    """The algorithm of one authorized_keys line, or None if unrecognised.

    Returns the first known-type token. That skips an options prefix
    (`from="10.0.0.1" ssh-rsa AAAA...`) without parsing options, cannot match
    inside the blob (base64 has no `-`), and beats any comment, which follows
    the real type.
    """
    for token in entry.split():
        if token in _KNOWN:
            return token
    return None


def has_fips_usable_key(entries: Iterable[str]) -> bool:
    """True if at least one entry can authenticate under a FIPS/STIG policy."""
    return any(key_type(e) in _USABLE for e in entries)


def describe_key_types(entries: Iterable[str]) -> str:
    """The key types present, deduped in order — for error messages."""
    seen: dict[str, None] = {}
    for e in entries:
        seen[key_type(e) or "<unrecognized>"] = None
    return ", ".join(seen) or "<none>"
