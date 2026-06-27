# Phase 3.4 — `crypto_policy` port to ubuntu2404 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the `crypto_policy` rule to ubuntu2404 so the generated autoinstall pins SSH, OpenSSL, and GnuTLS crypto based on `cfg.crypto.policy`.

**Architecture:** One new rule module + one new test file. The rule's `emit_post` composes three independent component blocks (SSH drop-in, OpenSSL drop-in, GnuTLS priority file) via `_emit_ssh`, `_emit_openssl`, `_emit_gnutls`. Shared `_meta/crypto_policy.py` is untouched. Same emit_post-only + defer-tailoring/exception pattern as phases 3.1/3.2/3.3.

**Tech Stack:** Python 3.11+, pydantic v2, jinja2, syrupy snapshots, pytest, ruff, mypy. Same toolchain as prior phases.

**Spec:** `docs/superpowers/specs/2026-06-19-ubuntu-stig-autoinstall-phase-3-4-crypto-policy-design.md`

**Branch:** `feat/phase-3-4-crypto-policy` (already created off main at `4b8644b`; spec already committed at `81eb71d`).

---

## Reference patterns

The implementer should mirror these established files. They're authoritative for code style, comment voice, and test shape:

- **alma9 sibling:** `src/ks_gen/rules/alma9/crypto_policy.py` — semantic source (system-wide policy + ssh-keygen -A regen for non-STIG).
- **Closest ubuntu2404 siblings:**
  - `src/ks_gen/rules/ubuntu2404/time_servers.py` (phase 3.3) for the `_emit(cfg)` top-level helper + `_Rule` dataclass + `RULE: Rule = cast(Rule, _Rule())` module-level binding + `Deferred:` comment wording.
  - `src/ks_gen/rules/ubuntu2404/ssh_config_apply.py` (phase 3.2) for the sshd_config drop-in pattern, `install -d`, `chmod 600`, and `sshd -t` validation tail.
- **Test sibling:** `tests/rules/test_ubuntu2404_time_servers.py` — module-level `from ... import RULE` at top, local `from ks_gen.config import X` inside per-test override functions.

The `ubuntu_cfg_factory` fixture is in `tests/conftest.py`. Default invocation yields a HostConfig with `distro="ubuntu2404"`, `hostname="u2404-host"`, admin user `"ops"`. Override `cfg.crypto.policy` via:

```python
from ks_gen.config import Crypto, CryptoPolicy
cfg = ubuntu_cfg_factory().model_copy(update={"crypto": Crypto(policy=CryptoPolicy.STIG)})
```

The default `cfg.crypto.policy` is `CryptoPolicy.MODERN` (see `src/ks_gen/config.py:433-434`).

---

## Task 1: Rule skeleton (all three component blocks, all three policies)

Create the rule file with all five SSH lookup tables, OpenSSL + GnuTLS tables, and the three component emitters in one shot. Create the test file with one failing path test that proves wiring works. The rule body has too many literal cipher strings to incrementally build out — putting it all in one TDD step keeps the lookup tables together where they're easy to review.

**Files:**
- Create: `src/ks_gen/rules/ubuntu2404/crypto_policy.py`
- Create: `tests/rules/test_ubuntu2404_crypto_policy.py`

- [ ] **Step 1: Write the failing test**

Create `tests/rules/test_ubuntu2404_crypto_policy.py`:

```python
from ks_gen.rules.ubuntu2404.crypto_policy import RULE


def test_ssh_block_writes_sshd_config_drop_in_at_10_prefix(ubuntu_cfg_factory):
    # Numeric prefix 10- puts this file AFTER phase 3.2's 00-ks-gen.conf,
    # so crypto wins on conflict if any future maintainer adds an overlap.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/ssh/sshd_config.d/10-ks-gen-crypto.conf" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/rules/test_ubuntu2404_crypto_policy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ks_gen.rules.ubuntu2404.crypto_policy'`

- [ ] **Step 3: Create the rule module**

