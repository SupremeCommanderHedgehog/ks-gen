# audit-story PR A — ubuntu2404 `emit_tailoring` + `exception_entry`

**Parent:** #127 (cross-distro audit-story PR).
**Phase 1 (data):** shipped v0.27.0 via PR #128.

## Goal

Wire up `emit_tailoring` + `exception_entry` for all 14 ubuntu2404 rules so that:

- `tailoring.xml` generated for an `distro: ubuntu2404` host actually contains the `<xccdf:select>` / `<xccdf:set-value>` ops that mirror the alma9 sibling's behavior — adjusted for Ubuntu-specific SSG rule IDs surfaced by phase 1.
- `exceptions.md` gains a populated "Tailored XCCDF rules" section + per-rule exception details that match the alma9 audit-trail completeness.

After this PR, an `oscap xccdf eval --tailoring-file ...` run on a ubuntu2404 install will skip the SSG rules ks-gen mooted (banner-text checks, sshd cipher checks, etc.) and the auditor reading `exceptions.md` sees the exception chain end-to-end.

## Cross-reference (from phase 1 data — `docs/audit-story/`)

Each row notes the alma9 emit_tailoring ops and the corresponding ubuntu2404 mapping. "Drop" means the alma9 SSG ID doesn't exist in `ssg-ubuntu2404-ds.xml` (0.1.79-1) and there's no equivalent.

### 8 rules: no tailoring work (alma9 returns `[]` too)

`admin_user_and_keys`, `ssh_keep_open`, `ssh_config_apply`, `time_servers`, `unattended_updates`, `kernel_module_blacklist`, `package_purge`, `container_host` — these already mirror alma9's empty `emit_tailoring` + `exception_entry`. **No changes.**

### `banner_text` — 3 alma9 ops → 6 ubuntu ops

Ubuntu's SSG splits the banner checks into CIS and non-CIS variants. Our civilian banner moots all of them.

```python
def emit_tailoring(self, cfg):
    return [
        TailoringOp(rule_id="xccdf_org.ssgproject.content_rule_banner_etc_issue_cis", action="disable"),
        TailoringOp(rule_id="xccdf_org.ssgproject.content_rule_banner_etc_issue_net", action="disable"),
        TailoringOp(rule_id="xccdf_org.ssgproject.content_rule_banner_etc_issue_net_cis", action="disable"),
        TailoringOp(rule_id="xccdf_org.ssgproject.content_rule_banner_etc_motd_cis", action="disable"),
        TailoringOp(rule_id="xccdf_org.ssgproject.content_rule_dconf_gnome_banner_enabled", action="disable"),
        TailoringOp(rule_id="xccdf_org.ssgproject.content_rule_dconf_gnome_login_banner_text", action="disable"),
    ]
```

Excluded `sshd_enable_warning_banner_net` — our `ssh_config_apply` rule's drop-in DOES enable the sshd Banner directive, so that check is satisfied (not mooted).

`exception_entry` mirrors alma9 verbatim (text from `_meta/banner_text.py` is shared).

### `ssh_config_apply` — no change

alma9's `emit_tailoring` is empty; ubuntu mirrors.

### `crypto_policy` — 5 alma9 ops → 4 ubuntu ops; same `cfg.crypto.policy` gating

The alma9 implementation only emits the cipher disables when `cfg.crypto.policy != STIG`. Mirror that branching exactly.

```python
def emit_tailoring(self, cfg):
    if cfg.crypto.policy.value == "STIG":
        return []
    return [
        TailoringOp(rule_id="xccdf_org.ssgproject.content_rule_is_fips_mode_enabled", action="disable"),
        TailoringOp(rule_id="xccdf_org.ssgproject.content_rule_sshd_use_approved_ciphers_ordered_stig", action="disable"),
        TailoringOp(rule_id="xccdf_org.ssgproject.content_rule_sshd_use_approved_kex_ordered_stig", action="disable"),
        TailoringOp(rule_id="xccdf_org.ssgproject.content_rule_sshd_use_approved_macs_ordered_stig", action="disable"),
    ]
```

