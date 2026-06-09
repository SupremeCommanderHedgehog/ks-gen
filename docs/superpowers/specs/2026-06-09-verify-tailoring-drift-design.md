# `ks-gen verify` — tailoring drift detection — design

**Issue:** [#12 — ks-gen verify: detect tailoring drift (workstation host.yaml vs. /root/tailoring.xml)](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/12)

**Status:** draft 2026-06-09

**Goal:** When `ks-gen verify` runs against a host whose deployed
`/root/tailoring.xml` no longer matches what the operator's current
`host.yaml` would render, surface that mismatch as a per-op diff.
Compliance against a stale tailoring is silently "clean" today; this
gives the operator a signal that their workstation intent and the
host's actual configuration have diverged.

## Background

`ks-gen verify` (shipped v0.3.0) re-runs oscap on a deployed host
using the install-time `/root/tailoring.xml` and reconciles failures
against the workstation `host.yaml` exception set. The reconcile is
authoritative for compliance, but it doesn't notice when the
workstation `host.yaml` itself has changed since the install — only
the deployed tailoring is consulted on the host side.

The user-visible failure mode the issue documents: an operator edits
`host.yaml` (adds an exception, flips a rule, changes a value),
runs `verify`, sees a clean report, and assumes the edit took effect.
It didn't — the edit lives on the workstation; the host is still
running against the tailoring written at install time.

`/root/tailoring.xml` is present on every ks-gen-provisioned host
(written by the `%post --nochroot` fetch stage, per the v0.2.0 hd:LABEL
transport architecture) and is what `oscap xccdf eval --tailoring-file`
consults during verify. It's the single source of truth on the host
side for what STIG profile the host is being measured against.

## Goals

- A `--check-tailoring` flag on `verify` that scp-pulls the host's
  `/root/tailoring.xml`, re-renders the expected tailoring locally
  from the workstation `host.yaml`, and reports a per-op diff (added,
  removed, changed `<select>` / `<set-value>` ops, plus profile-id
  mismatch as a header-level drift line).
- Distinct exit code `TAILORING_DRIFT = 8` so CI / automation can
  gate on "host's tailoring is stale" independently from "host is
  non-compliant" (`VERIFY_FAIL = 6`).
- Comparison is semantic, not byte-level. `build_tailoring_xml`
  embeds `datetime.now(UTC)` in `<xccdf:version time="...">`, so a
  byte-hash would always disagree; both sides are parsed into a
  sorted list of `(action, rule_id, value)` triples reusing the
  existing `TailoringOp` dataclass.
- JSON output integration: when `--check-tailoring` is set,
  `render_json` includes a new `tailoring_drift` key. When not set,
  the key is absent (backward-compatible).
- All transport, parse, and re-render failures map to existing or
  one new verify error class; no silent failure paths.

## Non-goals (deferred)

- **Default-on detection.** Brainstorming explicitly settled on
  opt-in. The cost (one extra scp_pull per verify run) doesn't
  justify default-on for a p3 ergonomic feature; operators who want
  the signal opt in.
- **Auto-regenerate + redeploy.** The fix path stays the operator's:
  `ks-gen gen <host.yaml>` + their own deploy method (re-burn ISO,
  rebuild + ship, etc.). Out of scope for verify.
- **ks.cfg-level drift.** Kickstart drift is a different problem
  (ks.cfg isn't persisted on the host post-install; the `%post`
  blocks ran once and are gone). Tracking only the tailoring is the
  scoped follow-up the issue asks for.
- **Local-mode drift detection.** Comparing against a local
  pre-staged tailoring file with no SSH involved is part of #13
  (on-host self-check / `--local` mode), not this issue.
- **Drift across multiple hosts in one invocation.** Batch / fleet
  scope belongs to #10. One verify run, one host.
- **Tolerating cosmetic differences** (whitespace, attribute order)
  beyond what stdlib ElementTree normalizes for free. The renderer
  is deterministic; any string-equality drift is meaningful drift —
  including a hand-edit of `/root/tailoring.xml`, which we want to
  flag.
- **Auto-resolving the drift.** Verify reports it. Operator decides
  whether their edit was intentional and runs `ks-gen gen`
  themselves.

## Architecture

New module `src/ks_gen/verify/tailoring_drift.py` with the pure
parse/compare/render functions. One new transport function in
`verify/remote.py`. One new optional field on `VerifyReport`. One
new param on `run_verify`. One new CLI flag.

### Data model

```python
# verify/tailoring_drift.py

@dataclass(frozen=True)
class ParsedTailoring:
    profile_id: str
    ops: list[TailoringOp]   # reused from ks_gen.rules._types

@dataclass(frozen=True)
class OpChange:
    rule_id: str
    action: str            # always "set_value" — only set_value carries a value
    expected_value: str
    deployed_value: str

@dataclass(frozen=True)
class TailoringDriftReport:
    profile_id_expected: str
    profile_id_deployed: str
    added: list[TailoringOp]    # expected has it, deployed doesn't
    removed: list[TailoringOp]  # deployed has it, expected doesn't
    changed: list[OpChange]     # both sides have (action, rule_id); value differs
```

`VerifyReport` (in `verify/reconcile.py`) gains:

```python
tailoring_drift: TailoringDriftReport | None = None

@property
def has_tailoring_drift(self) -> bool:
    """True iff a drift check ran AND found at least one delta."""
    d = self.tailoring_drift
    if d is None:
        return False
    return bool(d.added or d.removed or d.changed) or (
        d.profile_id_expected != d.profile_id_deployed
    )
```

`None` means the check didn't run (default). An empty
`TailoringDriftReport` with matching profile_ids means the check ran
and found no drift — surfaced in JSON but not in the text table.

### Functions

```python
# verify/tailoring_drift.py

def parse_tailoring_xml(text: str) -> ParsedTailoring:
    """Parse a tailoring.xml into profile_id + ordered TailoringOp list.

    Uses stdlib xml.etree.ElementTree with local-name matching (same
    pattern as verify/arf.py). Recognizes <xccdf:select selected="true"/>
    → action="select", selected="false"/> → action="disable",
    <xccdf:set-value> → action="set_value".

    Raises:
        TailoringParseError: malformed XML or no <Profile> element.
    """

def compare_tailorings(
    expected: ParsedTailoring,
    deployed: ParsedTailoring,
) -> TailoringDriftReport:
    """Pure diff. Sorts ops by rule_id before bucketing.

    An op is keyed by (action, rule_id). Same key on both sides with
    different value → OpChange (only meaningful for set_value).
    Key on expected only → added. Key on deployed only → removed.
    """

def render_drift_section(report: TailoringDriftReport) -> str:
    """Human-readable section for the verify text report.

    Empty string when there is no drift to render — caller doesn't
    have to gate on has_tailoring_drift.
    """
```

### Re-render helper

Extract `render_tailoring(cfg: HostConfig) -> str` from
`writer.build_bundle`. Pure function, three lines: load rules,
topo-sort + filter applicable, collect ops, call
`build_tailoring_xml`. `build_bundle` calls into it; verify also
calls into it. No behavior change to the existing render path —
both render paths produce byte-identical output for the same `cfg`
(modulo the embedded timestamp).

### Transport

New function in `verify/remote.py`:

```python
REMOTE_TAILORING = "/root/tailoring.xml"  # already defined

def collect_deployed_tailoring(
    *,
    host: str,
    user: str,
    workdir: Path,
    ssh_extra_opts: list[str],
) -> str:
    """scp-pull /root/tailoring.xml. Sibling to collect_arfs.

    Raises:
        OscapInvocationError: /root/tailoring.xml missing or unreadable
            (host not provisioned by ks-gen, or sudo perms wrong).
        SshConnectError: ssh/scp transport failure.
    """
```

Separate from `collect_arfs` rather than a parameter on it: the
`--no-drift` / `--check-tailoring` axes are independent, and
verifying composability is easier when the transport calls don't
share state.

### `run_verify` integration

```python
def run_verify(
    *,
    cfg: HostConfig,
    host: str,
    user: str,
    workdir: Path,
    no_drift: bool = False,
    check_tailoring: bool = False,        # ← new
    ssh_extra_opts: list[str] | None = None,
    timeout: int = 600,
) -> VerifyReport:
```

When `check_tailoring=True`:
1. `deployed_xml = collect_deployed_tailoring(...)` (before the
   compliance run — fails fast if the file is missing).
2. `expected_xml = render_tailoring(cfg)`.
3. `parsed_expected = parse_tailoring_xml(expected_xml)`,
   `parsed_deployed = parse_tailoring_xml(deployed_xml)`.
4. `tailoring_drift = compare_tailorings(parsed_expected, parsed_deployed)`.
5. Compliance run proceeds as today; `tailoring_drift` is attached to
   the returned `VerifyReport`.

When `False` (default): no transport, no parse, no re-render.
`tailoring_drift` stays `None`. Byte-identical behavior to v0.8.0.

### Report rendering

`verify/report.py`:

- `render_table`: when `report.has_tailoring_drift`, append a section
  below the existing compliance table (one blank line separator):

  ```
  Tailoring drift detected — workstation host.yaml differs from /root/tailoring.xml.
  Re-run `ks-gen gen <host.yaml>` and redeploy to align.

    + disable xccdf_org.ssgproject.content_rule_grub2_audit_argument
    - disable xccdf_org.ssgproject.content_rule_package_telnet_removed
    ~ xccdf_org.ssgproject.content_value_var_password_pam_unix_remember: 5 → 24
    (profile changed: stig_gui → stig)
  ```

  Glyph legend: `+` added (expected only), `-` removed (deployed only),
  `~` changed (set-value delta). The `(profile changed: ...)` line
  appears only when profile_ids differ.

- `render_json`: adds top-level key `tailoring_drift`. When the check
  didn't run: `null`. When it ran:
  ```json
  {
    "tailoring_drift": {
      "profile_id_expected": "...",
      "profile_id_deployed": "...",
      "added":   [{"action": "disable", "rule_id": "...", "value": null}, ...],
      "removed": [...],
      "changed": [{"rule_id": "...", "action": "set_value",
                   "expected_value": "...", "deployed_value": "..."}, ...]
    }
  }
  ```

### CLI

`ks-gen verify` gains `--check-tailoring` (store_true, default
False). Threads through to `run_verify(check_tailoring=...)`.

### Exit code

New `ExitCode.TAILORING_DRIFT = 8`. The CLI's verify command
computes the exit in this priority order (most-severe first):

| Priority | Condition                          | Exit |
| -------- | ---------------------------------- | ---- |
| 1        | `SshConnectError` / `ToolMissingError` raised | 7 / 5 |
| 2        | `ConfigError` / `SuggestApplyError` raised    | 2    |
| 3        | `report.is_clean` is False                    | 6    |
| 4        | `report.has_tailoring_drift` is True          | 8    |
| 5        | otherwise                                     | 0    |

Tailoring drift is the weakest non-zero signal — a host can be
compliant against a stale tailoring, and the drift report itself is
about workstation/host divergence rather than security state.

### Errors

New `TailoringParseError(VerifyError)` with
`exit_code = VERIFY_FAIL`. Raised by `parse_tailoring_xml` on
malformed XML or missing `<Profile>` element. Message names the side
(`"failed to parse deployed tailoring at /root/tailoring.xml"` vs
`"failed to parse re-rendered tailoring (ks-gen renderer bug?)"`) so
the operator knows where to look.

Transport failures reuse `SshConnectError` from
`verify/remote.py`. Missing `/root/tailoring.xml` reuses
`OscapInvocationError` with new message text.

## Edge cases

1. **Host not provisioned by ks-gen** — `/root/tailoring.xml`
   absent. `OscapInvocationError("install-time tailoring not present
   at /root/tailoring.xml — host may not have been provisioned by
   ks-gen")`. Exit 6 (VERIFY_FAIL).

2. **Malformed deployed XML** — `TailoringParseError`. Message names
   deployed side. Exit 6.

3. **Malformed re-rendered XML** — should never happen; would
   indicate a ks-gen renderer regression. Same exit but message
   names the renderer. Implies a bug worth filing.

4. **Profile-id mismatch only, ops identical** — `(profile changed:
   X → Y)` line, no `+`/`-`/`~` rows, `has_tailoring_drift = True`,
   exit 8.

5. **Op present in deployed but action unknown to parser** — e.g.,
   if a future ks-gen adds a new op type. Treated as `removed`
   (deployed has it, expected doesn't). Operator sees the drift; the
   ks-gen renderer side is the source of truth for what's supported.

6. **set-value with literal value `""`** — the renderer emits
   `<xccdf:set-value idref="...">` (empty body). Parser produces
   `value=""`. Two empty-string values compare equal; one empty and
   one populated compares as `changed`. Tested explicitly.

7. **Empty diff** — `tailoring_drift` is attached, all three lists
   empty, profile_ids match. `has_tailoring_drift` returns False.
   Table renderer produces nothing. JSON renderer emits the
   populated (but empty-list-bearing) object so consumers know the
   check ran.

8. **`check_tailoring=True` with `no_drift=True`** — independent
   axes. `no_drift` skips the install-time-ARF compliance baseline.
   `check_tailoring` adds the tailoring pull. Both can be set; the
   report carries both kinds of "drift" (install-vs-current
   compliance drift and intent-vs-deployed tailoring drift) at
   once. The terminology overlap is unfortunate but already locked
   in by v0.3.0.

9. **Hand-edited `/root/tailoring.xml`** — appears as drift the same
   way a workstation edit does. The verify report can't distinguish
   "operator edited host.yaml" from "operator edited the deployed
   file"; it just reports the delta. Both are equally interesting
   to know about.

## Testing

Following the v0.3.0 / v0.8.0 verify-feature pattern:

- `tests/test_tailoring_drift.py` (new) — unit tests for pure
  functions:
  - `parse_tailoring_xml`: round-trip a `build_tailoring_xml`
    output and confirm the parsed op list equals the input ops.
  - `parse_tailoring_xml`: raises `TailoringParseError` on garbage
    XML, on XML without `<Profile>`.
  - `compare_tailorings`: clean-no-drift, added-only, removed-only,
    changed-only, profile-id-only, all four simultaneously, unknown
    action in deployed (treated as removed), empty set-value vs
    populated.
  - `render_drift_section`: empty-drift returns empty string;
    non-empty matches the expected layout (glyph legend, profile
    line appears only when ids differ).

- `tests/test_verify_report.py` — syrupy snapshots at
  `tests/__snapshots__/test_verify_report.ambr`. Two new snapshots:
  (a) full table with drift section appended, (b) JSON with
  `tailoring_drift` populated. Mirrors the v0.8.0
  `suggestions=`-shaped extension.

- `tests/test_remote.py` — `collect_deployed_tailoring` raises
  `OscapInvocationError` when the file probe fails;
  `SshConnectError` propagates on scp failure.

- `tests/test_verify.py` (or integration-layer equivalent) — stub
  SSH layer:
  - `check_tailoring=True` + matching tailorings →
    `tailoring_drift` populated, `has_tailoring_drift` is False.
  - `check_tailoring=True` + diverged tailorings →
    `has_tailoring_drift` is True.
  - `check_tailoring=False` → `tailoring_drift is None`,
    no transport call made.

- `tests/test_cli.py` — `--check-tailoring` flag parses, defaults
  to False. Exit-code priority: drift alone → 8; compliance fail +
  drift → 6 (compliance wins); transport fail + drift → 7.

## Documentation

MANUAL.md gains a new §8.5 subsection ("Detecting tailoring
drift") peer to the v0.8.0 `--suggest-exceptions` subsection.
Cover:
- The use case (operator edits `host.yaml` post-install).
- The flag (`--check-tailoring`).
- The new exit code (8) and that drift alone does not mean the
  host is non-compliant.
- A sample diff output.
- The fix path (`ks-gen gen <host.yaml>` + redeploy).

README's `verify` blurb gets one extra sentence pointing at the
flag.

`exceptions.md` is not touched — tailoring drift isn't an
exception, it's a workstation/host divergence.

## Acceptance

- `ks-gen verify --check-tailoring --host <addr> --config host.yaml`
  on a host whose `/root/tailoring.xml` matches the workstation
  `host.yaml`: report shows no drift section, exit 0 (or 6 if
  compliance fails).
- Same invocation on a host whose deployed tailoring is stale:
  report shows the per-op diff section, exit 8 (or 6 if compliance
  also fails — compliance wins).
- `ks-gen verify` (no flag) on a drifted host: report shows nothing
  about drift, JSON has no `tailoring_drift` key. Backward-compatible.
- `--json` output round-trips through a JSON parser and the
  `tailoring_drift` field carries `null` (check not run) or the full
  object (check ran).
- ruff + ruff format --check + mypy --strict + pytest -q all green
  on 3.11 / 3.12 / 3.13.
