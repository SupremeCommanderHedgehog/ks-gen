# `ks-gen verify` — workstation-captured baseline — design

**Issue:** [#11 — ks-gen verify: workstation-captured baseline (--capture-baseline)](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/11)

**Status:** draft 2026-06-09

**Goal:** Let operators capture an ARF on the workstation at a moment
of their choosing (typically after manual post-install review) and use
that captured file as the drift baseline on subsequent `verify` runs,
in place of the install-time ARF at
`/root/oscap-remediation-results.xml`. Closes the v0.3-era gap where
the install ARF is the only available baseline — useful when manual
fixes have moved the host away from install state, or when an
upstream scap-security-guide upgrade made the install ARF reference
rules that no longer exist.

## Background

`ks-gen verify` (shipped v0.3.0) uses the host's
`/root/oscap-remediation-results.xml` (the install-time ARF written
by the kickstart `%post`) as the drift baseline. `categorize()` uses
`install` to distinguish `new_fail` (no baseline, or baseline was
incomplete) from `regression` (baseline was clean for that rule).

Two real operator scenarios push back against "install ARF is the
only baseline":

- **Manual review.** Operator finishes install, SSH's in, fixes some
  failing rules by hand (or accepts some as intentional via
  `host.yaml` exceptions), and wants future verify runs to treat
  *that* reviewed state as ground truth — not the dirty install
  state.
- **SSG upgrade staleness.** Months after install, an
  `scap-security-guide` upgrade adds/removes rules. The install ARF
  references rule IDs that no longer exist in the current SCAP
  content. Verify silently drops the orphan rules and the operator
  can't distinguish "rule passed" from "rule no longer evaluated."

The issue body calls this out as Approach B from the v0.3
brainstorming. v0.9.0's `--check-tailoring` (PR #39) handles the
workstation→host drift axis. This issue handles the
operator→reviewed-state axis: an explicit, operator-curated
alternative baseline.

## Goals

- A `--capture-baseline <path>` flag on `verify` that runs oscap on
  the host (the same oscap call `verify` already issues) and writes
  the resulting ARF to `<path>` on the workstation. The normal
  verify report still prints — capture is a *side effect* of a
  regular verify run, not a separate operation.
- A `--baseline <path>` flag that reads the captured ARF and uses
  it in place of the install ARF for reconcile. The host's `/root/`
  ARF is not pulled at all when `--baseline` is set.
- `--capture-baseline` and `--baseline` are mutually exclusive in a
  single invocation. Capturing and using are two operator intents
  on two different days.
- Reconcile semantics (the `categorize()` function and its
  `clean/expected_fail/new_fail/regression/incomplete` Categories)
  are unchanged. The baseline simply fills the slot previously held
  by `install`.
- Stale-baseline visibility: when the captured baseline references
  a rule_id absent from the current ARF, the report surfaces the
  orphan list as both a footer note (text mode) and a
  `baseline.orphans` array (JSON mode). Doesn't change exit codes.
- Backward-compat: when neither flag is set, byte-identical
  behavior to v0.9.0 (the install ARF still drives reconcile via
  the existing `--no-drift`-toggleable path).

## Non-goals (deferred)

- **Auto-discovery / sidecar convention.** No
  `hosts/<name>/baseline.arf.xml` lookup, no implicit "if a file
  next to host.yaml exists, use it." The issue body explicitly
  flagged the "which baseline am I comparing against?" confusion
  this would cause; explicit `--baseline <path>` makes it visible
  at invocation time.
- **Baseline file rotation, backup, or history.** Capture
  overwrites without backup. Operators who want history version
  the file (git, rsync, whatever). Different posture than the
  v0.8.0 `--apply` to host.yaml, which DID make a `.bak` —
  host.yaml is hand-curated and lossy to re-serialize, baseline
  ARFs are mechanical and reproducible.
- **`--capture-from install` mode.** Doesn't fetch the install ARF
  and call it a captured baseline. The "freeze the install ARF
  before it goes stale" story is real but YAGNI for v1 — operators
  can scp `/root/oscap-remediation-results.xml` to their workstation
  with one command and pass it to `--baseline`. Adding a flag for
  it just hides one scp behind verify.
- **Augment mode (use both install ARF AND captured baseline).**
  Three-way reconcile (current × baseline × install) is harder to
  explain, harder to test, and undermines the operator intent of
  `--baseline`: "I've reviewed THIS state; use it as ground truth."
- **`--baseline` for tailoring drift.** `--check-tailoring`
  compares the workstation-rendered tailoring against the host's
  `/root/tailoring.xml`. There is no "captured tailoring baseline"
  use case — the tailoring's source of truth is the workstation
  `host.yaml`, not a captured snapshot.
- **Multi-host / fleet baseline.** One host, one baseline file. The
  fleet workflow belongs to #10.
- **Encrypted / signed baseline file.** Plain XML. If chain-of-
  custody matters, version-control + GPG-sign at the operator's
  layer (the same way they version `host.yaml`).
- **Schema validation of the captured ARF beyond what `parse_arf`
  already does.** Existing checks (well-formed XML, has
  `<TestResult>`, has `<rule-result>` children) are enough. A
  baseline ARF that survives `parse_arf` is acceptable.

## Architecture

New module `src/ks_gen/verify/baseline.py` with pure parse/orphan
logic. Small `capture_current_arf` helper extracted from
`verify/remote.py`. `run_verify` gains two mutually-exclusive params.
`VerifyReport` gains an optional `baseline` field. Renderers surface
header/footer/JSON-block. Two new CLI flags + one mutual-exclusion
check.

### Data flow — `--capture-baseline <path>`

```
host.yaml ─► load cfg ────────────────────────────────────►
                                                          │
                                                          ▼
ssh/scp ─► collect_arfs (current=fresh oscap run,
                         install=/root/...   unchanged)
                                                          │
                                                          ▼
                                            parse + build_report (install used as today)
                                                          │
                                                          ▼
                                                  print verify report
                                                          │
                                                          ▼
                                  write arfs.current_text to <path> on workstation
                                                          │
                                                          ▼
                                       echo "captured baseline → <path>"
```

The file written is the **raw text** of the fresh-current ARF
(`arfs.current_text` from `collect_arfs`). We don't re-serialize
through our own parser. Whatever oscap produced is preserved verbatim
— including any non-XCCDF content that might be present.

### Data flow — `--baseline <path>`

```
host.yaml ─► load cfg ─►
                          │
                          ▼
read <path> from workstation ──► read_baseline ──► (results: dict, captured_utc: str | None)
                                                          │
ssh/scp ─► collect_arfs(no_drift=True)  ─►  current_text  │
                                                          ▼
                                            parse_arf(current_text)
                                                          │
                                                          ▼
                                build_report(current=..., install=baseline_results, ...)
                                                          │
                                                          ▼
                                               print verify report
```

`collect_arfs` is called with `no_drift=True` because the install
ARF pull is redundant — the captured baseline already fills the
`install=` slot in `build_report`. One fewer SSH round-trip per
`--baseline` run.

### Data model

```python
# verify/baseline.py

@dataclass(frozen=True)
class ReadBaseline:
    """A captured ARF loaded from disk."""

    results: dict[str, RuleResult]   # the parsed {rule_id: RuleResult}
    captured_utc: str | None         # ARF's <TestResult start-time>, or None
    path: Path                       # where it was loaded from (for report)


@dataclass(frozen=True)
class BaselineReport:
    """The 'baseline used' shape that gets attached to VerifyReport."""

    path: str            # file path as the operator specified it
    captured_utc: str | None
    orphans: tuple[str, ...]   # rule_ids in baseline but not current
```

`VerifyReport` (in `verify/reconcile.py`) gains:

```python
baseline: BaselineReport | None = None
```

Default `None` keeps every existing caller backward-compatible.
Naming chosen to read cleanly: `report.baseline is None` means
"install ARF (or nothing) was used"; `report.baseline is not None`
means "captured baseline at this path was used."

### Functions

```python
# verify/baseline.py

def read_baseline(path: Path) -> ReadBaseline:
    """Read and parse a captured baseline ARF from disk.

    Raises:
        ConfigError: path missing/unreadable (exit USAGE = 1).
        ArfMissingError: file exists but is 0 bytes (exit VERIFY_FAIL = 6).
        ArfParseError: file is not well-formed XML, has no TestResult,
            or has no rule-results (exit VERIFY_FAIL = 6).
    """


def orphan_rule_ids(
    baseline_results: dict[str, RuleResult],
    current_results: dict[str, RuleResult],
) -> tuple[str, ...]:
    """rule_ids present in baseline but absent from current.

    Pure set difference, sorted, deduped. The "stale baseline"
    signal — typically caused by an SSG upgrade between capture and
    verify.
    """
```

### Transport

`verify/remote.py` keeps `collect_arfs` unchanged. New tiny helper:

```python
def capture_current_arf(
    *,
    cfg: HostConfig,
    host: str,
    user: str,
    workdir: Path,
    ssh_extra_opts: list[str],
    timeout: int,
) -> str:
    """Run oscap on host, pull the fresh ARF, return its text.

    Implementation is `collect_arfs(no_drift=True)` followed by
    `return arfs.current_text`. Lifted out as a named helper so
    capture-mode call sites read clearly (not "collect_arfs with
    one half thrown away").
    """
```

In practice this MAY just delegate to `collect_arfs(no_drift=True)`
and grab `.current_text` — the helper exists for readability, not
behavioral difference.

### `run_verify` integration

```python
def run_verify(
    *,
    cfg: HostConfig,
    host: str,
    user: str,
    workdir: Path,
    no_drift: bool = False,
    check_tailoring: bool = False,
    baseline_path: Path | None = None,     # ← new
    capture_to: Path | None = None,        # ← new
    ssh_extra_opts: list[str] | None = None,
    timeout: int = 600,
) -> VerifyReport:
```

Mutual exclusion enforced inside `run_verify`:
```python
if baseline_path is not None and capture_to is not None:
    raise ConfigError(
        "--baseline and --capture-baseline are mutually exclusive",
        ExitCode.USAGE,
    )
```
(CLI also rejects at the typer layer for a friendlier error, but the
`run_verify` check is the source-of-truth guard for library callers.)

Branching:
- `capture_to` set: collect arfs as today (current + install for the
  report), write `arfs.current_text` to `capture_to`, build and
  return report with `baseline=None` (the captured baseline drove
  the next run, not this one).
- `baseline_path` set: `read_baseline(baseline_path)` first (fail
  fast on missing/malformed before any SSH), then
  `collect_arfs(no_drift=True)`, then `build_report(install=baseline.results, ...)`.
  Compute orphans, attach `BaselineReport` to the returned report.
- Neither set: byte-identical to v0.9.0.

### Report rendering

`verify/report.py` extensions:

- **`render_table`:** when `report.baseline is not None`, insert one
  line in the header block immediately after the
  `verify host=... user=... at=...` line:
  ```
    baseline: ./baseline.arf.xml (captured 2026-06-05T09:30:00Z)
  ```
  If `captured_utc is None`, the parenthetical is `(timestamp unknown)`.
  When orphans are non-empty, append one line to the bottom of the
  table block (before any drift/suggestions section):
  ```
    NOTE: 7 rule(s) in baseline not present in current ARF — baseline may be stale (SSG upgraded?)
  ```

- **`render_json`:** new top-level `baseline` key when
  `report.baseline is not None`. Absent otherwise (same backward-
  compat shape as `tailoring_drift`):
  ```json
  "baseline": {
    "path": "./baseline.arf.xml",
    "captured_utc": "2026-06-05T09:30:00Z",
    "orphans": [
      "xccdf_org.ssgproject.content_rule_some_removed_rule"
    ]
  }
  ```

### CLI

`verify_cmd` gains two new flags:

```python
capture_baseline: Path | None = typer.Option(
    None, "--capture-baseline",
    help=(
        "Write the freshly-captured ARF to this path on the workstation "
        "(in addition to printing the normal verify report). Use the "
        "captured file later via --baseline. Mutually exclusive with --baseline."
    ),
),
baseline: Path | None = typer.Option(
    None, "--baseline",
    help=(
        "Use this workstation-side ARF as the drift baseline instead of the "
        "host's /root/oscap-remediation-results.xml. Skips the install-ARF "
        "pull. Mutually exclusive with --capture-baseline."
    ),
),
```

CLI-layer mutual-exclusion check raises `Exit(USAGE)` with a clear
message before `run_verify` is called.

### Composition with existing flags

- `--baseline` + `--check-tailoring`: compose freely. Independent
  axes; both report sections may appear.
- `--baseline` + `--no-drift`: redundant but accepted. Internal
  logic always treats `--baseline` as if `no_drift=True` was set
  for transport purposes.
- `--baseline` + `--suggest-exceptions` / `--apply`: compose freely.
  Suggestions are derived from the same report rows; baseline just
  changes which rows get categorized as `new_fail` vs `regression`.
- `--capture-baseline` + `--check-tailoring`: compose freely. Both
  happen during the same SSH session.
- `--capture-baseline` + `--suggest-exceptions` / `--apply`:
  compose freely. The report against the install ARF still drives
  the suggestion list.

## Edge cases

1. **Captured ARF has no `start-time` attribute.** Fallback:
   `captured_utc=None`; report shows `(timestamp unknown)`. Doesn't
   raise. Tested explicitly.

2. **Baseline references rules absent from current ARF.** Footer
   `NOTE:` + JSON `orphans` populated. Reconcile drops them
   silently as today (the iteration loop is over `current`). Test
   pins the orphan count and rule_id list.

3. **Current ARF has rules absent from baseline.** Already-handled
   case today: `categorize(install=None, ...) → new_fail`. No
   change. The "rule new to SSG since baseline was captured" path.

4. **`--capture-baseline` against a host whose oscap reports rule
   failures (oscap exit 2).** `collect_arfs` already tolerates
   exit 2; capture writes the dirty ARF as-is. Dirty state may be
   exactly what the operator wants to freeze. Tested.

5. **`--capture-baseline <path>` where `<path>` already exists.**
   Overwrite. No backup. Documented.

6. **`--capture-baseline <path>` where `<path>` parent dir doesn't
   exist.** `ConfigError(USAGE)` with a message naming the missing
   parent. No `mkdir -p` — operator should know where they're
   writing.

7. **`--baseline <path>` where path is a directory, not a file.**
   `ConfigError(USAGE)` with "not a regular file" message. Same
   class as missing file.

8. **`--baseline` + `--capture-baseline` both set.** CLI rejects
   with `Exit(USAGE=1)` and a message naming both flags. `run_verify`
   also rejects at the library layer (defense in depth).

9. **Baseline ARF identical to current ARF (operator captured 30
   seconds ago, host hasn't changed).** Report is clean,
   `orphans=()`, no surprises.

10. **Baseline ARF that survives parse but has 0
    `<rule-result>` entries.** Treated as a valid (but uninformative)
    baseline — every current rule gets `install=None` →
    `new_fail` on failures. Mirrors today's `--no-drift` behavior.
    Could be argued for as an `ArfMissingError`, but a 0-result
    ARF is technically well-formed and the test workflow
    (operator runs verify, captures from a host with no rules
    selected) is plausible.

## Testing

Following the v0.3/v0.8/v0.9 verify-feature pattern:

- `tests/test_verify_baseline.py` (new) — pure-function tests:
  - `read_baseline` happy path round-trips a fixture ARF.
  - `read_baseline` raises `ConfigError(USAGE)` on missing path.
  - `read_baseline` raises `ArfMissingError` on 0-byte file.
  - `read_baseline` raises `ArfParseError` on garbage XML.
  - `read_baseline` raises `ArfParseError` on XML with no `<TestResult>`.
  - Timestamp extraction: ARF with `start-time` → returned; ARF without → `None`.
  - `orphan_rule_ids`: baseline ⊃ current → returns the difference,
    sorted; baseline ⊆ current → returns `()`; empty inputs → `()`.

- `tests/test_verify_remote.py` — `capture_current_arf` happy path
  (delegates to `collect_arfs(no_drift=True)` and returns
  `current_text`); transport failures propagate.

- `tests/test_verify_run.py` — three new integration tests:
  - `--capture-baseline` (via `capture_to=Path`) writes the file
    AND returns a normal report (install-driven reconcile).
  - `--baseline` (via `baseline_path=Path`) populates the `install`
    slot from the file, doesn't pull install ARF
    (mock `collect_arfs` asserts `no_drift=True`), attaches
    `BaselineReport` to returned `VerifyReport`.
  - Stale baseline: `BaselineReport.orphans` non-empty when
    baseline has rules current doesn't.
  - `baseline_path` + `capture_to` both set raises `ConfigError(USAGE)`.

- `tests/test_verify_report.py` — two new syrupy snapshots at
  `tests/__snapshots__/test_verify_report.ambr`:
  - Table with baseline header line + orphan footer note.
  - JSON with `baseline` block (path + captured_utc + orphans).

- `tests/test_cli/test_verify.py` — five CLI-layer tests:
  - `--capture-baseline ./out.arf` threads through to
    `run_verify(capture_to=...)`, file exists after run, exit 0.
  - `--baseline ./in.arf` threads through to
    `run_verify(baseline_path=...)`, file is read, exit follows
    normal reconcile.
  - `--baseline` + `--capture-baseline` both set → exit 1 (USAGE)
    with mutual-exclusion error message.
  - `--baseline` pointed at nonexistent file → exit 1 (USAGE)
    via `ConfigError`.
  - `--baseline` + `--check-tailoring` compose → both sections
    in report, exit code follows the priority table (compliance
    fail > tailoring drift > clean).

## Documentation

- **MANUAL.md §8.6** (new, peer to v0.9.0's §8.5):
  "Capturing and using a workstation baseline."
  Covers the two scenarios (manual-review and SSG-upgrade), the
  capture flow, the use flow, the stale-baseline warning, the
  file-format note, and the "doesn't replace host.yaml exceptions —
  orthogonal axis" caveat.

- **README.md:** one sentence appended to the verify blurb:
  "Use `--capture-baseline <path>` and `--baseline <path>` to
  reconcile against an operator-captured ARF instead of the
  install-time ARF."

## Acceptance

- `ks-gen verify --capture-baseline ./b.arf --host <addr> --config host.yaml`
  on a reachable host with `oscap` installed: writes `./b.arf`, prints
  a normal verify report, exits per normal reconcile.
- `ks-gen verify --baseline ./b.arf --host <addr> --config host.yaml`:
  skips the install-ARF pull (one fewer ssh round-trip), uses `./b.arf`
  as the drift baseline, prints report with `baseline:` header line and
  orphan footer (when applicable), exits per normal reconcile.
- `--baseline` + `--capture-baseline` together: exit `1` (USAGE).
- `--baseline` pointing at a missing/malformed file: exit `1` (USAGE)
  or `6` (VERIFY_FAIL) respectively, with operator-grokkable messages.
- `verify --format json --baseline ./b.arf` round-trips through a
  JSON parser; `baseline` key carries `path`, `captured_utc`, `orphans`.
- `verify` (no flags) — JSON has no `baseline` key. Backward-compatible.
- ruff + ruff format --check + mypy --strict + pytest -q all green
  on 3.11 / 3.12 / 3.13.