Note `is_fips_mode_enabled` (Ubuntu naming) vs `enable_fips_mode` (alma9 naming) — same concept. The 4 sshd-cipher rules carry an `_ordered_stig` suffix on Ubuntu (the underlying STIG-strict ordered-cipher check, not the looser ordering-free check).

`exception_entry` mirrors alma9's runtime-computed format (text embeds the operator's chosen policy value).

### `faillock_safety` — 2 set_value + 1 disable (alma9) → 2 set_value (ubuntu); drop the disable

The faillock variables (`var_accounts_passwords_pam_faillock_unlock_time`, `..._deny`) exist verbatim on ubuntu2404 (variables are typically SSG-shared regardless of distro). The `accounts_passwords_pam_faillock_even_deny_root` rule does NOT exist on ubuntu2404 — drop that op.

```python
def emit_tailoring(self, cfg):
    f = cfg.overrides.faillock
    ops = [
        TailoringOp(
            rule_id="xccdf_org.ssgproject.content_value_var_accounts_passwords_pam_faillock_unlock_time",
            action="set-value",
            value=str(f.unlock_time),
        ),
        TailoringOp(
            rule_id="xccdf_org.ssgproject.content_value_var_accounts_passwords_pam_faillock_deny",
            action="set-value",
            value=str(f.deny),
        ),
    ]
    # No `even_deny_root` rule on ubuntu2404 — alma9 disables that one
    # conditionally; ubuntu has nothing to disable.
    return ops
```

`exception_entry`: mirror alma9's runtime-computed summary + reason text.

### `auditd_actions` — 3 set_value (alma9) → 3 set_value (ubuntu); directly portable

All three auditd variables (`var_auditd_disk_full_action`, `_disk_error_action`, `_max_log_file_action`) exist verbatim on ubuntu2404.

```python
def emit_tailoring(self, cfg):
    a = cfg.overrides.auditd
    return [
        TailoringOp(rule_id="xccdf_org.ssgproject.content_value_var_auditd_disk_full_action",
                    action="set-value", value=a.disk_full_action.value),
        TailoringOp(rule_id="xccdf_org.ssgproject.content_value_var_auditd_disk_error_action",
                    action="set-value", value=a.disk_error_action.value),
        TailoringOp(rule_id="xccdf_org.ssgproject.content_value_var_auditd_max_log_file_action",
                    action="set-value", value=a.max_log_file_action.value),
    ]
```

`exception_entry`: mirror alma9 runtime-computed (SUSPEND/SUSPEND/ROTATE strict check, embeds operator-chosen values).

### `usbguard` — 3 ops (alma9) → 0 ops (ubuntu); exception_entry still applies

Ubuntu's SSG does NOT have usbguard rules (`grep usbguard docs/audit-story/ubuntu2404-rule-ids.txt` returns empty). Nothing to disable / select. But the exception_entry is still meaningful — the audit trail should still record "operator opted out of USBGuard."

```python
def emit_tailoring(self, cfg):
    # ubuntu2404 SSG (0.1.79-1) has no usbguard rules. alma9's
    # select/disable on package_usbguard_installed et al doesn't translate.
    return []

def exception_entry(self, cfg):
    if cfg.overrides.usbguard.enable:
        return None
    return ExceptionEntry(
        rule_id=meta.ID,
        summary=meta.EXCEPTION_SUMMARY,
        stig_rules_disabled=[],  # nothing actually disabled on ubuntu
        reason=meta.EXCEPTION_REASON,
    )
```

Note `stig_rules_disabled=[]` instead of `list(_USBGUARD_RULES)` (the alma9 pattern) — there's no Ubuntu rule list to record.

### `dod_root_ca` — 1 op (alma9) → 0 ops (ubuntu); exception_entry still applies

Ubuntu's SSG does NOT have `install_DoD_intermediate_certificates`. The closest hits (`only_allow_dod_certs`, `install_smartcard_packages`) have different semantics.