Create `src/ks_gen/rules/ubuntu2404/crypto_policy.py` (exact content; the cipher string literals are the source of truth for this rule, derived from DISA Ubuntu 24.04 STIG v1r5 + civilian extensions):

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
    from ks_gen.config import HostConfig


_SSH_CIPHERS = {
    "STIG": "aes256-gcm@openssh.com,aes128-gcm@openssh.com,aes256-ctr,aes192-ctr,aes128-ctr",
    "MODERN": "chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com,aes256-ctr,aes192-ctr,aes128-ctr",
    "FUTURE": "chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com,aes256-ctr",
}

_SSH_KEX = {
    "STIG": "ecdh-sha2-nistp521,ecdh-sha2-nistp384,ecdh-sha2-nistp256,diffie-hellman-group16-sha512,diffie-hellman-group14-sha256",
    "MODERN": "curve25519-sha256,curve25519-sha256@libssh.org,ecdh-sha2-nistp521,ecdh-sha2-nistp384,ecdh-sha2-nistp256,diffie-hellman-group16-sha512,diffie-hellman-group14-sha256",
    "FUTURE": "curve25519-sha256,curve25519-sha256@libssh.org,ecdh-sha2-nistp521,ecdh-sha2-nistp384,ecdh-sha2-nistp256,diffie-hellman-group16-sha512",
}

_SSH_MACS = {
    "STIG": "hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com,hmac-sha2-512,hmac-sha2-256",
    "MODERN": "hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com,hmac-sha2-512,hmac-sha2-256",
    "FUTURE": "hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com",
}

_SSH_HOSTKEYS = {
    "STIG": "ssh-rsa,rsa-sha2-512,rsa-sha2-256,ecdsa-sha2-nistp521,ecdsa-sha2-nistp384,ecdsa-sha2-nistp256",
    "MODERN": "ssh-ed25519,ssh-rsa,rsa-sha2-512,rsa-sha2-256,ecdsa-sha2-nistp521,ecdsa-sha2-nistp384,ecdsa-sha2-nistp256",
    "FUTURE": "ssh-ed25519,rsa-sha2-512,rsa-sha2-256,ecdsa-sha2-nistp521,ecdsa-sha2-nistp384",
}

# PubkeyAcceptedAlgorithms takes the same algorithm set as HostKeyAlgorithms.
_SSH_PUBKEYS = _SSH_HOSTKEYS

_OPENSSL_MIN_PROTO = {"STIG": "TLSv1.2", "MODERN": "TLSv1.2", "FUTURE": "TLSv1.3"}
_OPENSSL_CIPHERSTR = {
    "STIG": "DEFAULT@SECLEVEL=2",
    "MODERN": "DEFAULT@SECLEVEL=2",
    "FUTURE": "DEFAULT@SECLEVEL=3",
}

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
    body = (
        f"{banner}"
        f"Ciphers {_SSH_CIPHERS[policy]}\n"
        f"KexAlgorithms {_SSH_KEX[policy]}\n"
        f"MACs {_SSH_MACS[policy]}\n"
        f"HostKeyAlgorithms {_SSH_HOSTKEYS[policy]}\n"
        f"PubkeyAcceptedAlgorithms {_SSH_PUBKEYS[policy]}\n"
    )
    tail = "sshd -t" if policy == "STIG" else "ssh-keygen -A\nsshd -t"
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

