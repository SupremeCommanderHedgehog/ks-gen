"""Which SSH public-key algorithms survive a FIPS/STIG crypto policy.

A STIG host runs a FIPS-derived policy whose `PubkeyAcceptedAlgorithms` is an
allowlist, and ks-gen hosts have no console fallback — a key whose type is off
that list is a permanent lockout, not an inconvenience (#73).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

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

# Types a FIPS policy strips. Membership here never changes an accept/reject
# decision — a type absent from both tuples is equally unusable — it only lets
# an error message name the algorithm instead of saying "<unrecognized>".
# Only FIPS_USABLE can let a config through, which is why that one is pinned.
#
# Certificate types (`*-cert-v01@openssh.com`) are deliberately absent from
# both: the STIG PubkeyAcceptedAlgorithms list ks-gen writes on Ubuntu has no
# cert forms, so a cert-only key list cannot authenticate there. The ordinary
# `cert-authority ssh-rsa AAAA...` form parses as ssh-rsa and is unaffected.
FIPS_STRIPPED: tuple[str, ...] = (
    "ssh-ed25519",
    "sk-ssh-ed25519@openssh.com",
    "sk-ecdsa-sha2-nistp256@openssh.com",
    "ssh-dss",
)

_USABLE = frozenset(FIPS_USABLE)
_KNOWN = _USABLE | frozenset(FIPS_STRIPPED)


def _tokens(entry: str) -> Iterator[str]:
    """Split on whitespace, keeping a double-quoted option value as one token.

    A plain `str.split()` leaks the words of a quoted option value into the
    token stream, where an algorithm name inside one is read as the key's own
    type — `command="wrap ssh-rsa" ssh-ed25519 ...` would look usable under
    FIPS, which is the fail-open direction of #73.

    An unbalanced quote swallows the rest of the line, so key_type() returns
    None and the caller treats the key as unusable. That fails closed.
    """
    token: list[str] = []
    quoted = False
    escaped = False
    for ch in entry:
        if escaped:
            token.append(ch)
            escaped = False
        elif quoted and ch == "\\":
            token.append(ch)
            escaped = True
        elif ch == '"':
            quoted = not quoted
            token.append(ch)
        elif ch.isspace() and not quoted:
            if token:
                yield "".join(token)
                token = []
        else:
            token.append(ch)
    if token:
        yield "".join(token)


def key_type(entry: str) -> str | None:
    """The algorithm of one authorized_keys line, or None if unrecognised.

    Returns the first known-type token. That skips an options prefix
    (`from="10.0.0.1" ssh-rsa AAAA...`), cannot match inside the blob (base64
    has no `-`), and beats any comment, which follows the real type.
    """
    for token in _tokens(entry):
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
