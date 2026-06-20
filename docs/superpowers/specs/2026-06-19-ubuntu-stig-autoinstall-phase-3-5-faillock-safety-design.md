# Phase 3.5 — `faillock_safety` port to ubuntu2404

**Parent:** #81 ubuntu STIG autoinstall.
**Previous phases on this workstream:** 3.0 admin_user_and_keys + ssh_keep_open (#94), 3.1 banner_text (#101), 3.2 ssh_config_apply (#102), 3.3 time_servers (#104), 3.4 crypto_policy (#106).

## Goal

Port the `faillock_safety` rule to ubuntu2404 so the generated
autoinstall produces a **functional** remote-safe lockout policy on
Ubuntu Server. That requires two coordinated actions: (1) write
`/etc/security/faillock.conf` with operator's `cfg.overrides.faillock`
values, and (2) wire `pam_faillock` into the PAM stack via Ubuntu's
`pam-auth-update` profile mechanism — without this wiring, the config
file is dead.

## Non-goals

- **ssg-ubuntu2404-ds.xml tailoring + exception text.** Deferred to the
  coordinated audit-story PR per the established phase-3.x pattern. The
  RHEL XCCDF rule IDs in the alma9 rule (`xccdf_org.ssgproject.content_value_var_accounts_passwords_pam_faillock_*`)
  do NOT carry over verbatim to the Ubuntu datastream and need to be
  re-surveyed there.
- **Schema changes.** `FaillockCfg` (`enable`, `deny`, `unlock_time`,
  `even_deny_root`) is already distro-agnostic in
  `src/ks_gen/config.py:553` — no edits.
- **Direct edits of `/etc/pam.d/common-auth`.** Brittle vs apt upgrades
  of `libpam-runtime` (which regenerates the common-* files).
  pam-auth-update profile mechanism owns this surface; use it.

## Architecture

One new rule module + one new test file. Shared
`src/ks_gen/rules/_meta/faillock_safety.py` (ID, SUMMARY, DEPENDS_ON,
EXCEPTION_REASON) is untouched.

`emit_post` composes three independent blocks in sequence:

```python
def _emit(cfg: HostConfig) -> str:
    return "".join([
        _emit_faillock_conf(cfg),
        _emit_pam_profile(cfg),
        _emit_pam_enable(cfg),
    ])
```

Splitting by responsibility means a future change to the
faillock.conf sed-replace pattern doesn't risk corrupting the profile
heredoc.

The rule plugs into the existing ubuntu2404 bundle pipeline:
- `emit_post` contributes a `# rule:faillock_safety` block to
  `late-commands`.
- `emit_packages` returns `[]` — `pam_faillock.so` ships in
  `libpam-modules`, `pam-auth-update` ships in `libpam-runtime`. Both
  essential.

No changes to `writer.py`, `skeleton.py`, the user-data template, or
the config schema.

## Files touched

- **Create:** `src/ks_gen/rules/ubuntu2404/faillock_safety.py`
- **Create:** `tests/rules/test_ubuntu2404_faillock_safety.py`
- **Modify:** `tests/golden/__snapshots__/test_ubuntu_minimal.ambr`
  (snapshot regen)

## `emit_post` behavior

### Block 1: `/etc/security/faillock.conf`

Same defensive sed-replace pattern as alma9 (path is identical on
Ubuntu; the file ships pre-installed via `libpam-modules`):

```bash
# faillock.conf — soften lockout for remote-safe operation
sed -i -E 's/^[# ]*unlock_time *=.*/unlock_time = {f.unlock_time}/' /etc/security/faillock.conf
grep -q '^unlock_time' /etc/security/faillock.conf || echo 'unlock_time = {f.unlock_time}' >> /etc/security/faillock.conf
sed -i -E 's/^[# ]*deny *=.*/deny = {f.deny}/' /etc/security/faillock.conf
grep -q '^deny' /etc/security/faillock.conf || echo 'deny = {f.deny}' >> /etc/security/faillock.conf
sed -i -E 's/^[# ]*even_deny_root.*/# even_deny_root removed by ks-gen: {even}/' /etc/security/faillock.conf
```

`{even}` is `"yes"` if `cfg.overrides.faillock.even_deny_root` else
`"no"`. The directive itself is commented out either way; the trailing
`yes`/`no` preserves cfg intent for the auditor.

The `sed → grep || echo` pattern handles three states defensively:
- file has the line uncommented → sed replaces in place
- file has the line commented → sed replaces and uncomments
- file is missing the line entirely → echo appends

### Block 2: pam-auth-update profile

Write `/usr/share/pam-configs/ks-gen-faillock`:

```
Name: pam_faillock (ks-gen)
Default: yes
Priority: 1024
Auth-Type: Primary
Auth-Initial:
        [default=die]                  pam_faillock.so authfail
Auth:
        [success=1 default=ignore]     pam_faillock.so preauth
Account-Type: Primary
Account:
        required                       pam_faillock.so
```

- `Name:` is a unique identifier (the `ks-gen` suffix avoids collision
  with any future Debian-shipped `pam-faillock` profile).
- `Priority: 1024` lands between `pam_unix` (256) and `pam_winbind`
  (192) — ensures faillock's preauth check runs before the password
  prompt and authfail runs after a failure.
- `Default: yes` makes the profile enabled-by-default after the
  `--enable` flag runs in block 3.
- The four PAM lines: preauth (counts failures before auth), authfail
  (records the failure when auth dies), authsucc would zero the
  counter on success but `Account: required pam_faillock.so` already
  does that on the account path — keeping the profile minimal.

Late-command tail: `install -d -m 755 /usr/share/pam-configs` belt for
idempotent re-run safety (same pattern as time_servers and
crypto_policy).

### Block 3: Enable the profile

```bash
DEBIAN_FRONTEND=noninteractive pam-auth-update --enable ks-gen-faillock --package
```

- `DEBIAN_FRONTEND=noninteractive` suppresses prompts (no TTY in
  late-commands).
- `--enable ks-gen-faillock` activates the profile we just wrote.
- `--package` tells pam-auth-update this is a package-managed,
  non-interactive run — survives subsequent `libpam-runtime` upgrades
  that regenerate the common-* files.

## Rule scaffolding (matches phase 3.4)

```python
"""ubuntu2404 faillock soften-lockout rule.

Writes /etc/security/faillock.conf and wires pam_faillock into the
common-auth/common-account stack via pam-auth-update. Wiring is
required on Ubuntu because the libpam-modules package ships
pam_faillock.so but does not auto-enable it (unlike RHEL).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import faillock_safety as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


def _emit_faillock_conf(cfg: HostConfig) -> str:
    f = cfg.overrides.faillock
    even = "yes" if f.even_deny_root else "no"
    conf = "/etc/security/faillock.conf"
    return (
        "# faillock.conf — soften lockout for remote-safe operation\n"
        f"sed -i -E 's/^[# ]*unlock_time *=.*/unlock_time = {f.unlock_time}/' {conf}\n"
        f"grep -q '^unlock_time' {conf} || echo 'unlock_time = {f.unlock_time}' >> {conf}\n"
        f"sed -i -E 's/^[# ]*deny *=.*/deny = {f.deny}/' {conf}\n"
        f"grep -q '^deny' {conf} || echo 'deny = {f.deny}' >> {conf}\n"
        f"sed -i -E 's/^[# ]*even_deny_root.*/# even_deny_root removed by ks-gen: {even}/' {conf}\n"
    )


def _emit_pam_profile(cfg: HostConfig) -> str:
    return """\
# pam-auth-update profile (wires pam_faillock into common-auth/common-account)
install -d -m 755 /usr/share/pam-configs
cat > /usr/share/pam-configs/ks-gen-faillock <<'__KS_GEN_EOF__'
Name: pam_faillock (ks-gen)
Default: yes
Priority: 1024
Auth-Type: Primary
Auth-Initial:
        [default=die]                  pam_faillock.so authfail
Auth:
        [success=1 default=ignore]     pam_faillock.so preauth
Account-Type: Primary
Account:
        required                       pam_faillock.so
__KS_GEN_EOF__
chmod 644 /usr/share/pam-configs/ks-gen-faillock
"""


def _emit_pam_enable(cfg: HostConfig) -> str:
    return "DEBIAN_FRONTEND=noninteractive pam-auth-update --enable ks-gen-faillock --package\n"


def _emit(cfg: HostConfig) -> str:
    return "".join([_emit_faillock_conf(cfg), _emit_pam_profile(cfg), _emit_pam_enable(cfg)])


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return cfg.overrides.faillock.enable

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        # Deferred: ssg-ubuntu2404-ds.xml faillock rule survey lands in the audit-story PR.
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

## Tests (19)

All use the `ubuntu_cfg_factory` fixture. Module-level imports of
`RULE`; local imports of `FaillockCfg, Overrides` inside per-test
override functions (matches phase 3.3/3.4 pattern).

### `applies` semantics
1. `test_applies_when_enabled` — default cfg → True
2. `test_applies_short_circuits_when_disabled` — `enable=False` → False (rule excluded from late-commands)

### faillock.conf shape
3. `test_post_writes_faillock_conf_path`
4. `test_post_reasserts_unlock_time_from_cfg` — default 900
5. `test_post_reasserts_deny_from_cfg` — default 3
6. `test_post_comments_out_even_deny_root_with_no_marker` — default
   `even_deny_root=False` → `# even_deny_root removed by ks-gen: no`
7. `test_post_comments_out_even_deny_root_with_yes_marker` — cfg
   override `even_deny_root=True` → `... : yes`
8. `test_post_reflects_unlock_time_override` — cfg `unlock_time=300`
9. `test_post_reflects_deny_override` — cfg `deny=5`

### pam-auth-update profile
10. `test_post_writes_pam_configs_profile_at_ks_gen_faillock`
11. `test_post_profile_contains_preauth_and_authfail_lines`
12. `test_post_profile_contains_account_required_line`

### pam-auth-update enable
13. `test_post_enables_profile_via_pam_auth_update`
14. `test_post_uses_debian_frontend_noninteractive`

### Protocol contract (mirror phase 3.4)
15. `test_emit_packages_returns_empty` — libpam-modules ships with base
16. `test_emit_tailoring_returns_empty_deferred`
17. `test_exception_entry_returns_none_deferred`
18. `test_depends_on_is_empty`
19. `test_id_and_summary_come_from_shared_meta`

## Snapshot regen

After tests pass, run `pytest tests/golden/ --snapshot-update -k ubuntu_minimal`.

Expected diff (and ONLY these changes):

1. New `# rule:faillock_safety ──────────...` band in `late-commands`
   containing the three blocks (faillock.conf sed-replace +
   pam-configs heredoc + pam-auth-update enable).
2. "Applied rules: N" header bumps from 6 to 7.
3. The Applied-rules list gains `- faillock_safety — Set faillock
   unlock_time and disable even_deny_root for remote safety.` inserted
   alphabetically (between `crypto_policy` and `ssh_config_apply`).

No `autoinstall.packages:` changes. No alma9 snapshots affected.

### Merge-order assumption

The 6 → 7 count assumes this branch sits on main at `2ba0cc5`
(post-v0.18.0, includes phases 3.0/3.1/3.2/3.3/3.4 = 6 ubuntu rules).
If unrelated work landed first, regenerate the snapshot and confirm
the diff is "+1 your rule, nothing else."

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| pam-auth-update isn't available in chroot at late-command time | `libpam-runtime` is Essential: yes; it's installed before late-commands run. Verified by Debian package metadata. |
| Profile name collision with a future Debian-shipped pam-faillock profile | `ks-gen-faillock` prefix is unique; no Debian package ships a `pam-configs/ks-gen-*` file. |
| pam-auth-update prompts for input when run in chroot | `DEBIAN_FRONTEND=noninteractive` + `--package` flag together force non-interactive. |
| sed pattern matches commented-out lines incorrectly | Tested by matching `^[# ]*unlock_time *=.*` — covers both `unlock_time` and `# unlock_time` forms. Same pattern alma9 uses for years. |
| pam_faillock locks out the admin user before first SSH | Late-commands run AFTER subiquity creates the admin user; pam_faillock's defaults (deny=3, 15min unlock) don't penalize first-time SSH-with-key. Safe. |

## CI parity check before push

Per `CLAUDE.md`:

```bash
ruff check src tests \
  && ruff format --check src tests \
  && mypy \
  && pytest -q
```

If `ruff format --check` fails, fix with `ruff format src tests`.

## Out of scope (deferred)

- ssg-ubuntu2404-ds.xml faillock rule IDs + `TailoringOp` entries.
- `exception_entry` English text (uses `meta.EXCEPTION_REASON` once the
  audit-story survey lands).
- Removing the `ks-gen-faillock` profile on rule
  `enable=False` after a previous install enabled it. (Operator concern,
  not a kickstart-time concern — the rule no-ops via `applies()` and
  any prior install is the operator's problem.)