No edit to `src/ks_gen/rules/ubuntu2404/__init__.py` — registry uses `pkgutil.iter_modules` auto-discovery.

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/rules/test_ubuntu2404_crypto_policy.py -v`
Expected: PASS — `test_ssh_block_writes_sshd_config_drop_in_at_10_prefix` is green.

- [ ] **Step 5: Commit**

```bash
git add tests/rules/test_ubuntu2404_crypto_policy.py src/ks_gen/rules/ubuntu2404/crypto_policy.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(rules/ubuntu2404): add crypto_policy rule skeleton (#81 phase 3.4)

Writes SSH (sshd_config drop-in /etc/ssh/sshd_config.d/10-ks-gen-crypto.conf),
OpenSSL (/etc/ssl/openssl.cnf.d/10-ks-gen.conf), and GnuTLS
(/etc/gnutls/default-priorities) based on cfg.crypto.policy. Lookup
tables sourced from DISA Ubuntu 24.04 STIG v1r5 + civilian extensions
for MODERN/FUTURE. STIG mode emits a NOT-FIPS-validated banner;
FIPS validation deferred to a future pro_attach rule. emit_tailoring
+ exception_entry deferred to audit-story PR.

First test pins the SSH drop-in path."
```

---

## Task 2: Remaining per-component path tests

Two more file path assertions for the OpenSSL and GnuTLS blocks. Tests
are cheap; they protect against path-drift regressions.

**Files:**
- Modify: `tests/rules/test_ubuntu2404_crypto_policy.py`

- [ ] **Step 1: Append two path tests**

Append to `tests/rules/test_ubuntu2404_crypto_policy.py`:

```python
def test_openssl_block_writes_under_openssl_cnf_d(ubuntu_cfg_factory):
    # Ubuntu 24.04's /etc/ssl/openssl.cnf .include's openssl.cnf.d/*.cnf,
    # so dropping a file here applies system-wide without editing the
    # main config.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/ssl/openssl.cnf.d/10-ks-gen.conf" in out


def test_gnutls_block_writes_default_priorities(ubuntu_cfg_factory):
    # Debian/Ubuntu convention for system-wide GnuTLS priority.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/gnutls/default-priorities" in out
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/rules/test_ubuntu2404_crypto_policy.py -v`
Expected: all 3 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_crypto_policy.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert crypto_policy openssl + gnutls paths"
```

---

## Task 3: SSH per-policy algorithm tests (STIG / MODERN / FUTURE)

Six tests assert that the cipher / KEX / MAC / hostkey / pubkey
algorithm lists vary correctly per policy. Each test exercises one
policy at a time and asserts presence/absence of canonical markers from
the per-policy mapping table.

**Files:**
- Modify: `tests/rules/test_ubuntu2404_crypto_policy.py`

- [ ] **Step 1: Append three per-policy SSH algorithm tests**

```python
def test_ssh_stig_emits_no_chacha20_no_curve25519(ubuntu_cfg_factory):
    from ks_gen.config import Crypto, CryptoPolicy

    cfg = ubuntu_cfg_factory().model_copy(
        update={"crypto": Crypto(policy=CryptoPolicy.STIG)}
    )
    out = RULE.emit_post(cfg)
    # STIG = FIPS-aligned algorithm set. chacha20 and curve25519 are
    # excluded under FIPS 140-3.
    assert "chacha20-poly1305" not in out
    assert "curve25519" not in out
    assert "ssh-ed25519" not in out
    # But STIG-approved AES-GCM / ECDH-nistp / hmac-sha2 are present:
    assert "aes256-gcm@openssh.com" in out
    assert "ecdh-sha2-nistp384" in out
    assert "hmac-sha2-512-etm@openssh.com" in out


def test_ssh_modern_emits_chacha20_and_curve25519(ubuntu_cfg_factory):
    # MODERN is the default policy. Adds chacha20-poly1305, curve25519,
    # and ssh-ed25519 to the STIG base.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "chacha20-poly1305@openssh.com" in out
    assert "curve25519-sha256" in out
    assert "ssh-ed25519" in out


def test_ssh_future_drops_sha1_and_short_macs(ubuntu_cfg_factory):
    from ks_gen.config import Crypto, CryptoPolicy

    cfg = ubuntu_cfg_factory().model_copy(
        update={"crypto": Crypto(policy=CryptoPolicy.FUTURE)}
    )
    out = RULE.emit_post(cfg)
    # FUTURE keeps only the strongest MACs (ETM variants).
    assert "hmac-sha2-512-etm@openssh.com" in out
    assert "hmac-sha2-256-etm@openssh.com" in out
    # Non-ETM hmac-sha2-256 / -512 dropped.
    assert "MACs hmac-sha2-512-etm@openssh.com,hmac-sha2-256-etm@openssh.com\n" in out
    # ssh-rsa (without rsa-sha2-* prefix) dropped from HostKeyAlgorithms
    # — the "ssh-rsa," prefix would still appear inside "ssh-rsa-..." so
    # check the canonical form:
    assert "HostKeyAlgorithms ssh-ed25519,rsa-sha2-512" in out
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/rules/test_ubuntu2404_crypto_policy.py -v`
Expected: 6 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_crypto_policy.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert crypto_policy SSH per-policy algorithm sets"
```

---

## Task 4: SSH banner + ssh-keygen -A + validation tests

Six more tests covering the per-policy structural pieces of the SSH
block: STIG warning banner, ssh-keygen -A regen (non-STIG only), sshd
-t validation, chmod 600.

**Files:**
- Modify: `tests/rules/test_ubuntu2404_crypto_policy.py`

- [ ] **Step 1: Append six structural SSH tests**

```python
def test_ssh_stig_emits_warning_banner_comment(ubuntu_cfg_factory):
    from ks_gen.config import Crypto, CryptoPolicy

    cfg = ubuntu_cfg_factory().model_copy(
        update={"crypto": Crypto(policy=CryptoPolicy.STIG)}
    )
    out = RULE.emit_post(cfg)
    # The banner is unambiguous about the FIPS gap so an auditor reading
    # the generated sshd_config drop-in immediately sees that STIG mode
    # without pro_attach is algorithm-aligned, not FIPS-validated.
    assert "STIG-aligned algorithms but NOT FIPS-validated" in out
    assert "pro_attach rule" in out


def test_ssh_modern_does_not_emit_warning_banner_comment(ubuntu_cfg_factory):
    # MODERN is civilian-by-design; no FIPS claim to disclaim.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "NOT FIPS-validated" not in out


def test_ssh_non_stig_emits_ssh_keygen_a(ubuntu_cfg_factory):
    # MODERN/FUTURE may need Ed25519 host keys that wouldn't exist if
    # the host was ever in FIPS mode. Regen any missing keys.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "ssh-keygen -A" in out


def test_ssh_stig_does_not_emit_ssh_keygen_a(ubuntu_cfg_factory):
    # Under STIG/FIPS, host keys are FIPS-approved already; no regen
    # needed and ssh-keygen -A could regenerate non-FIPS keys.
    from ks_gen.config import Crypto, CryptoPolicy

    cfg = ubuntu_cfg_factory().model_copy(
        update={"crypto": Crypto(policy=CryptoPolicy.STIG)}
    )
    out = RULE.emit_post(cfg)
    assert "ssh-keygen -A" not in out


def test_ssh_block_runs_sshd_t_validation(ubuntu_cfg_factory):
    # sshd -t in the late-command makes the install fail-fast if the
    # generated config is invalid — better than producing a host with
    # broken sshd that can't accept SSH.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "sshd -t" in out


def test_ssh_block_chmod_600(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "chmod 600 /etc/ssh/sshd_config.d/10-ks-gen-crypto.conf" in out
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/rules/test_ubuntu2404_crypto_policy.py -v`
Expected: 12 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_crypto_policy.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert crypto_policy SSH banner + regen + chmod"
```

---

## Task 5: OpenSSL per-policy tests

Two tests for the OpenSSL block. STIG and MODERN produce identical
OpenSSL output by design (no FIPS provider without Pro), so only STIG
and FUTURE need policy-specific tests.

**Files:**
- Modify: `tests/rules/test_ubuntu2404_crypto_policy.py`

- [ ] **Step 1: Append two OpenSSL tests**

```python
def test_openssl_stig_minproto_tlsv1_2_seclevel_2(ubuntu_cfg_factory):
    # STIG = MinProtocol TLSv1.2 + SECLEVEL=2. Identical to MODERN under
    # this rule (the spec note on OpenSSL explains why).
    from ks_gen.config import Crypto, CryptoPolicy

    cfg = ubuntu_cfg_factory().model_copy(
        update={"crypto": Crypto(policy=CryptoPolicy.STIG)}
    )
    out = RULE.emit_post(cfg)
    assert "MinProtocol = TLSv1.2" in out
    assert "CipherString = DEFAULT@SECLEVEL=2" in out


def test_openssl_future_minproto_tlsv1_3_seclevel_3(ubuntu_cfg_factory):
    # FUTURE jumps to TLS 1.3 only + SECLEVEL=3 (forces 128-bit symmetric
    # and ECDH-only key agreement).
    from ks_gen.config import Crypto, CryptoPolicy

    cfg = ubuntu_cfg_factory().model_copy(
        update={"crypto": Crypto(policy=CryptoPolicy.FUTURE)}
    )
    out = RULE.emit_post(cfg)
    assert "MinProtocol = TLSv1.3" in out
    assert "CipherString = DEFAULT@SECLEVEL=3" in out
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/rules/test_ubuntu2404_crypto_policy.py -v`
Expected: 14 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_crypto_policy.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert crypto_policy OpenSSL per-policy MinProtocol/SECLEVEL"
```

---

## Task 6: GnuTLS per-policy tests

Two tests for the GnuTLS priority file. STIG and MODERN both write
`SECURE128`; FUTURE writes `SECURE256`.

**Files:**
- Modify: `tests/rules/test_ubuntu2404_crypto_policy.py`

- [ ] **Step 1: Append two GnuTLS tests**

```python
def test_gnutls_stig_emits_secure128(ubuntu_cfg_factory):
    # STIG = SECURE128 (gnutls28 built-in profile for 128-bit equivalent
    # security). Identical to MODERN under this rule.
    from ks_gen.config import Crypto, CryptoPolicy

    cfg = ubuntu_cfg_factory().model_copy(
        update={"crypto": Crypto(policy=CryptoPolicy.STIG)}
    )
    out = RULE.emit_post(cfg)
    # The priority appears inside the heredoc body, on its own line.
    assert "SECURE128\n" in out
    assert "SECURE256" not in out


def test_gnutls_future_emits_secure256(ubuntu_cfg_factory):
    from ks_gen.config import Crypto, CryptoPolicy

    cfg = ubuntu_cfg_factory().model_copy(
        update={"crypto": Crypto(policy=CryptoPolicy.FUTURE)}
    )
    out = RULE.emit_post(cfg)
    assert "SECURE256\n" in out
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/rules/test_ubuntu2404_crypto_policy.py -v`
Expected: 16 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_crypto_policy.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert crypto_policy GnuTLS per-policy priority"
```

---

## Task 7: Protocol contract tests

Six tests that guard the Rule Protocol contract against drift. Mirrors
the same group from phase 3.3 (`test_ubuntu2404_time_servers.py`).

**Files:**
- Modify: `tests/rules/test_ubuntu2404_crypto_policy.py`

- [ ] **Step 1: Append six protocol tests**

```python
def test_applies_always_true(ubuntu_cfg_factory):
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_emit_packages_returns_empty(ubuntu_cfg_factory):
    # openssh-server, openssl, libgnutls30 all ship in Ubuntu Server's
    # minimal install. No apt deps.
    assert RULE.emit_packages(ubuntu_cfg_factory()) == []


def test_emit_tailoring_returns_empty_deferred(ubuntu_cfg_factory):
    # Deferred until ssg-ubuntu2404-ds.xml crypto rule survey lands in
    # the audit-story PR.
    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []


def test_exception_entry_returns_none_deferred(ubuntu_cfg_factory):
    # Deferred until ssg-ubuntu2404-ds.xml crypto rule survey lands.
    assert RULE.exception_entry(ubuntu_cfg_factory()) is None


def test_depends_on_is_empty(ubuntu_cfg_factory):
    # Mirrors meta's empty DEPENDS_ON. The drop-in lex-orders after
    # ssh_config_apply's 00-ks-gen.conf without needing an explicit
    # depends_on edge — they don't overlap on directives.
    assert RULE.depends_on == []


def test_id_and_summary_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules._meta import crypto_policy as meta

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY
```

- [ ] **Step 2: Run all tests in the file**

Run: `pytest tests/rules/test_ubuntu2404_crypto_policy.py -v`
Expected: 22 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_crypto_policy.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert protocol contract for crypto_policy"
```

---

## Task 8: Regenerate the ubuntu_minimal golden snapshot

The new rule's late-command body must be captured in the golden
snapshot for `test_ubuntu_minimal`.

**Files:**
- Modify: `tests/golden/__snapshots__/test_ubuntu_minimal.ambr`

- [ ] **Step 1: Run the golden test to confirm it fails**

Run: `pytest tests/golden/ -v -k ubuntu_minimal`
Expected: FAIL — syrupy reports the snapshot diff for the new
crypto_policy block.

- [ ] **Step 2: Regenerate the snapshot**

Run: `pytest tests/golden/ --snapshot-update -k ubuntu_minimal`
Expected: pass; the `.ambr` file is updated.

- [ ] **Step 3: Inspect the diff before committing**

Run: `git diff tests/golden/__snapshots__/test_ubuntu_minimal.ambr`

Expected diff (and ONLY these changes):

1. A new `# rule:crypto_policy ──────────...` band inside `late-commands`
   containing the three component blocks (SSH heredoc → OpenSSL heredoc
   → GnuTLS heredoc), evaluated for the default `MODERN` policy. The
   SSH heredoc body should contain `Ciphers chacha20-poly1305@openssh.com,...`,
   `KexAlgorithms curve25519-sha256,...`, `ssh-keygen -A`, `sshd -t`. The
   OpenSSL heredoc should contain `MinProtocol = TLSv1.2`, `CipherString = DEFAULT@SECLEVEL=2`.
   The GnuTLS heredoc should contain `SECURE128`.
2. The "Applied rules: N" header in the late-commands intro comment
   bumps from 5 to 6.
3. The Applied-rules list inside that header gains a `- crypto_policy —
   Apply system crypto-policy; optionally generate Ed25519 host keys.`
   line.

If any alma9 snapshot diffs, STOP — that's a bug, investigate before
proceeding. No `autoinstall.packages:` changes expected (this rule's
`emit_packages` is empty).

**Merge-order assumption.** The 5 → 6 count assumes this branch sits on
top of main at `4b8644b` (phases 3.0/3.1/3.2/3.3 already merged = 5
rules). If unrelated work landed first that added another ubuntu2404
rule, regenerate the snapshot and confirm the diff is "+1 your rule,
nothing else."

- [ ] **Step 4: Commit the regenerated snapshot**

```bash
git add tests/golden/__snapshots__/test_ubuntu_minimal.ambr
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(golden): regen ubuntu_minimal snapshot for crypto_policy rule"
```

---

## Task 9: CI parity check + push + PR

Per `CLAUDE.md`, run the full local CI chain in the exact order CI runs
it. `ruff format --check` is a separate gate from `ruff check` and has
bounced PRs on this workstream before.

**Files:** none modified by this task (tooling only — possibly a
`style:` commit if `ruff format --check` finds drift).

- [ ] **Step 1: Run ruff check**

Run: `ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 2: Run ruff format --check**

Run: `ruff format --check src tests`
Expected: `N files already formatted` (no diff).

If `Would reformat: ...` appears:

```bash
ruff format src tests
ruff format --check src tests  # verify clean
git add -u
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "style: ruff format src tests"
```

- [ ] **Step 3: Run mypy**

Run: `mypy`
Expected: `Success: no issues found in N source files`

- [ ] **Step 4: Run pytest**

Run: `pytest -q`
Expected: all tests pass — should be 800 tests (778 from end of phase 3.3 + 22 new crypto_policy tests).

- [ ] **Step 5: Verify branch is signed-clean**

Run: `git log --show-signature -9 --oneline`
Expected: every commit since `81eb71d` (the spec commit) shows `Good signature from "Patrick Connallon (SupremeCommanderHedgehog) <github.v5f9w@bitbucket.onl>"` with key `BE707B220C995478`.

- [ ] **Step 6: Push the branch**

Run: `git push -u origin feat/phase-3-4-crypto-policy`
Expected: push succeeds; GitHub returns the URL for opening a PR.

If push fails with `GH007: Your push would publish a private email address`, STOP and surface to the user. Do NOT fall back to noreply form.

- [ ] **Step 7: Open the PR**

```bash
gh pr create --title "feat(rules/ubuntu2404): crypto_policy port (#81 phase 3.4)" --body "$(cat <<'EOF'
## Summary

- Ports the `crypto_policy` rule to ubuntu2404 (issue #81 phase 3.4).
- Pins crypto across three components per `cfg.crypto.policy`:
  - **SSH** drop-in `/etc/ssh/sshd_config.d/10-ks-gen-crypto.conf` (Ciphers / KexAlgorithms / MACs / HostKeyAlgorithms / PubkeyAcceptedAlgorithms)
  - **OpenSSL** drop-in `/etc/ssl/openssl.cnf.d/10-ks-gen.conf` (MinProtocol + CipherString in `[system_default_sect]`)
  - **GnuTLS** `/etc/gnutls/default-priorities` (priority string)
- STIG mode emits the DISA Ubuntu 24.04 STIG v1r5 algorithm lists with a `NOT FIPS-validated` warning banner in the SSH drop-in. FIPS validation is delegated to a future `pro_attach` rule that will own Ubuntu Pro attach + `pro enable fips-updates`.
- libgcrypt is intentionally NOT touched — Ubuntu has no civilian-equivalent system-wide knob; libgcrypt config is owned by the embedding application.
- `emit_tailoring` + `exception_entry` deferred to the audit-story PR (same pattern as phases 3.1 / 3.2 / 3.3).

Spec: `docs/superpowers/specs/2026-06-19-ubuntu-stig-autoinstall-phase-3-4-crypto-policy-design.md`
Plan: `docs/superpowers/plans/2026-06-19-ubuntu-stig-autoinstall-phase-3-4-crypto-policy.md`

## Test plan

- [x] 22 new unit tests in `tests/rules/test_ubuntu2404_crypto_policy.py` cover per-component paths, SSH per-policy algorithm sets (STIG/MODERN/FUTURE), SSH banner + ssh-keygen -A regen, sshd -t validation, chmod 600, OpenSSL MinProtocol/SECLEVEL per policy, GnuTLS priority per policy, and the Rule Protocol contract.
- [x] `tests/golden/__snapshots__/test_ubuntu_minimal.ambr` regenerated — diff adds the `# rule:crypto_policy` band (3 component heredocs) and bumps Applied-rules header 5 → 6. No `autoinstall.packages:` changes (this rule contributes no packages).
- [x] Full CI chain run locally: `ruff check && ruff format --check && mypy && pytest -q` — all four green.
- [x] Each commit on this branch is GPG-signed with `BE707B220C995478`.
EOF
)"
```

- [ ] **Step 8: Wait for required status checks**

Run: `gh pr checks <pr-number>` (number returned by `gh pr create`)
Expected: 5/5 status checks pass (ruff, analyze (python), test 3.11/3.12/3.13, CodeQL).

If a check fails, read the failure, fix on the branch, push again.

(Merging is a separate user-driven step — see superpowers:finishing-a-development-branch.)
