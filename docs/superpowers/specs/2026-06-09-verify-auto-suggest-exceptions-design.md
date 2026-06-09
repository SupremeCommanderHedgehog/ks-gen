# `ks-gen verify` — auto-suggest exception entries — design

**Issue:** [#14 — ks-gen verify: auto-suggest host.yaml exception entries for failing rules](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/14)

**Status:** draft 2026-06-09

**Goal:** When `ks-gen verify` reports `new_fail` or `regression` rules,
print ready-to-paste `ExceptionDecl` YAML for each, and (opt-in)
append them to `host.yaml` with a backup. Closes the manual
hand-editing friction called out in the issue without erasing the
issue's strict safety invariant: `--apply` must never default, and
regression-category suggestions need a second opt-in to be written.

## Background

`ks-gen verify` (shipped v0.3.0) categorizes each rule as `clean` /
`expected_fail` / `new_fail` / `regression` / `incomplete`. When the
report has `new_fail` or `regression` rows, the operator's three
options are: fix the host, accept the failure as a declared
exception in `host.yaml`, or change the tailoring. The
accept-as-exception path requires hand-editing `host.yaml` with the
right rule id, reason, and category.

The hand-edit step is the friction. It's also the most dangerous
place to add automation: a `verify --apply` that silently writes
regression suggestions would let an operator "verify" their way
into rubber-stamping a real correctness regression as a declared
exception. The issue body calls this footgun out by name as the
non-negotiable safety constraint.

## Goals

- A `--suggest-exceptions` flag on `verify` that renders one
  `ExceptionDecl` per `new_fail` and `regression` row, annotated
  with the originating category, with a `TODO:` reason that carries
  run context (host, date, current/install states).
- A separate `--apply` flag (opt-in, never default) that appends
  the suggestions to `host.yaml` after writing a backup
  (`host.yaml.bak`, single rotating slot) and round-tripping
  through `HostConfig.model_validate()` to refuse to write any
  candidate that wouldn't parse.
- A third `--allow-regression` flag that the apply path requires
  before writing any regression-category suggestion. Render output
  always includes regression suggestions regardless of this flag —
  the operator sees everything; the gate is purely on the write side.
- Idempotent apply: re-running the same `verify --apply` is a no-op
  once the suggestions are present (matched by deterministic id).
- JSON output integration: when `--suggest-exceptions` is set,
  `render_json` includes a new `suggested_exceptions` array.
  Otherwise the JSON shape is unchanged (backward-compatible).
- All write paths preserve the invariant that the original
  `host.yaml` is either fully replaced or untouched.

## Non-goals (deferred)

- Comment / formatting preservation in `host.yaml`. PyYAML's
  `safe_dump` roundtrip loses comments, quoting style choices, and
  block/flow style. The `.bak` is the recovery path. Operators who
  want comments preserved should hand-paste the rendered
  suggestions instead. Adding `ruamel.yaml` as a runtime dep just
  for this is too heavy for a p3 feature.
- Interactive confirm-before-write. The operator opted in via two
  explicit flags (`--apply`, plus `--allow-regression` for
  regressions); the backup is the safety net.
- Auto-resolution of exceptions. `verify` doesn't try to remove
  exceptions for rules that newly pass — the operator's "expected
  failure" list is intentional and may be deliberately broader than
  the currently-failing set. Stale-exception pruning could be a
  follow-up p3.
- Multi-host / batch mode. One verify run → one host.yaml.
  Operators with fleets re-invoke per host.
- `host.yaml` not version-controlled. We assume git or equivalent.
  The `.bak` is a single rotating slot, not a history.
- `incomplete`-category suggestions. `incomplete` rules (oscap
  errored / notchecked / unknown) aren't failures; they're
  diagnostic gaps. The operator can't usefully declare an exception
  for "we couldn't tell".

## Architecture

New module `src/ks_gen/verify/suggest.py`, mirroring the verify
package's existing small-files pattern (each existing file is
~80–120 lines, one responsibility).

```
src/ks_gen/verify/
├── suggest.py        # NEW: build_suggestions + render_yaml + apply_to_host_yaml
├── arf.py            # unchanged
├── errors.py         # adds SuggestApplyError
├── reconcile.py      # unchanged
├── remote.py         # unchanged
├── report.py         # render_table / render_json gain `suggestions=` param
├── run.py            # unchanged
├── ssh.py            # unchanged
└── __init__.py       # re-exports unchanged
```

### Types

