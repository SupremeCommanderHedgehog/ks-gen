# ks-gen verify --host — design

Date: 2026-06-07
Target release: v0.3.0
Tracks GitHub issue: [#5](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/5)
Status: design approved, implementation plan to follow

## 1. Problem

`ks-gen` builds STIG-compliant kickstarts and the install-time `%post` block
runs `oscap xccdf eval --remediate` against a per-host tailoring. Today an
operator can install a host and trust that remediation ran (logs and ARF land
under `/root/`), but there is no scripted way to re-evaluate the host later and
confirm it hasn't drifted, or to reconcile remaining failures against the
host's declared `host.yaml` exceptions.

`verify` closes that loop. After implementation, every other v0.3+ change
(LUKS, `disk.layout:`, wizard expansion) can be confirmed end-to-end against a
real Hyper-V install rather than relying on lint + snapshot tests alone.

## 2. Goals

- Re-run `oscap xccdf eval` on a deployed host against its install-time
  tailoring, and report:
  - **Compliance**: rules failing now that are not covered by a declared
    exception in workstation `host.yaml`.
  - **Drift**: rules failing now that were passing at install time, compared
    against the install-time ARF persisted at
    `/root/oscap-remediation-results.xml`.
- Single-host, workstation-driven, single invocation. Operator loops externally
  if a fleet sweep is needed.
- Exit-code distinguishable so shell integration is unambiguous
  (clean / failures detected / transport problem).

## 3. Non-goals (deferred — see linked issues)

- Batch / fleet mode (#10)
- Workstation-captured baseline / `--capture-baseline` (#11)
- Tailoring drift detection (`host.yaml` vs. `/root/tailoring.xml`) (#12)
- Continuous on-host self-check / systemd timer (#13)
- Auto-suggest `host.yaml` exception entries (#14)
- HTML report generation (#15)
- Password sudo / direct root SSH (#16)
- Trend / history tracking across multiple runs (#17)

## 4. User-facing surface

### 4.1 Command shape

```
ks-gen verify --host <addr> --config <path/to/host.yaml>
              [--user <admin>]           # default: cfg.user.admin.name
              [--ssh-opts "<args>"]      # raw extra args appended to BOTH ssh and scp invocations
              [--format table|json]      # default: table
              [--arf-out <dir>]          # default: tempdir, removed on exit
              [--keep-arf]               # opt-in: persist ARFs even on success
              [--no-drift]               # skip install-time-ARF probe/pull; compliance-only
              [--timeout <secs>]         # oscap run timeout, default 600
```

### 4.2 Exit codes

Extends the existing `ExitCode` IntEnum in `src/ks_gen/loader.py`.

| Code | Name | Meaning |
|---|---|---|
| 0 | `OK` | All evaluated rules pass; no drift detected. |
| 1 | `USAGE` | Bad CLI args / unreachable file (existing). |
| 2 | `CONFIG_INVALID` | host.yaml fails validation (existing). |
| 5 | `TOOL_MISSING` | system `ssh` or `scp` not on PATH (existing). |
| 6 | `VERIFY_FAIL` | at least one rule fails on the live host. |
| 7 | `TRANSPORT_FAIL` | ssh connection error, sudo prompt, oscap non-zero with no usable ARF. |

`VERIFY_FAIL` covers both "new failure" and "regression from install"; the
categorization shows in the report output, not the exit code. Single failure
exit code keeps shell integration simple
(`if ks-gen verify ...; then ... fi`).

### 4.3 Operator-facing error format

Single line, prefix-tagged, machine-greppable. Full stderr is appended on
following lines with two-space indent so it's clearly secondary:

```
ks-gen verify: transport failure: ssh exit 255: <stderr first line>
ks-gen verify: sudo prompt detected on <host> as <user>: passwordless sudo is required
ks-gen verify: oscap not runnable on <host>: tailoring missing at /root/tailoring.xml
```

## 5. Architecture

### 5.1 Module layout

```
src/ks_gen/
  cli.py                          # +1 command: verify_cmd
  loader.py                       # +2 enum members: VERIFY_FAIL, TRANSPORT_FAIL
  verify/
    __init__.py                   # public surface: run_verify(...)
    ssh.py                        # subprocess wrappers: ssh_exec, scp_pull
    remote.py                     # orchestrates remote oscap run + ARF pull
    arf.py                        # ARF parser → {rule_id: result_state}
    reconcile.py                  # current × install × expected → rows
    report.py                     # table + json renderers
    errors.py                     # VerifyError hierarchy
tests/
  verify/
    test_ssh.py                   # subprocess mocked
    test_arf.py                   # fixture ARFs (pass/fail/mixed/empty)
    test_reconcile.py             # table-driven; pure function
    test_report.py                # golden snapshots (syrupy)
    test_cli_verify.py            # CliRunner with run_verify monkeypatched
    test_integration_end_to_end.py
    fixtures/
      arf-clean.xml
      arf-mixed.xml
      arf-install-baseline.xml
```

### 5.2 Module responsibilities and boundaries

- **`ssh.py`** — the only module that calls `subprocess`. Returns
  `(stdout, stderr, exit_code)` or raises a typed `SshError`. Mockable; all
  other modules consume its interface, not `subprocess` directly.
- **`remote.py`** — composes `ssh.py` calls into the "run oscap, fetch two
  ARFs" workflow. Knows tempfile paths on the host
  (`/tmp/ksgen-verify-current.arf.xml`) and best-effort cleanup.
- **`arf.py`** — pure function `parse_arf(text: str) -> dict[str, RuleResult]`.
  No I/O. stdlib `xml.etree.ElementTree` only. No new dependency.
- **`reconcile.py`** — pure function. Takes three inputs (current ARF results,
  install ARF results or `None`, expected-failures set from `host.yaml`) and
  produces a `VerifyReport` dataclass. No I/O. Table-driven tests.
- **`report.py`** — `render_table(report)` / `render_json(report)`. Pure
  rendering.
- **`errors.py`** — `VerifyError` base, subclasses for transport / sudo /
  oscap / parse failures. `cli.verify_cmd` maps these to exit codes.

`run_verify(cfg, host, options) -> VerifyReport` is the public seam — what a
future `--hosts` batch mode (#10) calls in a loop.

## 6. Data flow

```
1. cli.verify_cmd
   ├─ load_host_config(--config) → HostConfig         (loader.py, existing)
   ├─ resolve ssh user: --user OR cfg.user.admin.name
   ├─ check `ssh` and `scp` on PATH                   → TOOL_MISSING if not
   └─ call verify.run_verify(cfg, host, opts)

2. verify.run_verify
   ├─ expected_failures = derive_expected(cfg)
   │     → set of XCCDF rule ids tailored-out by rules + cfg.exceptions
   │       (same source render_exceptions_md uses)
   ├─ remote.collect_arfs(host, user, opts)
   │     ├─ ssh: sudo -n test -r /root/tailoring.xml   → SudoPromptError on prompt
   │     ├─ ssh: sudo -n oscap xccdf eval
   │     │           --tailoring-file /root/tailoring.xml
   │     │           --profile xccdf_org.ssgproject.content_profile_<profile>
   │     │           --fetch-remote-resources
   │     │           --results-arf /tmp/ksgen-verify-current.arf.xml
   │     │           /usr/share/xml/scap/ssg/content/<scap_content>
   │     │     → oscap exit codes: 0=all pass, 2=some rules failed (NORMAL),
   │     │       anything else → OscapInvocationError
   │     ├─ scp pull /tmp/ksgen-verify-current.arf.xml → workstation tempdir
   │     ├─ if not opts.no_drift:
   │     │     ├─ ssh: sudo -n test -r /root/oscap-remediation-results.xml
   │     │     │     → if missing, install_arf=None; drift section degrades
   │     │     └─ scp pull /root/oscap-remediation-results.xml (if present)
   │     │   else:
   │     │     install_arf=None  (skipped entirely; report banner notes this)
   │     ├─ ssh: sudo -n rm -f /tmp/ksgen-verify-current.arf.xml  (cleanup)
   │     └─ return (current_text, install_text_or_None)
   ├─ current = arf.parse_arf(current_text)
   ├─ install = arf.parse_arf(install_text) if install_text else None
   ├─ report  = reconcile.build_report(current, install, expected_failures,
   │                                   meta={host, user, ts, …})
   └─ return report

3. cli.verify_cmd (continued)
   ├─ render report (table | json) per --format
   ├─ if --keep-arf or --arf-out: copy current.arf.xml (+install if present)
   │     to <arf-out>/<hostname>-<UTC>.current.arf.xml etc.
   └─ exit: OK if report.is_clean else VERIFY_FAIL
```

`verify` runs the same `oscap xccdf eval` flags as install-time, minus
`--remediate`. `--fetch-remote-resources` is included to match install-time
semantics (rules tied to the AlmaLinux OVAL feed are evaluated, not silently
skipped); on air-gapped hosts the fetch failure is logged but eval proceeds —
identical handling to install-time, documented in MANUAL.md §3.2.

## 7. Types

### 7.1 RuleResult (from `arf.parse_arf`)

```python
@dataclass(frozen=True)
class RuleResult:
    rule_id: str                  # xccdf_org.ssgproject.content_rule_…
    result: Literal["pass", "fail", "notapplicable", "notchecked",
                    "notselected", "error", "unknown", "fixed",
                    "informational"]
```

### 7.2 VerifyRow / VerifyReport (from `reconcile.build_report`)

```python
@dataclass(frozen=True)
class VerifyRow:
    rule_id: str
    current: str                  # result on the host now
    install: str | None           # result at install time, or None
    expected: bool                # declared as a tailored exception?
    category: Literal["clean", "expected_fail", "new_fail", "regression",
                      "incomplete"]

@dataclass(frozen=True)
class VerifyReport:
    host: str
    user: str
    timestamp_utc: str
    rows: tuple[VerifyRow, ...]
    install_baseline_available: bool

    @property
    def is_clean(self) -> bool:
        """True iff no new_fail and no regression rows."""
```

### 7.3 Reconciliation table

| `current` | `install` | declared exception? | `category` |
|---|---|---|---|
| `pass` / `fixed` | * | * | `clean` (omitted from the rendered table; counted in the summary line) |
| `notapplicable` / `notselected` / `informational` | * | * | `clean` (rule didn't apply or wasn't selected — not an actionable signal) |
| `fail` | * | yes | `expected_fail` |
| `fail` | `fail` | no | `new_fail` (still failing from install — never remediated) |
| `fail` | `pass` / `fixed` / `notapplicable` / `notselected` / `informational` | no | `regression` (drifted since install) |
| `fail` | n/a (no baseline) | no | `new_fail` (best we can say without baseline) |
| `error` / `notchecked` / `unknown` | * | * | `incomplete` — not counted toward clean/dirty |

Rule-set asymmetry: if the host's `scap-security-guide` was upgraded
post-install, the current and install ARFs may not contain the same rule set.
`reconcile.build_report` handles this as: rules only in `current` → treat
normally (no install row, `install=None`); rules only in `install` → ignore
(rule was removed from the current eval, no actionable info).

## 8. Error handling

`VerifyError` hierarchy in `errors.py`. Every error carries a one-line operator
message and maps to an exit code in `cli.verify_cmd`. No exception leaks past
`cli.py` as a stack trace.

```python
class VerifyError(Exception):
    exit_code: ExitCode

class SshConnectError(VerifyError):        # TRANSPORT_FAIL
    """ssh exit 255 — host unreachable, key rejected, kex failure."""

class SudoPromptError(VerifyError):        # TRANSPORT_FAIL
    """sudo -n returned 'a password is required' or non-zero before oscap."""

class OscapInvocationError(VerifyError):   # TRANSPORT_FAIL
    """oscap exit not in {0, 2}. Tailoring missing, profile typo,
    scap-security-guide unpopulated, OOM."""

class ArfMissingError(VerifyError):        # TRANSPORT_FAIL
    """oscap reported success but the ARF file isn't on the host,
    or scp pulled 0 bytes."""

class ArfParseError(VerifyError):          # TRANSPORT_FAIL
    """ARF is XML but doesn't look like SCAP ARF — wrong namespace,
    no TestResult element."""

class ToolMissingError(VerifyError):       # TOOL_MISSING
    """system ssh or scp not on PATH."""
```

`VERIFY_FAIL` is not an exception — it's `cli.verify_cmd` inspecting
`report.is_clean` after a successful run and exiting `6` when there are
unhandled failures. Transport problems and "rules failed" are categorically
different and exit-code-distinct.

### 8.1 Specific failure-mode handling

| Scenario | Behavior |
|---|---|
| `ssh` exit 255 | `SshConnectError`. Print stderr first line (typically informative: "Connection refused", "Permission denied"). |
| `sudo` wants a password | Detected via `sudo -n test -r /root/tailoring.xml` probe *before* the oscap run. `SudoPromptError` with a pointer to the `nopasswd_yes` invariant. |
| `oscap` exit 1/3/127 | `OscapInvocationError` with captured stderr. Common cause: scap-security-guide not installed (drift). |
| `oscap` exit 2 | Normal — rules failed. Proceed to ARF parse. |
| `/root/tailoring.xml` missing | `OscapInvocationError` ("install-time tailoring not present — host may not have been provisioned by ks-gen"). Hard fail. |
| `/root/oscap-remediation-results.xml` missing | Soft fail: `install_baseline_available=False`, drift comparison skipped, table shows a banner "drift comparison skipped: install-time ARF missing on host". Compliance is still computed. |
| ARF on host present but 0 bytes | `ArfMissingError`. Don't silently treat as "all pass". |
| `--timeout` exceeded | Kill the ssh subprocess. `OscapInvocationError("oscap timed out after Ns")`. Tmpfile on host may leak — cleanup is best-effort. |
| Workstation tempdir cleanup | `tempfile.TemporaryDirectory` context manager unless `--arf-out` / `--keep-arf` is set. |
| Ctrl-C mid-run | Propagate `KeyboardInterrupt`. Best-effort host-side cleanup via `finally` running `rm -f /tmp/ksgen-verify-current.arf.xml`. |

## 9. Testing

All tests use stdlib + existing project deps (pytest, syrupy). No live SSH, no
real oscap.

### 9.1 Unit tests by module

| Module | Approach | Key cases |
|---|---|---|
| `ssh.py` | Mock `subprocess.run`. Construct synthetic `CompletedProcess` for stdout/stderr/returncode. | exit 0 happy path; exit 255 → `SshConnectError`; sudo-prompt stderr → `SudoPromptError`; PATH-missing → `ToolMissingError`. |
| `arf.py` | Pure function, real fixture XMLs. | small all-pass ARF; mixed pass/fail; ARF with `error` and `notapplicable` results; truncated ARF → `ArfParseError`; wrong-root-element XML → `ArfParseError`. |
| `reconcile.py` | Table-driven, inline dicts. | every row of the reconciliation table from §7.3; `install=None` path; rule in expected_failures but `current=pass` (over-specified exception — no warning, classified `clean`); rule in current but not install (new rule introduced in tailoring) — categorized by current-state only. |
| `report.py` | syrupy snapshots in `tests/verify/__snapshots__/`. | clean report; report with 1 of each category; report with no baseline; `--format json` shape. |
| `cli.py` (`verify_cmd`) | Typer `CliRunner` with `verify.run_verify` monkeypatched. | exit-code mapping for every `ExitCode` value; `--config` missing file; `--format json` flag plumbing; `--keep-arf` copies the file. |

### 9.2 Integration test

`tests/verify/test_integration_end_to_end.py` wires the real `arf.py` +
`reconcile.py` + `report.py` together against fixture ARFs and a fixture
`host.yaml`. Mocks only `ssh.py` (returns canned ARF text). Catches
integration bugs that pure unit tests miss.

### 9.3 Fixtures

Small, hand-authored ARFs (~30–50 lines each), not real oscap output. Three
baseline files cover all reconciliation paths:

- `arf-clean.xml` — 3 rules, all pass.
- `arf-mixed.xml` — 3 pass, 2 fail (one matches an exception in the
  fixture `host.yaml`, one doesn't), 1 error.
- `arf-install-baseline.xml` — same 6 rules, all pass at install time. Diffed
  against `arf-mixed.xml` produces 1 regression + 1 new_fail + 1
  expected_fail + 1 incomplete.

### 9.4 Lint integration

`ks-gen verify` invokes nothing from `lint.py`. Lint validates generated
`ks.cfg` artifacts; verify operates on live hosts. No new lint invariants.

### 9.5 Local CI parity

The project's standard chain
(`ruff check && ruff format --check && mypy && pytest -q`) covers all of the
above. No new tooling.

## 10. Documentation deltas (in scope for this change)

- `MANUAL.md`: new section "Post-install verification" describing the command,
  prerequisites (passwordless sudo, ssh access, install-time `/root/`
  artifacts), output reading, exit-code semantics.
- `README.md`: one-line addition to the command summary table.
- `MINIMAL-TEST.md`: optional final step "Run `ks-gen verify`" closing the
  Hyper-V acceptance loop.

## 11. Open issues at design time

None. All design questions surfaced during brainstorming are resolved:
verify mode (compliance + drift), contract source (workstation `host.yaml`),
SSH transport (system ssh shell-out), privilege model (passwordless sudo),
scope (single host).

## 12. References

- Issue #5 (this feature): https://github.com/SupremeCommanderHedgehog/ks-gen/issues/5
- Deferred follow-ups: #10–#17
- Install-time architecture: `docs/superpowers/specs/2026-06-01-alma-stig-kickstart-design.md`
- `%post`/`%addon` chroot-boundary lesson:
  `docs/superpowers/specs/2026-06-01-tailoring-pre-fetcher-design.md`
- `hd:LABEL=` oscap transport split:
  `docs/superpowers/specs/2026-06-06-hd-oscap-transport-design.md`
- `--fetch-remote-resources` at install time:
  `docs/superpowers/specs/2026-06-06-oscap-fetch-remote-resources-design.md`
