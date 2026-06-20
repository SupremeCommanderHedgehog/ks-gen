# Phases 3.9 + 3.10 + 3.11 — bundled port: `usbguard`, `package_purge`, `dod_root_ca` to ubuntu2404

**Parent:** #81 ubuntu STIG autoinstall.
**Previous phases on this workstream:** 3.0 admin_user_and_keys +
ssh_keep_open (#94), 3.1 banner_text (#101), 3.2 ssh_config_apply
(#102), 3.3 time_servers (#104), 3.4 crypto_policy (#106), 3.5
faillock_safety (#108), 3.6 unattended_updates (#110), 3.7
auditd_actions (#112), 3.8 kernel_module_blacklist (#114).

## Goal

Port three rules to ubuntu2404 in a single bundled PR:

1. **Phase 3.9 — `usbguard`** — scaffolding-only port. Like alma9,
   `emit_post` is empty (the meaningful work is `emit_tailoring` to
   `select`/`disable` SSG rules and `exception_entry`, both of
   which are deferred per the phase 3.x audit-story pattern).
   `applies()` returns `True` so the rule lands in the Applied-rules
   count and listing for the eventual audit-story PR to reference.
2. **Phase 3.10 — `package_purge`** — `apt-get -y purge` mirror of
   the alma9 `dnf -y remove` rule. Operator-configured exclude list
   (`cfg.packages.excluded`) drives the late-command. `|| true`
   squashes "package not installed / unable to locate" exits so
   stale exclude entries don't fail the install.
3. **Phase 3.11 — `dod_root_ca`** — scaffolding-only port. Like
   alma9, `emit_post` is empty (the meaningful work is
   `emit_tailoring` to disable the SSG `install_DoD_intermediate_certificates`
   rule and `exception_entry`, both of which are deferred). `applies()`
   returns `not cfg.overrides.dod_root_ca.install` — applies when the
   operator is NOT installing the DoD CA bundle (default, civilian use).

## Why bundled

These three ports are independent at the code level (no shared
schema changes, no rule deps) but interact at the snapshot level:
each bumps the `Applied rules: N` count and adds a line to the
Applied-rules listing in `tests/golden/__snapshots__/test_ubuntu_minimal.ambr`.
Doing them as three separate PRs serialises the merges and forces
PRs #2 and #3 to rebase + regen the snapshot just for that count
bump (no real code conflict). Bundling lets the snapshot regen run
once and the CI cycle run once.

## Non-goals

- **ssg-ubuntu2404-ds.xml tailoring + exception text** for any of
  the three rules. Deferred to the coordinated audit-story PR per
  the established phase-3.x pattern (the same deferral applied to
  phases 3.1 through 3.8).
- **Schema changes.** `UsbguardCfg`, `PackagePurgeCfg`, `DodRootCaCfg`,
  and `Packages.excluded` are all distro-neutral in
  `src/ks_gen/config.py` — no edits.
- **Cross-distro mapping of `cfg.packages.excluded`.** The default
  excluded list is RHEL-flavored (`telnet-server`, `rsh-server`,
  `tftp-server`, `vsftpd`, `ypserv`). On Ubuntu, the equivalent apt
  names differ (`telnetd`, `inetutils-telnetd`, `tftpd-hpa`, etc.).
  This is a known schema-level cross-distro gap; `|| true`
  defensively handles the default-list-on-Ubuntu case (apt returns
  exit 100 for "Unable to locate package", squashed). Operators
  configure Ubuntu-flavored exclude names in `host.yaml` for actual
  purges. Fixing the default to be distro-aware is a separate
  feature.
- **USBGuard service enablement.** alma9's `emit_post` is empty;
  this port mirrors. If/when the audit-story PR lands and operators
  set `usbguard.enable=True`, a follow-up rule edit (in BOTH alma9
  and ubuntu2404 to keep parity) will need to install the
  `usbguard` package + enable the service + populate initial
  policy. Out of scope for this PR.
- **DoD CA bundle install (the `install=True` branch).** alma9's
  `emit_post` is empty even when `install=True` — the
  install-the-bundle logic was never implemented (the operator-set
  flag only affects tailoring/exception). Ubuntu mirrors. Follow-up
  in the audit-story PR if ever needed.

## Architecture

Three new rule modules + three new test files. Shared
`src/ks_gen/rules/_meta/{usbguard,package_purge,dod_root_ca}.py`
(ID, SUMMARY, DEPENDS_ON, EXCEPTION_*) are untouched.

### Phase 3.9 — `usbguard`

```python
def applies(self, cfg: HostConfig) -> bool:
    return True

def emit_post(self, cfg: HostConfig) -> str:
    return ""

def emit_packages(self, cfg: HostConfig) -> list[str]:
    return []

def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
    # Deferred: ssg-ubuntu2404-ds.xml usbguard rule IDs land in
    # the audit-story PR.
    return []

def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
    # Deferred: paired with emit_tailoring above.
    return None
```

`applies = True` mirrors the alma9 rule unconditionally. The
empty `emit_post` is intentional — the writer's `if body:` guard
in `_build_ubuntu2404_bundle` (writer.py:124) means no
`# rule:usbguard` band lands in `late-commands`. The rule still
appears in the Applied-rules count + listing in `exceptions.md`.

### Phase 3.10 — `package_purge`

```python
def applies(self, cfg: HostConfig) -> bool:
    return cfg.overrides.package_purge.enable and bool(cfg.packages.excluded)

def emit_post(self, cfg: HostConfig) -> str:
    pkgs = " ".join(cfg.packages.excluded)
    return (
        "# Remove disallowed packages (no-op if not installed)\n"
        f"DEBIAN_FRONTEND=noninteractive apt-get -y purge {pkgs} || true\n"
    )

def emit_packages(self, cfg: HostConfig) -> list[str]:
    return []

def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
    return []

def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
    return None
```

Design notes:
- `apt-get -y purge` (not `apt purge` — `apt` is interactive and
  not script-safe). `-y` is the non-interactive yes flag.
- `DEBIAN_FRONTEND=noninteractive` prevents any conffile-removal
  prompts from blocking — late-commands has no TTY.
- `|| true` mirrors the alma9 `|| true` and squashes:
  - `exit 100`: "Unable to locate package" (default RHEL-flavored
    excluded list against Ubuntu archive).
  - `exit 1`: package was already removed in a prior run.
- No `apt-get update` first — the install media already populated
  apt's cache during package selection; no fresh metadata needed
  to remove already-installed packages. (`apt-get update` would
  also require network reachability inside late-commands, which
  is not guaranteed in the Subiquity chroot.)

### Phase 3.11 — `dod_root_ca`

```python
def applies(self, cfg: HostConfig) -> bool:
    return not cfg.overrides.dod_root_ca.install

def emit_post(self, cfg: HostConfig) -> str:
    return ""

def emit_packages(self, cfg: HostConfig) -> list[str]:
    return []

def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
    # Deferred: ssg-ubuntu2404-ds.xml DoD certificate rule ID
    # lands in the audit-story PR.
    return []

def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
    # Deferred: paired with emit_tailoring above.
    return None
```

`applies = not install` mirrors alma9 exactly — the rule "fires"
when the operator is opting OUT of installing the DoD CA bundle,
which is the civilian default (`DodRootCaCfg.install = False`).
The empty `emit_post` is intentional (matches alma9 — the
install-the-bundle branch was never implemented; only the
tailoring/exception branch exists, and both are deferred here).

### Bundle pipeline integration

All three rules plug into the existing ubuntu2404 bundle pipeline:
- Only `package_purge` contributes a `# rule:package_purge` band to
  `late-commands` (and only when `applies` is True). usbguard and
  dod_root_ca contribute nothing to `late-commands`.
- None of the three contribute `emit_packages` entries (no
  `autoinstall.packages:` additions).
- All three contribute to the Applied-rules count + listing in
  `exceptions.md` when `applies` is True.
- `emit_tailoring` returns `[]` for all three (deferred to
  audit-story PR).

No changes to `writer.py`, `skeleton.py`, the user-data template,
or the config schema.

## Files touched

- **Create:** `src/ks_gen/rules/ubuntu2404/usbguard.py`
- **Create:** `tests/rules/test_ubuntu2404_usbguard.py`
- **Create:** `src/ks_gen/rules/ubuntu2404/package_purge.py`
- **Create:** `tests/rules/test_ubuntu2404_package_purge.py`
- **Create:** `src/ks_gen/rules/ubuntu2404/dod_root_ca.py`
- **Create:** `tests/rules/test_ubuntu2404_dod_root_ca.py`
- **Modify:** `tests/golden/__snapshots__/test_ubuntu_minimal.ambr`
  (single bundled regen — three new rules at once)

## Tests

### Phase 3.9 — `usbguard` (6 tests)

1. `test_applies_always_returns_true` — default cfg → True
   (matches alma9 unconditional applies, the meaningful enable/disable
   distinction lives in the deferred tailoring/exception methods).
2. `test_emit_post_returns_empty` — `""` (writer skips empty bodies;
   no `# rule:usbguard` band in late-commands).
3. `test_emit_packages_returns_empty` — `[]` (audit-story PR will
   add `usbguard` to packages when service install is implemented).
4. `test_emit_tailoring_returns_empty_deferred` — `[]`.
5. `test_exception_entry_returns_none_deferred` — `None`.
6. `test_id_and_summary_come_from_shared_meta` (+ `depends_on == []`).

### Phase 3.10 — `package_purge` (10 tests)

1. `test_applies_when_enabled_and_has_excluded` — default cfg (enable=True,
   excluded=5 RHEL-flavored entries) → True.
2. `test_applies_short_circuits_when_disabled` — `enable=False` → False.
3. `test_applies_short_circuits_when_excluded_empty` — `excluded=[]`
   → False (no work to do).
4. `test_post_uses_apt_get_purge` — `apt-get -y purge` present.
5. `test_post_uses_debian_frontend_noninteractive` — `DEBIAN_FRONTEND=noninteractive`
   present (no TTY in late-commands; would hang on a conffile prompt).
6. `test_post_squashes_failures_with_or_true` — `|| true` present at
   end-of-line (mirrors alma9; squashes "unable to locate package" exits).
7. `test_post_lists_all_default_excluded_packages` — each of
   `telnet-server`, `rsh-server`, `tftp-server`, `vsftpd`, `ypserv`
   appears in the rendered command.
8. `test_post_reflects_excluded_override` — operator-set
   `excluded=["apache2", "nginx"]` lands; default 5 absent.
9. `test_emit_packages_returns_empty` — `[]`.
10. `test_emit_tailoring_+ exception_entry deferred + protocol contract`
    (3 sub-asserts in one test, mirrors prior phase test density).

### Phase 3.11 — `dod_root_ca` (6 tests)

1. `test_applies_when_install_is_false` — default cfg (install=False)
   → True (the rule "fires" when NOT installing DoD CA, mirroring
   alma9).
2. `test_applies_short_circuits_when_install_is_true` —
   `install=True` → False.
3. `test_emit_post_returns_empty` — `""`.
4. `test_emit_packages_returns_empty` — `[]`.
5. `test_emit_tailoring_returns_empty_deferred` + `exception_entry_returns_none_deferred`
   (2 sub-asserts).
6. `test_id_and_summary_come_from_shared_meta` (+ `depends_on == []`).

Total: **22 new tests** across three test files.

## Snapshot regen

After all tests pass and all three rule modules exist, run
`pytest tests/golden/ --snapshot-update -k ubuntu_minimal`.

Expected diff (and ONLY these changes):

1. `- Applied rules: 10` → `+ Applied rules: 13` in the Summary
   section (count bumps by 3 — all three rules' `applies` returns
   True against the default ubuntu_minimal config).
2. Three new entries in the Applied-rules list at their
   alphabetical positions:
   - `dod_root_ca` — after `crypto_policy`, before `faillock_safety`
   - `package_purge` — after `kernel_module_blacklist`, before `ssh_keep_open`
     (`p` < `s`)
   - `usbguard` — after `unattended_updates` (last alphabetically)
3. ONE new `# rule:package_purge ──────────...` band inside
   `late-commands` containing:
   ```
   # Remove disallowed packages (no-op if not installed)
   DEBIAN_FRONTEND=noninteractive apt-get -y purge telnet-server rsh-server tftp-server vsftpd ypserv || true
   ```
4. **No** `# rule:usbguard` or `# rule:dod_root_ca` bands
   (`emit_post` returns `""` → writer's `if body:` guard at
   writer.py:124 skips them).
5. **No** addition to `autoinstall.packages:` (none of the three
   contribute `emit_packages`).

No alma9 snapshots affected.

### Merge-order assumption

The 10 → 13 count assumes this branch sits on main at `8a1f2a4`
(release 0.22.0, includes phases 3.0–3.8 = 10 ubuntu rules counting
admin_user_and_keys). If unrelated work landed first that added
another rule, regenerate and confirm "+3 your rules, nothing else."

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Default `excluded` list (RHEL-flavored) renders the package_purge late-command useless on Ubuntu | `\|\| true` defensively squashes the resulting exit 100. The rule still emits the line, so an operator scanning logs sees what was attempted. Schema-level cross-distro mapping is a known follow-up. |
| `apt-get -y purge` prompts about conffile removal | `DEBIAN_FRONTEND=noninteractive` neutralises any tty prompt. apt-get without a TTY also can't escalate to interactive mode. |
| usbguard scaffolding-only landing confuses operators who set `usbguard.enable=True` | The Applied-rules listing in `exceptions.md` documents that the rule is applied; the deferred tailoring/exception methods mean operators don't yet get differential behavior on the flag. The audit-story PR (#81 future phase) wires this up. Documented in spec non-goals. |
| dod_root_ca scaffolding-only landing — operator might expect `install=True` to install the CA bundle | alma9 has the same gap (the install branch was never implemented). Ubuntu mirrors. If anyone needs the install path, a coordinated alma9+ubuntu2404 update lands then. |
| Bundled PR is reviewer-heavy (3 rules + tests at once) | Plan groups changes by rule (each rule = 2-3 commits). Reviewer can read one rule + its tests at a time. Spec doc surfaces the per-rule design decisions. |
| Snapshot regen masks an unintended diff in one of the three rules | The plan's snapshot-diff inspection step enumerates EXACTLY what should change (`+3 count`, 3 new Applied-rules listing entries, 1 new band). Any other diff = stop and investigate. |

## CI parity check before push

Per `CLAUDE.md`:

```bash
ruff check src tests \
  && ruff format --check src tests \
  && mypy \
  && pytest -q
```

If `ruff format --check` fails, fix with `ruff format src tests`.

Expected test count: `868 + 22 = 890` (or close, depending on what's
landed since v0.22.0).

## Out of scope (deferred)

- All three rules' `emit_tailoring` + `exception_entry` (audit-story PR).
- Schema-level cross-distro mapping for `cfg.packages.excluded`.
- USBGuard service install + enable on `enable=True`.
- DoD CA bundle install on `install=True`.
- data_disks_preserve port (phase 3.12 — separate PR).
- container_host port (issue #88 — separate PR).