```python
# verify/suggest.py

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from ks_gen.config import ExceptionDecl
from ks_gen.verify.reconcile import VerifyReport, Category


@dataclass(frozen=True)
class Suggestion:
    decl: ExceptionDecl
    category: Category  # "new_fail" or "regression"


@dataclass(frozen=True)
class AppendResult:
    added: tuple[str, ...]               # decl ids written this call
    skipped_existing: tuple[str, ...]    # decl ids already present in host.yaml
    skipped_regression: tuple[str, ...]  # regression decl ids gated out without --allow-regression
    path: Path                           # the host.yaml that was written
    backup_path: Path                    # host.yaml.bak

# All three id-tuples are symmetric. Full ExceptionDecl content is
# already available via the `suggestions` list passed in — the CLI
# summary only needs the ids.


def build_suggestions(report: VerifyReport) -> list[Suggestion]:
    """Pure. One Suggestion per new_fail + regression row in `report.rows`.
    Stable order matches report row order (already sorted by rule_id)."""


def render_yaml(suggestions: list[Suggestion], report: VerifyReport) -> str:
    """Pure. The paste-friendly YAML block including the
    '## Suggested exception entries' header and per-Suggestion
    YAML rendered by yaml.safe_dump. Empty string if suggestions=[]."""


def apply_to_host_yaml(
    *,
    suggestions: list[Suggestion],
    host_yaml_path: Path,
    allow_regression: bool,
) -> AppendResult:
    """Idempotent append-only. Writes <path>.bak, validates the
    candidate via HostConfig.model_validate(), and only then atomically
    replaces host.yaml. Raises SuggestApplyError on read/parse/validate
    failure with host.yaml untouched."""
```

### `Suggestion`-building rules

- `id` = `f"auto-{row.category}-{row.rule_id}"` — deterministic,
  search-grep-friendly, and stable across runs (so re-applying the
  same suggestion is a no-op).
- `reason` = `f"TODO: explain why — auto-suggested {date} from
  {host} (current={cur}, install={inst}, category={category})"`.
  The `TODO:` prefix lets operators `grep TODO host.yaml` for
  unreviewed entries.
- `stig_rules_disabled` = `[row.rule_id]` — one rule per
  `ExceptionDecl` (matches the choice to render one block per
  failing rule rather than batched).

## CLI shape & flag semantics

Three new flags on `verify_cmd` in `cli.py`:

```
--suggest-exceptions   # render ExceptionDecl YAML for new_fail + regression rows
--apply                # write to host.yaml (implies --suggest-exceptions)
--allow-regression     # let --apply write regression-category suggestions too
```

**Implication graph:**

- `--apply` without `--suggest-exceptions` is treated as if both
  were passed. You can't apply without first suggesting.
- `--allow-regression` only changes what `--apply` *writes*.
  Rendering always shows both `new_fail` and `regression` rows,
  annotated with their category.
- `--allow-regression` without `--apply` emits one stderr line
  (`"--allow-regression has no effect without --apply"`) and is
  otherwise a no-op.

**Filtering matrix:**

| Category        | Suggestion rendered? | Written by `--apply`? |
| --------------- | -------------------- | --------------------- |
| `clean`         | no                   | no                    |
| `expected_fail` | no                   | no                    |
| `incomplete`    | no                   | no                    |
| `new_fail`      | yes                  | yes                   |
| `regression`    | yes                  | yes, with `--allow-regression` |

**Exit codes:** unchanged. `VERIFY_FAIL=6` still fires when the
report has `new_fail` / `regression` rows even after a successful
`--apply` — the report reflects the host *at the time of the run*;
an apply doesn't retroactively make the host clean.

## Render format

### Text (`--format table`)

After the existing report table, append:

```
## Suggested exception entries — copy into host.yaml's `exceptions:` list
## verify host=web01.example.com user=opsadmin at=2026-06-09T01:30:00Z (3 suggestions)

- id: auto-new_fail-xccdf_org.ssgproject.content_rule_sysctl_kernel_dmesg_restrict
  reason: 'TODO: explain why — auto-suggested 2026-06-09 from web01.example.com (current=fail, install=fail, category=new_fail)'
  stig_rules_disabled:
    - xccdf_org.ssgproject.content_rule_sysctl_kernel_dmesg_restrict

- id: auto-regression-xccdf_org.ssgproject.content_rule_package_telnet-server_removed
  reason: 'TODO: explain why — auto-suggested 2026-06-09 from web01.example.com (current=fail, install=pass, category=regression)'
  stig_rules_disabled:
    - xccdf_org.ssgproject.content_rule_package_telnet-server_removed
```