```python
def emit_tailoring(self, cfg):
    return []  # no equivalent rule on ubuntu2404

def exception_entry(self, cfg):
    return ExceptionEntry(
        rule_id=meta.ID,
        summary=meta.EXCEPTION_SUMMARY,
        stig_rules_disabled=[],
        reason=meta.EXCEPTION_REASON,
    )
```

## Files touched

For each of the 6 rules with new tailoring (banner_text, crypto_policy, faillock_safety, auditd_actions, usbguard, dod_root_ca):

- **Modify:** `src/ks_gen/rules/ubuntu2404/<rule>.py` — replace deferred `return []` / `return None` with the real implementations described above.
- **Modify:** `tests/rules/test_ubuntu2404_<rule>.py` — replace the "deferred returns empty" tests with assertions on the specific TailoringOps + ExceptionEntry shapes.

For the 8 rules with no tailoring work: no edits.

**Modify:** `tests/golden/__snapshots__/test_ubuntu_minimal.ambr` — snapshot regen. Expected changes:
- `Tailored XCCDF rules: 0` → `Tailored XCCDF rules: 9` (or whatever count the actual default-config rules produce — banner_text alone adds 6; faillock + auditd add var-sets that are counted in tailoring but as "set-value" not "disable"; usbguard + dod_root_ca on default cfg don't fire emit_tailoring meaningfully because `applies` always True but tailoring ops list is empty / conditional)
- New "Tailored XCCDF rules" table populated.
- New "Rule exception details" entries for whichever exception_entry returns are non-None on default config.

## Tests

Per-rule: replace the deferred-tests with concrete assertions:
- `test_<rule>_emit_tailoring_returns_specific_ops` — assert the exact list of TailoringOps the rule emits on default cfg.
- `test_<rule>_emit_tailoring_branches_on_cfg` (for crypto_policy + usbguard which have cfg-dependent ops).
- `test_<rule>_exception_entry_returns_populated` (for rules where exception_entry is non-None on default cfg).

Estimated test delta: +20-30 new test assertions across the 6 rules, replacing ~12 "deferred returns empty" tests.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| The `_ordered_stig` Ubuntu cipher rules may have semantically different intent than alma9's `_ordered` | Both check the same underlying sshd_config setting; the `_stig` suffix denotes the strict-STIG-ordering variant. ks-gen's crypto_policy moots the entire approved-cipher check regardless. |
| `set-value` ops on the variable IDs require the actions match the SSG profile's variable type | Phase 1 data + the variable values we're injecting (e.g., `SUSPEND`, `900`) match SSG's expected types — verified by the alma9 tests passing for years. |
| Snapshot regen produces large diff (Tailored XCCDF rules section populates) | Expected — it's the central deliverable. Inspect each new entry against the per-rule plan above. |
| New `stig_rules_disabled=[]` entries in exception_entry result in odd-looking exceptions.md output | Acceptable: the empty list correctly says "we recorded the exception but no SSG rules needed disabling on this distro." Matches the data accurately. |
| Ubuntu's SSG might rename rules in a future bump, invalidating our hardcoded IDs | Out of scope. Phase 1's `extract_ssg_rule_ids.py` + `cross-distro-rule-id-diff.md` lets us re-audit on bump. |

## CI parity

```bash
ruff check src tests scripts \
  && ruff format --check src tests scripts \
  && mypy \
  && pytest -q
```

Expected new test count delta: net +~10 (replace deferred-tests with concrete assertions; some are 1:1, some expand).

## Out of scope (for PR A only)

- Alma8 divergence + alma9 sweep — PR B of #127.
- New SSG rule IDs not currently emitted by alma9 (don't expand scope — just port the existing alma9 set).
- Ubuntu-specific rules that have no alma9 counterpart (e.g., `sshd_enable_warning_banner_net` is a positive check we satisfy; not a disable target).
- Datastream version bumping — out of scope until SSG ships an update we care about.
