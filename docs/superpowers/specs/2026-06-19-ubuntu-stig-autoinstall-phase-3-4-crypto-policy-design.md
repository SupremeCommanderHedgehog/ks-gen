# Phase 3.4 — `crypto_policy` port to ubuntu2404

**Parent:** #81 ubuntu STIG autoinstall.
**Previous phases on this workstream:** 3.0 admin_user_and_keys + ssh_keep_open (#94), 3.1 banner_text (#101), 3.2 ssh_config_apply (#102), 3.3 time_servers (#104).
**Sibling future work:** a future `pro_attach` rule will own Ubuntu Pro attach + `pro enable fips-updates`. This rule writes the algorithm lists; that future rule provides the FIPS validation underneath.

## Goal

Port the `crypto_policy` rule to ubuntu2404 so the generated autoinstall
pins crypto across three components (SSH, OpenSSL, GnuTLS) via
`cfg.crypto.policy`. STIG mode emits the algorithm lists the DISA
Ubuntu 24.04 STIG (v1r5) requires; FIPS validation is delegated to a
future `pro_attach` rule.

## Non-goals

- **Ubuntu Pro attach + FIPS enable.** That's a future `pro_attach`
  rule. This rule writes config but does NOT call `pro attach` or
  `pro enable fips-updates`.
- **libgcrypt configuration.** Ubuntu has no civilian-equivalent knob;
  libgcrypt config is owned by the embedding application, not a
  system-wide policy file. Emitting a comment-only marker would be
  noise. Omit entirely.
- **ssg-ubuntu2404-ds.xml tailoring + exception text.** Deferred to the
  coordinated audit-story PR per the established phase-3.x pattern.
- **System-wide RHEL-style umbrella knob.** Ubuntu has no
  `update-crypto-policies` equivalent — three separate component config
  files is the only path.

## Architecture

One new rule module + one new test file. The shared
`src/ks_gen/rules/_meta/crypto_policy.py` is unchanged (already
distro-agnostic; its note about runtime-computed summary/reason
survives).

`emit_post` composes three independent component blocks. They run in
sequence, write three separate config files, and don't share state.
Splitting per component (instead of one giant string template) means a
future change to the SSH cipher list doesn't risk corrupting the
OpenSSL block.

```python
def _emit(cfg: HostConfig) -> str:
    return "".join([
        _emit_ssh(cfg),
        _emit_openssl(cfg),
        _emit_gnutls(cfg),
    ])
```

The rule plugs into the existing ubuntu2404 bundle pipeline:
- `emit_post` contributes a `# rule:crypto_policy` block to
  `late-commands`.
- `emit_packages` returns `[]` — `openssh-server`, `openssl`, and
  `libgnutls30` all ship in Ubuntu Server's minimal install.

No changes to `writer.py`, `skeleton.py`, the user-data template, or
the config schema.

## Files touched

- **Create:** `src/ks_gen/rules/ubuntu2404/crypto_policy.py`
- **Create:** `tests/rules/test_ubuntu2404_crypto_policy.py`
- **Modify:** `tests/golden/__snapshots__/test_ubuntu_minimal.ambr`
  (snapshot regen)

## Per-policy mapping

The three policies (`STIG`, `MODERN`, `FUTURE`) map to per-component
algorithm sets. STIG = "DISA Ubuntu 24.04 STIG v1r5"; MODERN = "civilian
defaults with modern algorithms"; FUTURE = "strictest civilian, drop
SHA1/SHA256-only fallbacks".

### SSH — `/etc/ssh/sshd_config.d/10-ks-gen-crypto.conf`

Numeric prefix `10-` puts this file **after** phase 3.2's `00-ks-gen.conf`
(which owns Port/PermitRootLogin/PasswordAuth/etc.). They don't
conflict on directives — `00-ks-gen.conf` doesn't set Ciphers/Kex/MACs
— but lex-ordering ensures crypto wins if a future maintainer ever
adds an overlap.

Directives emitted (all five always present; values change per policy):

| Directive | STIG | MODERN | FUTURE |
|---|---|---|---|
| `Ciphers` | `aes256-gcm@openssh.com,aes128-gcm@openssh.com,aes256-ctr,aes192-ctr,aes128-ctr` | STIG + `chacha20-poly1305@openssh.com` (prefixed) | MODERN minus `aes128-ctr,aes192-ctr` |
| `KexAlgorithms` | `ecdh-sha2-nistp521,ecdh-sha2-nistp384,ecdh-sha2-nistp256,diffie-hellman-group16-sha512,diffie-hellman-group14-sha256` | STIG + `curve25519-sha256,curve25519-sha256@libssh.org` (prefixed) | MODERN minus `diffie-hellman-group14-sha256` |
| `MACs` | `hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com,hmac-sha2-512,hmac-sha2-256` | same as STIG | MODERN minus `hmac-sha2-256,hmac-sha2-512` (only ETM variants) |
| `HostKeyAlgorithms` | `ssh-rsa,rsa-sha2-512,rsa-sha2-256,ecdsa-sha2-nistp521,ecdsa-sha2-nistp384,ecdsa-sha2-nistp256` | STIG + `ssh-ed25519` (prefixed) | MODERN minus `ssh-rsa,ecdsa-sha2-nistp256` |
| `PubkeyAcceptedAlgorithms` | same shape as HostKeyAlgorithms | same shape as HostKeyAlgorithms | same shape as HostKeyAlgorithms |

STIG mode also writes a banner comment as the first line of the file:

```
# WARNING: STIG-aligned algorithms but NOT FIPS-validated. For
# FIPS-validated crypto, add the future pro_attach rule to enable
# Ubuntu Pro `fips-updates`.
```

MODERN/FUTURE: no banner.

Late-command tail: `sshd -t` validates the resulting config before
late-commands finish (mirrors phase 3.2). If `sshd -t` fails, the
install fails fast rather than producing a host that can't accept SSH.

For non-STIG policies, append `ssh-keygen -A` to regenerate any missing
host keys (matches alma9 — Ed25519 isn't produced under FIPS so when
moving from STIG→MODERN you'd be missing it).

### OpenSSL — `/etc/ssl/openssl.cnf.d/10-ks-gen.conf`

Ubuntu 24.04's `/etc/ssl/openssl.cnf` ships with an `.include` directive
that loads `*.cnf` from `/etc/ssl/openssl.cnf.d/`. ks-gen drops its
file there; no main-cnf edit.

Two directives only:

| Directive | STIG | MODERN | FUTURE |
|---|---|---|---|
| `MinProtocol` (in `[system_default_sect]`) | `TLSv1.2` | `TLSv1.2` | `TLSv1.3` |
| `CipherString` (in `[system_default_sect]`) | `DEFAULT@SECLEVEL=2` | `DEFAULT@SECLEVEL=2` | `DEFAULT@SECLEVEL=3` |

STIG and MODERN produce identical OpenSSL output by design: without the
FIPS provider (Ubuntu Pro), there's no system-OpenSSL knob that
distinguishes "STIG-aligned" from "modern civilian" — both are simply
"better than the SECLEVEL=1 default." The differentiation lives in SSH
(stricter algorithm whitelist) and GnuTLS (no difference at this scope).

File body shape:

```ini
[default_sect]
activate = 1
[system_default_sect]
MinProtocol = TLSv1.2
CipherString = DEFAULT@SECLEVEL=2
```

(The `[default_sect]`/`activate = 1` lines are required for the
override to take effect — they re-enable the default provider so the
overridden `system_default_sect` is read.)

Late-command tail: `install -d -m 755 /etc/ssl/openssl.cnf.d` belt for
idempotent re-run safety (same pattern as time_servers' `install -d
-m 755 /etc/chrony`).

### GnuTLS — `/etc/gnutls/default-priorities`

One-line file containing the priority string. Debian/Ubuntu convention.

| Policy | Priority |
|---|---|
| STIG | `SECURE128` |
| MODERN | `SECURE128` |
| FUTURE | `SECURE256` |

Late-command tail: `install -d -m 755 /etc/gnutls` belt.

## Rule scaffolding (matches phase 3.3)

```python
"""ubuntu2404 system-wide crypto policy.

Pins crypto across SSH (sshd_config drop-in), OpenSSL
(/etc/ssl/openssl.cnf.d/), and GnuTLS (/etc/gnutls/default-priorities)
based on cfg.crypto.policy. FIPS validation is owned by a future
pro_attach rule; this rule writes algorithm lists, not entitlements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import crypto_policy as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig, CryptoPolicy


# Algorithm sets per policy (literal lists; readability matters more than DRY here).
_SSH_CIPHERS = {
    "STIG":   "aes256-gcm@openssh.com,aes128-gcm@openssh.com,aes256-ctr,aes192-ctr,aes128-ctr",
    "MODERN": "chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com,aes256-ctr,aes192-ctr,aes128-ctr",
    "FUTURE": "chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com,aes256-ctr",
}
# _SSH_KEX, _SSH_MACS, _SSH_HOSTKEYS, _SSH_PUBKEYS follow the same dict-of-three-strings
# shape. The per-policy mapping table above is the source of truth for every value;
# the implementation plan will spell out all five lookup tables verbatim.

_OPENSSL_MIN_PROTO = {"STIG": "TLSv1.2", "MODERN": "TLSv1.2", "FUTURE": "TLSv1.3"}
_OPENSSL_CIPHERSTR = {"STIG": "DEFAULT@SECLEVEL=2", "MODERN": "DEFAULT@SECLEVEL=2", "FUTURE": "DEFAULT@SECLEVEL=3"}

_GNUTLS_PRIORITY = {"STIG": "SECURE128", "MODERN": "SECURE128", "FUTURE": "SECURE256"}


def _emit_ssh(cfg: HostConfig) -> str:
    policy = cfg.crypto.policy.value
    banner = ""
    if policy == "STIG":
        banner = (
            "# WARNING: STIG-aligned algorithms but NOT FIPS-validated. For\n"
            "# FIPS-validated crypto, add the future pro_attach rule to enable\n"
            "# Ubuntu Pro `fips-updates`.\n"
        )
    body = f"""\
{banner}Ciphers {_SSH_CIPHERS[policy]}
KexAlgorithms {_SSH_KEX[policy]}
MACs {_SSH_MACS[policy]}
HostKeyAlgorithms {_SSH_HOSTKEYS[policy]}
PubkeyAcceptedAlgorithms {_SSH_PUBKEYS[policy]}
"""
    tail = "sshd -t"
    if policy != "STIG":
        tail = "ssh-keygen -A\nsshd -t"
    return f"""\
# SSH crypto policy ({policy})
install -d -m 755 /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/10-ks-gen-crypto.conf <<'__KS_GEN_EOF__'
{body}__KS_GEN_EOF__
chmod 600 /etc/ssh/sshd_config.d/10-ks-gen-crypto.conf
{tail}
"""


def _emit_openssl(cfg: HostConfig) -> str:
    policy = cfg.crypto.policy.value
    return f"""\
# OpenSSL crypto policy ({policy})
install -d -m 755 /etc/ssl/openssl.cnf.d
cat > /etc/ssl/openssl.cnf.d/10-ks-gen.conf <<'__KS_GEN_EOF__'
[default_sect]
activate = 1
[system_default_sect]
MinProtocol = {_OPENSSL_MIN_PROTO[policy]}
CipherString = {_OPENSSL_CIPHERSTR[policy]}
__KS_GEN_EOF__
chmod 644 /etc/ssl/openssl.cnf.d/10-ks-gen.conf
"""


def _emit_gnutls(cfg: HostConfig) -> str:
    policy = cfg.crypto.policy.value
    return f"""\
# GnuTLS crypto policy ({policy})
install -d -m 755 /etc/gnutls
cat > /etc/gnutls/default-priorities <<'__KS_GEN_EOF__'
{_GNUTLS_PRIORITY[policy]}
__KS_GEN_EOF__
chmod 644 /etc/gnutls/default-priorities
"""


def _emit(cfg: HostConfig) -> str:
    return "".join([_emit_ssh(cfg), _emit_openssl(cfg), _emit_gnutls(cfg)])


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        # Deferred: ssg-ubuntu2404-ds.xml crypto rule survey lands in the audit-story PR.
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        # Deferred: paired with emit_tailoring above; see audit-story PR.
        return None


RULE: Rule = cast(Rule, _Rule())
```

## Tests (21)

All use the `ubuntu_cfg_factory` fixture, with policy overrides via
`Crypto(policy=CryptoPolicy.X)`. Module-level imports.

### Per-component file path
1. `test_ssh_block_writes_sshd_config_drop_in_at_10_prefix`
2. `test_openssl_block_writes_under_openssl_cnf_d`
3. `test_gnutls_block_writes_default_priorities`

### SSH per-policy
4. `test_ssh_stig_emits_no_chacha20_no_curve25519` (STIG)
5. `test_ssh_modern_emits_chacha20_and_curve25519` (MODERN, default)
6. `test_ssh_future_drops_sha1_and_short_macs` (FUTURE)
7. `test_ssh_stig_emits_warning_banner_comment` (STIG)
8. `test_ssh_modern_does_not_emit_warning_banner_comment` (MODERN)
9. `test_ssh_non_stig_emits_ssh_keygen_a` (MODERN — regen missing Ed25519)
10. `test_ssh_stig_does_not_emit_ssh_keygen_a` (STIG — FIPS already produced its keys)
11. `test_ssh_block_runs_sshd_t_validation`
12. `test_ssh_block_chmod_600`

### OpenSSL per-policy
13. `test_openssl_stig_minproto_tlsv1_2_seclevel_2`
14. `test_openssl_future_minproto_tlsv1_3_seclevel_3`

### GnuTLS per-policy
15. `test_gnutls_stig_emits_secure128`
16. `test_gnutls_future_emits_secure256`

### Protocol contract (mirror phase 3.3)
16. `test_applies_always_true`
17. `test_emit_packages_returns_empty` — all 3 components are in Ubuntu Server's minimal install
18. `test_emit_tailoring_returns_empty_deferred`
19. `test_exception_entry_returns_none_deferred`
20. `test_id_and_summary_come_from_shared_meta`
21. `test_depends_on_is_empty`

## Snapshot regen

After tests pass, run `pytest tests/golden/ --snapshot-update -k ubuntu_minimal`.

Expected diff (and ONLY these changes):

1. New `# rule:crypto_policy ──────────...` band in `late-commands`
   containing the three component blocks (SSH heredoc → OpenSSL heredoc
   → GnuTLS heredoc), evaluated for the default `MODERN` policy.
2. "Applied rules: N" header in late-commands intro bumps from 5 to 6
   (phase 3.3 already brought it from 4 to 5).

No `autoinstall.packages:` changes (this rule's `emit_packages` is
empty). No alma9 snapshots affected.

### Merge-order assumption

The 5 → 6 count assumes this branch sits on main at `4b8644b`
(post-v0.17.0, includes phases 3.0/3.1/3.2/3.3 = 5 ubuntu rules). If
unrelated work landed first that added another ubuntu2404 rule,
regenerate the snapshot and confirm the diff is "+1 your rule, nothing
else."

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Operator reads "STIG" and assumes FIPS-validated | Banner comment in the SSH drop-in is unambiguous; spec calls it out; future `pro_attach` rule closes the gap. |
| Cipher list drift from DISA STIG v1r6+ | Algorithm sets are literal constants at the top of the rule module; easy to update when a new STIG revision lands. |
| `sshd -t` rejects the resulting config | `sshd -t` runs in late-command before reboot; install fails fast rather than producing an unreachable host. |
| OpenSSL `.cnf.d/` not loaded on Ubuntu 24.04 | Verified: `/etc/ssl/openssl.cnf` ships with `.include /etc/ssl/openssl.cnf.d` (or similar — the implementer should confirm during testing and adjust if the path differs in a point release). |
| GnuTLS `default-priorities` ignored by some apps | True — Ubuntu's gnutls28 reads it, but applications can override. Documented limitation; matches alma9 behavior on the equivalent rule. |
| Phase 3.2's `00-ks-gen.conf` and this rule's `10-ks-gen-crypto.conf` conflict | They don't — disjoint directive sets. Numeric ordering protects future maintainers from accidental overlap. |

## CI parity check before push

Per `CLAUDE.md`, run the full chain locally:

```bash
ruff check src tests \
  && ruff format --check src tests \
  && mypy \
  && pytest -q
```

If `ruff format --check` fails (heredoc indentation is the usual
culprit), fix with `ruff format src tests` and re-verify.

## Out of scope (deferred to other work)

- `emit_tailoring`: ssg-ubuntu2404-ds.xml crypto/SSH rule IDs (TBD by
  the audit-story survey).
- `exception_entry`: English justification for the civilian-deviation
  exceptions.
- `pro_attach` rule: Ubuntu Pro attach + FIPS enable. Likely a phase
  3.4.5 or 3.5 sibling.
- libgcrypt: no civilian-equivalent config knob; not emitted at all.