- Generated via `yaml.safe_dump([decl.model_dump() for decl in
  decls], sort_keys=False, default_flow_style=False)`. The
  `model_dump()` order matches the schema definition (id → reason
  → stig_rules_disabled), which is the order operators expect.
- A blank line separates each suggestion for paste-readability.
- Header comments use `##` (two hashes) so they survive a copy-paste
  into a YAML file as comments rather than being mistaken for keys.
- If `len(suggestions) == 0`, the entire block (including header)
  is omitted. Clean reports get clean output.

### JSON (`--format json`)

When `--suggest-exceptions` is set, the existing JSON payload gains
one top-level key:

```json
{
  "host": "web01.example.com",
  ...,
  "rows": [...],
  "suggested_exceptions": [
    {
      "category": "new_fail",
      "decl": {
        "id": "auto-new_fail-xccdf_...dmesg_restrict",
        "reason": "TODO: explain why — auto-suggested 2026-06-09 from web01.example.com (current=fail, install=fail, category=new_fail)",
        "stig_rules_disabled": ["xccdf_...dmesg_restrict"]
      }
    }
  ]
}
```

`suggested_exceptions` is present (possibly empty) when the flag
is set, and omitted entirely when it isn't — preserving the
JSON shape for existing consumers.

### Plumbing

`render_table` and `render_json` in `report.py` gain an optional
`suggestions: list[Suggestion] | None = None` parameter. When
`None`, behavior is unchanged. The CLI decides whether to compute
suggestions and pass them through.

## Apply path

`apply_to_host_yaml` steps:

1. **Filter by allow_regression**:
   `to_consider = [s for s in suggestions if s.category != "regression" or allow_regression]`.
   Dropped → `skipped_regression`.

2. **Read & parse host.yaml**:
   `raw = host_yaml_path.read_text("utf-8"); data = yaml.safe_load(raw) or {}`.
   If `data` isn't a dict → `SuggestApplyError("host.yaml is not a YAML mapping; refusing to modify")`.

3. **Compute existing ids**:
   `existing = {entry["id"] for entry in data.get("exceptions", []) if isinstance(entry, dict) and "id" in entry}`.

4. **Filter idempotent**:
   `to_apply = [s for s in to_consider if s.decl.id not in existing]`. Dropped → `skipped_existing`.

5. **Build candidate** (in-memory append):
   `candidate = {**data, "exceptions": data.get("exceptions", []) + [s.decl.model_dump() for s in to_apply]}`.

6. **Validate candidate via pydantic** before writing:
   `HostConfig.model_validate(candidate)`. If this raises, wrap as
   `SuggestApplyError("applied host.yaml would fail validation:
   <e>; original untouched")` and refuse to write. No `.bak` is
   created. Order matters: pydantic-check → backup → atomic write.

7. **Backup**:
   `backup_path = host_yaml_path.with_suffix(host_yaml_path.suffix + ".bak")`
   (i.e., `host.yaml` → `host.yaml.bak`).
   `shutil.copy2(host_yaml_path, backup_path)` — overwrites any
   prior `.bak` (single rotating slot).

8. **Atomic write**:
   `tmp = host_yaml_path.with_suffix(host_yaml_path.suffix + ".tmp")`.
   `tmp.write_text(yaml.safe_dump(candidate, sort_keys=False,
   default_flow_style=False), encoding="utf-8", newline="\n")`.
   `tmp.replace(host_yaml_path)` — atomic on POSIX, near-atomic on
   Windows (`Path.replace` is the right primitive on both).

9. **Return** `AppendResult(added=tuple(s.decl.id for s in to_apply),
   skipped_existing=tuple(...), skipped_regression=tuple(...),
   path=host_yaml_path, backup_path=backup_path)`.

### Invariant

Either the apply fully succeeds and `host.yaml` reflects the new
state, or `host.yaml` is byte-identical to before the call. There
is no intermediate window in which both files exist with stale
content (atomic replace + validate-before-write).

## Errors & edge cases

New exception type in `verify/errors.py`:

```python
class SuggestApplyError(VerifyError):
    exit_code = ExitCode.CONFIG_INVALID  # 2 — bad host.yaml content,
                                         # not a CLI invocation problem
```

Sub-cases the CLI surfaces with `"ks-gen verify: apply failed: <e>"`:

