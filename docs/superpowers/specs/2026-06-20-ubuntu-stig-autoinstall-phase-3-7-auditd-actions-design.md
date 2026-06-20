# Phase 3.7 — `auditd_actions` port to ubuntu2404

**Parent:** #81 ubuntu STIG autoinstall.
**Previous phases on this workstream:** 3.0 admin_user_and_keys +
ssh_keep_open (#94), 3.1 banner_text (#101), 3.2 ssh_config_apply
(#102), 3.3 time_servers (#104), 3.4 crypto_policy (#106), 3.5
faillock_safety (#108), 3.6 unattended_updates (#110).

## Goal

Port the `auditd_actions` rule to ubuntu2404 so the generated
autoinstall produces a **functional** remote-safe auditd disk-action
policy on Ubuntu Server. That requires two coordinated actions: (1)
install the `auditd` package (Ubuntu Server doesn't ship it by
default, unlike RHEL), and (2) defensively re-assert
`disk_full_action`, `disk_error_action`, and `max_log_file_action`
in `/etc/audit/auditd.conf` to the operator's `cfg.overrides.auditd`
values.

## Non-goals

- **ssg-ubuntu2404-ds.xml tailoring + exception text.** Deferred to
  the coordinated audit-story PR per the established phase-3.x
  pattern. The three SSG variable IDs in the alma9 rule
  (`xccdf_org.ssgproject.content_value_var_auditd_disk_full_action`,
  `..._disk_error_action`, `..._max_log_file_action`) are upstream
  SSG-shared and likely carry over verbatim to ubuntu2404, but the
  audit-story PR will systematically verify all 8 ported rules at
  once.
- **Schema changes.** `AuditdActionsCfg`, `AuditdSystemAction`,
  `AuditdMaxFileAction` are already distro-neutral in
  `src/ks_gen/config.py:560-577` — no edits.
- **Enabling the kernel audit subsystem (`audit=1` on grub
  cmdline).** Separate STIG concern, not part of this rule. The
  auditd daemon's disk-action policy is what we configure; whether
  the kernel-level audit subsystem fires events is governed by
  upstream `ssg-ubuntu2404` rules unrelated to `auditd_actions`.
- **Restarting auditd in late-commands.** Late-commands run during
  the autoinstall before the target system's first boot. auditd has
  not started yet; our config file is in place when it does start
  on first boot. No `systemctl restart auditd` needed.
- **`audispd-plugins`.** Network/syslog forwarding is a distinct
  feature; YAGNI for the safety rule.

## Architecture

One new rule module + one new test file. Shared
`src/ks_gen/rules/_meta/auditd_actions.py` (ID, SUMMARY,
DEPENDS_ON) is untouched.

`emit_post` composes one block via a module-level `_emit(cfg)`
helper (mirrors faillock_safety's single-block structure):

```python
def _emit(cfg: HostConfig) -> str:
    a = cfg.overrides.auditd
    conf = "/etc/audit/auditd.conf"
    df = a.disk_full_action.value      # e.g. "SUSPEND"
    de = a.disk_error_action.value     # e.g. "SUSPEND"
    mf = a.max_log_file_action.value   # e.g. "ROTATE" or "keep_logs"
    return (
        "# Re-assert auditd actions (defensive sed + append-if-missing)\n"
        f"sed -i -E 's|^[# ]*disk_full_action.*|disk_full_action = {df}|' {conf}\n"
        f"grep -q '^disk_full_action' {conf} || echo 'disk_full_action = {df}' >> {conf}\n"
        f"sed -i -E 's|^[# ]*disk_error_action.*|disk_error_action = {de}|' {conf}\n"
        f"grep -q '^disk_error_action' {conf} || echo 'disk_error_action = {de}' >> {conf}\n"
        f"sed -i -E 's|^[# ]*max_log_file_action.*|max_log_file_action = {mf}|' {conf}\n"
        f"grep -q '^max_log_file_action' {conf} || echo 'max_log_file_action = {mf}' >> {conf}\n"
    )
```

The rule plugs into the existing ubuntu2404 bundle pipeline:
- `emit_post` contributes a `# rule:auditd_actions` band to
  `late-commands`.
- `emit_packages` returns `["auditd"]` — Ubuntu Server's
  `ubuntu-server` seed does NOT include auditd; without this pull,
  `/etc/audit/auditd.conf` doesn't exist and the sed-replace block
  fails. Mirrors phase 3.3 (chrony) and 3.6 (unattended-upgrades)
  precedent.
- `applies(cfg)` returns `True` unconditionally (no parent
  enable/disable on `AuditdActionsCfg`; matches alma9).

No changes to `writer.py`, `skeleton.py`, the user-data template, or
the config schema.

## Files touched

- **Create:** `src/ks_gen/rules/ubuntu2404/auditd_actions.py`
- **Create:** `tests/rules/test_ubuntu2404_auditd_actions.py`
- **Modify:** `tests/golden/__snapshots__/test_ubuntu_minimal.ambr`
  (snapshot regen)

## `emit_post` behavior

### Single block: `/etc/audit/auditd.conf`

Same defensive sed-replace pattern as phase 3.5 faillock_safety
(path is identical on Ubuntu; the file ships in the `auditd`
package, which `emit_packages` pulls in):

```bash
# Re-assert auditd actions (defensive sed + append-if-missing)
sed -i -E 's|^[# ]*disk_full_action.*|disk_full_action = {df}|' /etc/audit/auditd.conf
grep -q '^disk_full_action' /etc/audit/auditd.conf || echo 'disk_full_action = {df}' >> /etc/audit/auditd.conf
sed -i -E 's|^[# ]*disk_error_action.*|disk_error_action = {de}|' /etc/audit/auditd.conf
grep -q '^disk_error_action' /etc/audit/auditd.conf || echo 'disk_error_action = {de}' >> /etc/audit/auditd.conf
sed -i -E 's|^[# ]*max_log_file_action.*|max_log_file_action = {mf}|' /etc/audit/auditd.conf
grep -q '^max_log_file_action' /etc/audit/auditd.conf || echo 'max_log_file_action = {mf}' >> /etc/audit/auditd.conf
```

Design notes:
- The `sed → grep || echo` pair handles three file states defensively:
  - line present uncommented → sed replaces in place
  - line present commented (e.g., `# disk_full_action = SUSPEND`) →
    sed uncomments + replaces (`^[# ]*` prefix)
  - line absent entirely → echo appends (Ubuntu's stock auditd.conf
    today has all three lines uncommented, but Debian downstream
    rebuilds or apt upgrades could change that)
- Pipe-delimited `s|...|...|` (matches alma9) — auditd.conf values
  never contain `|`. Avoids escaping concerns for the `/` slashes
  alma9 chose.
- `{df}` / `{de}` / `{mf}` are `a.X.value` — the `StrEnum`'s string
  value, e.g., `"SUSPEND"`, `"HALT"`, `"ROTATE"`, `"keep_logs"`
  (mixed case: `keep_logs` is lowercase per upstream auditd
  convention; the enum preserves it).

## Rule scaffolding

```python
"""ubuntu2404 auditd_actions rule.

Installs the auditd package and defensively re-asserts
disk_full_action, disk_error_action, and max_log_file_action in
/etc/audit/auditd.conf to the operator's cfg.overrides.auditd
values. Ubuntu Server does not ship auditd by default (unlike
RHEL), so emit_packages pulls it in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import auditd_actions as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


def _emit(cfg: HostConfig) -> str:
    a = cfg.overrides.auditd
    conf = "/etc/audit/auditd.conf"
    df = a.disk_full_action.value
    de = a.disk_error_action.value
    mf = a.max_log_file_action.value
    return (
        "# Re-assert auditd actions (defensive sed + append-if-missing)\n"
        f"sed -i -E 's|^[# ]*disk_full_action.*|disk_full_action = {df}|' {conf}\n"
        f"grep -q '^disk_full_action' {conf} || echo 'disk_full_action = {df}' >> {conf}\n"
        f"sed -i -E 's|^[# ]*disk_error_action.*|disk_error_action = {de}|' {conf}\n"
        f"grep -q '^disk_error_action' {conf} || echo 'disk_error_action = {de}' >> {conf}\n"
        f"sed -i -E 's|^[# ]*max_log_file_action.*|max_log_file_action = {mf}|' {conf}\n"
        f"grep -q '^max_log_file_action' {conf} || echo 'max_log_file_action = {mf}' >> {conf}\n"
    )


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        # Deferred: ssg-ubuntu2404-ds.xml var_auditd_* variable IDs
        # land in the audit-story PR.
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        # Ubuntu Server doesn't ship auditd by default (unlike RHEL).
        return ["auditd"]

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        # Deferred: paired with emit_tailoring above; see audit-story PR.
        return None


RULE: Rule = cast(Rule, _Rule())
```

## Tests (14)

All use the `ubuntu_cfg_factory` fixture. Module-level imports of
`RULE`; local imports of `AuditdActionsCfg, AuditdSystemAction,
AuditdMaxFileAction, Overrides` inside per-test override functions
(matches phases 3.3/3.4/3.5/3.6 pattern).

### `applies` semantics
1. `test_applies_always_returns_true` — default cfg → True (no
   parent enable/disable on this rule)

### `emit_post` path + defaults
2. `test_post_targets_etc_audit_auditd_conf` — path present
3. `test_post_reasserts_disk_full_action_default_suspend`
4. `test_post_reasserts_disk_error_action_default_suspend`
5. `test_post_reasserts_max_log_file_action_default_rotate`

### Cfg-override responsiveness
6. `test_post_reflects_disk_full_action_override` — cfg
   `disk_full_action=HALT` → `disk_full_action = HALT`
7. `test_post_reflects_disk_error_action_override` — cfg
   `disk_error_action=SYSLOG` → `disk_error_action = SYSLOG`
8. `test_post_reflects_max_log_file_action_override` — cfg
   `max_log_file_action=KEEP_LOGS` → `max_log_file_action =
   keep_logs` (lowercase per enum's string value)

### Defensive pattern shape
9. `test_post_uses_defensive_sed_prefix_for_all_three_directives` —
   `^[# ]*` appears in each of three sed lines (count == 3)
10. `test_post_appends_with_grep_fallback_for_all_three_directives`
    — `grep -q '^disk_full_action'` (+ similar for the other two)
    each present, paired with `||` and an `echo ... >> ...`

### Packages
11. `test_emit_packages_returns_auditd` — `["auditd"]`

### Protocol contract
12. `test_id_and_summary_come_from_shared_meta`
13. `test_emit_tailoring_returns_empty_deferred`
14. `test_exception_entry_returns_none_deferred` (+ inline assert
    `depends_on == []`)

## Snapshot regen

After tests pass, run `pytest tests/golden/ --snapshot-update -k ubuntu_minimal`.

Expected diff (and ONLY these changes):

1. New `# rule:auditd_actions ──────────...` band in
   `late-commands` containing the 6 sed+grep lines.
2. "Applied rules: N" header bumps from 8 to 9.
3. The Applied-rules list gains `- auditd_actions — auditd
   disk_full/disk_error/max_log_file actions (SUSPEND/ROTATE
   default).` at its sorted position (observed in the writer's
   ordering — accept whatever single-line insertion the regen
   produces).
4. `auditd` added to `autoinstall.packages:` list.

No alma9 snapshots affected.

### Merge-order assumption

The 8 → 9 count assumes this branch sits on main at `388b46a`
(post-v0.20.0, includes phases 3.0/3.1/3.2/3.3/3.4/3.5/3.6 = 8
ubuntu rules). If unrelated work landed first, regenerate the
snapshot and confirm the diff is "+1 your rule, nothing else."

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| auditd package install fails or stalls on a missing kernel-audit subsystem | The `auditd` package's postinst doesn't require kernel audit to be enabled to install — the daemon will start (or not) at first boot based on the kernel cmdline. Install is unconditional. |
| Stock Ubuntu auditd.conf doesn't have these three lines | Defensive sed + grep-fallback pattern appends if missing. Tested explicitly. |
| `max_log_file_action = keep_logs` (lowercase) confuses operators who expect uppercase enum semantics | The `AuditdMaxFileAction.KEEP_LOGS` enum's string value is literally `"keep_logs"` (matches auditd.conf's documented lowercase token). The sed-replace writes it verbatim. Tested explicitly. |
| auditd starts before late-commands modify the config | Late-commands run in the Subiquity target chroot BEFORE the target system boots. auditd has never started in this chroot. First-boot auditd starts with our config in place. |
| apt upgrade rewrites auditd.conf with a conffile prompt | The package is shipped with `Conf-Files: /etc/audit/auditd.conf` and uses `dpkg-deb`'s conffile mechanism. On upgrade, dpkg detects our edits and prompts the operator (or in non-interactive mode, applies `--force-confold` per the global apt config). Phase 3.6 unattended_updates installs `52ks-gen-unattended` policy but doesn't set conf options — runtime upgrades that bump auditd may prompt. Acceptable: post-install operator concern, not kickstart-time. |

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

- ssg-ubuntu2404-ds.xml `var_auditd_*` variable IDs +
  `TailoringOp` entries.
- `exception_entry` runtime-computed English (mirrors alma9's
  HALT/HALT/keep_logs strict check).
- Forwarding plugins (`audispd-plugins`) — separate feature, not
  part of the safety rule.
- Kernel-level `audit=1` cmdline — separate STIG concern, owned by
  upstream ssg-ubuntu2404 rules.