- **host.yaml not a mapping** — "host.yaml is not a YAML mapping (got `<type>`); refusing to modify."
- **yaml.YAMLError on read** — "host.yaml is not valid YAML: `<reason>`; refusing to modify."
- **pydantic ValidationError on candidate** — "applied host.yaml would fail validation: `<error path>`; original file untouched."
- **OSError on backup or rename** — re-raise the OSError directly; the CLI catches and prints `"ks-gen verify: apply failed: <e>"`. No `.bak` retained if the failure was before backup; if after, `.bak` survives.

### Edge cases

- **No failing rows** (`report.is_clean`) — `--suggest-exceptions`
  prints only the report (suggestions block omitted). `--apply` is
  a no-op with empty `AppendResult`; CLI prints `"nothing to apply"`.
- **All suggestions already present** — no `.bak`, no `.tmp`, no
  write. CLI: `"all N suggestions already present in host.yaml;
  nothing to apply"`.
- **`exceptions:` key absent in host.yaml** — `data.get("exceptions",
  [])` defaults; candidate adds the key.
- **`host.yaml.bak` exists** — overwritten silently (single
  rotating slot).
- **`--apply` without `--suggest-exceptions`** — implicit. No error.
- **`--allow-regression` without `--apply`** — stderr note;
  otherwise no-op.

## Testing strategy

New file `tests/test_verify_suggest.py` (mirrors the
`tests/test_verify_*.py` pattern):

1. **Pure-function tests** — `build_suggestions` filters correctly
   (clean / expected_fail / incomplete excluded; new_fail +
   regression included), id format matches `auto-<category>-<rule_id>`,
   reason contains `TODO:` + run context (host, date,
   current/install).
2. **Golden-snapshot test** — `render_yaml` output via syrupy
   `.ambr`, fixture `VerifyReport` containing one of each category.
   Pins the formatting (header style, quote style, blank-line
   separation).
3. **`apply_to_host_yaml` table-tests** (using `tmp_path`):
   - Empty `exceptions:` list → appends suggestions, returns `added`.
   - Existing entries preserved, new ones appended.
   - Idempotent: second call with same suggestions → `skipped_existing`
     populated, file mtime unchanged.
   - `allow_regression=False` filters regression suggestions into
     `skipped_regression`.
   - `allow_regression=True` lets them through.
   - `host.yaml.bak` is created and matches the pre-apply content
     byte-for-byte.
   - Malformed host.yaml (not a mapping) → raises
     `SuggestApplyError`, file untouched, no `.bak`.
   - Schema violation in candidate → raises `SuggestApplyError`,
     file untouched.
   - `host.yaml.bak` already exists → overwritten cleanly.
4. **CLI integration tests** via `CliRunner` — `verify_cmd` with
   each flag combination produces expected stdout/stderr/exit-code.
   `monkeypatch` on `run_verify` to inject canned `VerifyReport`s
   (existing test pattern in `tests/test_cli/`).

## Docs to update in the same PR

- `MANUAL.md` §8.5 — add a subsection covering the three new flags
  with one worked example showing the rendered YAML block, the
  `host.yaml.bak` rotation behavior, and the PyYAML
  formatting-loss caveat. Cross-reference the `--allow-regression`
  safety story.
- No `README.md` update needed — verify enhancements live below the
  README's quickstart abstraction.
- `CHANGELOG.md` — release-please generates from conventional
  commits; no manual edit.

## Acceptance criteria

1. `verify --suggest-exceptions` with a `new_fail` + `regression`
   report prints the report followed by a YAML block containing one
   `ExceptionDecl` per failing rule, formatted per the spec.
2. `verify --suggest-exceptions --format json` returns the existing
   payload plus a `suggested_exceptions` array; when the flag is
   absent, the array is absent and JSON shape is unchanged.
3. `verify --apply` writes only `new_fail` suggestions to
   `host.yaml`, after creating `host.yaml.bak`, after validating the
   candidate through `HostConfig.model_validate()`, and never if any
   step would fail.
4. `verify --apply --allow-regression` additionally writes
   regression suggestions.
5. Re-running `verify --apply` against an unchanged host produces
   `AppendResult` with no `added`, all-skipped entries, and no file
   mutation (mtime unchanged).
6. Pydantic-rejected candidates leave `host.yaml` byte-identical
   to its pre-call state, and no `.bak` is created.
7. `tests/test_verify_suggest.py` covers each documented edge case
   with at least one positive and one negative test.
8. CI green on 3.11 / 3.12 / 3.13. Local CI parity chain (ruff +
   ruff format --check + mypy + pytest) clean before commit.
