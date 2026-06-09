# Verify auto-suggest exceptions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--suggest-exceptions` / `--apply` / `--allow-regression` flags to `ks-gen verify` that render and (opt-in) write `ExceptionDecl` YAML for failing rules. Closes #14; ships the design at `docs/superpowers/specs/2026-06-09-verify-auto-suggest-exceptions-design.md`.

**Architecture:** New `src/ks_gen/verify/suggest.py` module with three pure-ish units: `build_suggestions` (filter report rows), `render_yaml` (paste-friendly output), `apply_to_host_yaml` (idempotent append-only with backup + pydantic round-trip validation). `report.py` gains a `suggestions=` parameter on both renderers; `cli.py` wires the three new flags. Schema-rejected candidates leave `host.yaml` byte-identical to its pre-call state.

**Tech Stack:** Python 3.11+, pydantic 2.x, typer, PyYAML (no new dep), pytest + syrupy + monkeypatch + tmp_path for testing. CI parity: `ruff check && ruff format --check && mypy && pytest -q`.

**Branch:** `impl/v0.8.0-verify-suggest-exceptions` (already created; spec at commit `37bf017`).

---

## Pre-flight

- [ ] Verify branch state:

```bash
git branch --show-current
# expected: impl/v0.8.0-verify-suggest-exceptions
git log -1 --format="%h %s"
# expected: 37bf017 docs(specs): verify auto-suggest exceptions design (#14)
git status --short
# expected: only .claude/ and .scratch/ untracked
```

- [ ] Confirm CI parity baseline is green:

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
# expected: all green, 422 passed (the v0.7.0 baseline)
```

---

### Task 1: Add `SuggestApplyError` to `verify/errors.py`

**Files:**
- Modify: `src/ks_gen/verify/errors.py` (append one class at end)

- [ ] **Step 1: Append `SuggestApplyError` to `src/ks_gen/verify/errors.py`**

Add at the end of the file:

```python
class SuggestApplyError(VerifyError):
    """Apply-side failure: malformed host.yaml, schema-rejecting candidate,
    or write/backup IO error. Exit code is CONFIG_INVALID (2) because the
    operator's config file content (not CLI invocation) is what needs fixing."""

    exit_code: ExitCode = ExitCode.CONFIG_INVALID
```

- [ ] **Step 2: Smoke-import the new class**

```bash
python -c "from ks_gen.verify.errors import SuggestApplyError; print(SuggestApplyError.exit_code)"
# expected: ExitCode.CONFIG_INVALID
```

- [ ] **Step 3: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 422 passed.

- [ ] **Step 4: Commit**

```bash
git add src/ks_gen/verify/errors.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(verify): add SuggestApplyError(VerifyError) with CONFIG_INVALID exit code"
```

---

### Task 2: `build_suggestions` in `verify/suggest.py`

Pure function — filters `VerifyReport.rows` to the rule rows that should produce suggestions and constructs `ExceptionDecl`s.

**Files:**
- Create: `src/ks_gen/verify/suggest.py`
- Create: `tests/test_verify_suggest.py`

- [ ] **Step 1: Write failing tests for `build_suggestions`**

Create `tests/test_verify_suggest.py`:

```python
from __future__ import annotations

from ks_gen.verify.reconcile import VerifyReport, VerifyRow
from ks_gen.verify.suggest import Suggestion, build_suggestions


def _report(*rows: VerifyRow, host: str = "h1") -> VerifyReport:
    return VerifyReport(
        host=host,
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=tuple(rows),
        install_baseline_available=True,
    )


def test_build_suggestions_filters_to_new_fail_and_regression():
    report = _report(
        VerifyRow("rule_a", "pass", "pass", False, "clean"),
        VerifyRow("rule_b", "fail", "fail", True, "expected_fail"),
        VerifyRow("rule_c", "error", None, False, "incomplete"),
        VerifyRow("rule_d", "fail", "fail", False, "new_fail"),
        VerifyRow("rule_e", "fail", "pass", False, "regression"),
    )
    out = build_suggestions(report)
    # only rule_d (new_fail) and rule_e (regression) become suggestions
    assert [s.decl.stig_rules_disabled[0] for s in out] == ["rule_d", "rule_e"]
    assert [s.category for s in out] == ["new_fail", "regression"]


def test_build_suggestions_id_format():
    report = _report(
        VerifyRow("rule_d", "fail", "fail", False, "new_fail"),
        VerifyRow("rule_e", "fail", "pass", False, "regression"),
    )
    out = build_suggestions(report)
    assert out[0].decl.id == "auto-new_fail-rule_d"
    assert out[1].decl.id == "auto-regression-rule_e"


def test_build_suggestions_reason_carries_run_context():
    report = _report(
        VerifyRow("rule_d", "fail", "pass", False, "regression"),
        host="web01.example.com",
    )
    suggestion = build_suggestions(report)[0]
    reason = suggestion.decl.reason
    assert reason.startswith("TODO:")
    assert "web01.example.com" in reason
    assert "2026-06-09" in reason
    assert "current=fail" in reason
    assert "install=pass" in reason
    assert "category=regression" in reason


def test_build_suggestions_stig_rules_disabled_is_single_id():
    report = _report(VerifyRow("rule_d", "fail", "fail", False, "new_fail"))
    suggestion = build_suggestions(report)[0]
    assert suggestion.decl.stig_rules_disabled == ["rule_d"]


def test_build_suggestions_empty_report_returns_empty_list():
    report = _report(VerifyRow("rule_a", "pass", "pass", False, "clean"))
    assert build_suggestions(report) == []


def test_build_suggestions_order_matches_report_row_order():
    # build_report sorts by rule_id; build_suggestions preserves that order
    report = _report(
        VerifyRow("rule_a", "fail", "fail", False, "new_fail"),
        VerifyRow("rule_b", "fail", "pass", False, "regression"),
        VerifyRow("rule_c", "fail", "fail", False, "new_fail"),
    )
    out = build_suggestions(report)
    assert [s.decl.stig_rules_disabled[0] for s in out] == ["rule_a", "rule_b", "rule_c"]
```

- [ ] **Step 2: Run the failing tests**

```bash
pytest tests/test_verify_suggest.py -v
```

Expected: ImportError on `from ks_gen.verify.suggest import Suggestion, build_suggestions`.

- [ ] **Step 3: Create `src/ks_gen/verify/suggest.py`**

```python
"""Suggest ExceptionDecl entries for verify failures.

Pure-function building blocks plus the (file-touching) apply path.
The apply path is the only file mutation surface — see `apply_to_host_yaml`
for the validate-before-write invariant.
"""
from __future__ import annotations

from dataclasses import dataclass

from ks_gen.config import ExceptionDecl
from ks_gen.verify.reconcile import Category, VerifyReport


@dataclass(frozen=True)
class Suggestion:
    decl: ExceptionDecl
    category: Category  # "new_fail" or "regression"


_SUGGESTABLE: frozenset[Category] = frozenset({"new_fail", "regression"})


def _reason_for(row_host: str, row_date: str, row_current: str, row_install: str | None, category: Category) -> str:
    install = row_install if row_install is not None else "-"
    return (
        f"TODO: explain why — auto-suggested {row_date} from {row_host} "
        f"(current={row_current}, install={install}, category={category})"
    )


def build_suggestions(report: VerifyReport) -> list[Suggestion]:
    """Filter the report to rows worth suggesting an exception for.

    Includes `new_fail` and `regression` only. Order matches `report.rows`
    (which is sorted by rule_id at build time).
    """
    date = report.timestamp_utc.split("T", 1)[0]
    suggestions: list[Suggestion] = []
    for row in report.rows:
        if row.category not in _SUGGESTABLE:
            continue
        decl = ExceptionDecl(
            id=f"auto-{row.category}-{row.rule_id}",
            reason=_reason_for(report.host, date, row.current, row.install, row.category),
            stig_rules_disabled=[row.rule_id],
        )
        suggestions.append(Suggestion(decl=decl, category=row.category))
    return suggestions
```

- [ ] **Step 4: Run all suggest tests**

```bash
pytest tests/test_verify_suggest.py -v
```

Expected: all 6 pass.

- [ ] **Step 5: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/verify/suggest.py tests/test_verify_suggest.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(verify): build_suggestions() — pure ExceptionDecl builder for failing rows"
```

---

### Task 3: `render_yaml` in `verify/suggest.py`

Pure function that produces the paste-friendly YAML block. Golden-snapshot tested via syrupy (existing repo pattern — see `tests/__snapshots__/test_bootloader.ambr`).

**Files:**
- Modify: `src/ks_gen/verify/suggest.py` (add `render_yaml`)
- Modify: `tests/test_verify_suggest.py` (append render tests)
- Create: `tests/__snapshots__/test_verify_suggest.ambr` (auto-generated)

- [ ] **Step 1: Write failing tests for `render_yaml`**

Append to `tests/test_verify_suggest.py`:

```python
# --- render_yaml tests -----------------------------------------------------

from syrupy.assertion import SnapshotAssertion

from ks_gen.verify.suggest import render_yaml


def test_render_yaml_empty_suggestions_returns_empty_string():
    report = _report(VerifyRow("rule_a", "pass", "pass", False, "clean"))
    assert render_yaml([], report) == ""


def test_render_yaml_mixed_categories(snapshot: SnapshotAssertion):
    report = _report(
        VerifyRow("xccdf_rule_d", "fail", "fail", False, "new_fail"),
        VerifyRow("xccdf_rule_e", "fail", "pass", False, "regression"),
        host="web01.example.com",
    )
    suggestions = build_suggestions(report)
    assert render_yaml(suggestions, report) == snapshot


def test_render_yaml_header_includes_run_context():
    report = _report(
        VerifyRow("rule_d", "fail", "fail", False, "new_fail"),
        host="web01.example.com",
    )
    suggestions = build_suggestions(report)
    out = render_yaml(suggestions, report)
    assert out.startswith("## Suggested exception entries")
    assert "web01.example.com" in out
    assert "2026-06-09T12:00:00Z" in out
    assert "1 suggestion" in out  # singular


def test_render_yaml_header_pluralizes_count():
    report = _report(
        VerifyRow("rule_d", "fail", "fail", False, "new_fail"),
        VerifyRow("rule_e", "fail", "pass", False, "regression"),
    )
    out = render_yaml(build_suggestions(report), report)
    assert "2 suggestions" in out
```

- [ ] **Step 2: Run the failing tests**

```bash
pytest tests/test_verify_suggest.py -v -k render_yaml
```

Expected: ImportError / AttributeError on `render_yaml`.

- [ ] **Step 3: Add `render_yaml` to `src/ks_gen/verify/suggest.py`**

Append to the file (after `build_suggestions`):

```python
import yaml


def render_yaml(suggestions: list[Suggestion], report: VerifyReport) -> str:
    """Paste-friendly YAML block. Empty string when suggestions=[].

    Uses yaml.safe_dump with sort_keys=False so the per-decl field order
    matches the schema (id -> reason -> stig_rules_disabled).
    """
    if not suggestions:
        return ""
    n = len(suggestions)
    plural = "suggestion" if n == 1 else "suggestions"
    header = (
        "## Suggested exception entries — copy into host.yaml's `exceptions:` list\n"
        f"## verify host={report.host} user={report.user} "
        f"at={report.timestamp_utc} ({n} {plural})\n"
        "\n"
    )
    body_parts: list[str] = []
    for suggestion in suggestions:
        block = yaml.safe_dump(
            [suggestion.decl.model_dump()],
            sort_keys=False,
            default_flow_style=False,
        )
        body_parts.append(block)
    return header + "\n".join(body_parts)
```

- [ ] **Step 4: Run the render tests and update the snapshot**

```bash
pytest tests/test_verify_suggest.py::test_render_yaml_mixed_categories --snapshot-update
pytest tests/test_verify_suggest.py -v -k render_yaml
```

Expected: all pass. The snapshot file is created at `tests/__snapshots__/test_verify_suggest.ambr`.

- [ ] **Step 5: Inspect the generated snapshot**

```bash
cat tests/__snapshots__/test_verify_suggest.ambr
```

Verify: the snapshot contains the two-line `##` header followed by two YAML blocks separated by a blank line; each block has `id:`, `reason:`, `stig_rules_disabled:` in that order; the `auto-new_fail-` and `auto-regression-` ids are present.

- [ ] **Step 6: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/ks_gen/verify/suggest.py tests/test_verify_suggest.py tests/__snapshots__/test_verify_suggest.ambr
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(verify): render_yaml() — paste-friendly suggestion output"
```

---

### Task 4: `report.py` gains optional `suggestions=` param

`render_table` and `render_json` learn to append a suggestions block. When `suggestions=None` (default), output is unchanged — preserves backward compatibility.

**Files:**
- Modify: `src/ks_gen/verify/report.py`
- Modify: `tests/test_verify_report.py` (add tests for the new param)

- [ ] **Step 1: Write failing tests for the new param**

Read the existing `tests/test_verify_report.py` and append (at end of file):

```python
# --- suggestions= param tests ----------------------------------------------

from ks_gen.verify.suggest import build_suggestions


def _report_with_failures() -> VerifyReport:
    return VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(
            VerifyRow("rule_d", "fail", "fail", False, "new_fail"),
            VerifyRow("rule_e", "fail", "pass", False, "regression"),
        ),
        install_baseline_available=True,
    )


def test_render_table_without_suggestions_unchanged():
    report = _report_with_failures()
    out_with_none = render_table(report)
    out_without_param = render_table(report, suggestions=None)
    assert out_with_none == out_without_param
    assert "Suggested exception entries" not in out_with_none


def test_render_table_with_suggestions_appends_block():
    report = _report_with_failures()
    suggestions = build_suggestions(report)
    out = render_table(report, suggestions=suggestions)
    assert "Suggested exception entries" in out
    assert "auto-new_fail-rule_d" in out
    assert "auto-regression-rule_e" in out


def test_render_json_without_suggestions_omits_key():
    import json as _json
    report = _report_with_failures()
    payload = _json.loads(render_json(report))
    assert "suggested_exceptions" not in payload


def test_render_json_with_suggestions_includes_array():
    import json as _json
    report = _report_with_failures()
    suggestions = build_suggestions(report)
    payload = _json.loads(render_json(report, suggestions=suggestions))
    assert "suggested_exceptions" in payload
    assert len(payload["suggested_exceptions"]) == 2
    assert payload["suggested_exceptions"][0] == {
        "category": "new_fail",
        "decl": {
            "id": "auto-new_fail-rule_d",
            "reason": payload["suggested_exceptions"][0]["decl"]["reason"],
            "stig_rules_disabled": ["rule_d"],
        },
    }


def test_render_json_with_empty_suggestions_includes_empty_array():
    import json as _json
    report = _report_with_failures()
    payload = _json.loads(render_json(report, suggestions=[]))
    assert payload["suggested_exceptions"] == []
```

- [ ] **Step 2: Run the failing tests**

```bash
pytest tests/test_verify_report.py -v -k "suggestions or suggested_exceptions"
```

Expected: TypeError — `render_table()` / `render_json()` got unexpected keyword `suggestions`.

- [ ] **Step 3: Update `src/ks_gen/verify/report.py`**

Replace the file with:

```python
from __future__ import annotations

import json
from collections import Counter

from ks_gen.verify.reconcile import VerifyReport
from ks_gen.verify.suggest import Suggestion, render_yaml


def _summary(report: VerifyReport) -> dict[str, int]:
    counts: Counter[str] = Counter(r.category for r in report.rows)
    return {
        "clean": counts.get("clean", 0),
        "expected_fail": counts.get("expected_fail", 0),
        "new_fail": counts.get("new_fail", 0),
        "regression": counts.get("regression", 0),
        "incomplete": counts.get("incomplete", 0),
    }


def render_table(
    report: VerifyReport, *, suggestions: list[Suggestion] | None = None
) -> str:
    """Plain-text report. Omits `clean` rows by default to keep output focused.

    When `suggestions` is a non-None list (including empty), appends a
    rendered suggestions block via `render_yaml`. None means "operator
    didn't ask for suggestions" and output is unchanged.
    """
    lines: list[str] = []
    lines.append(f"verify host={report.host} user={report.user} at={report.timestamp_utc}")
    if not report.install_baseline_available:
        lines.append("  NOTE: drift comparison skipped — install-time ARF not present on host")
    summary = _summary(report)
    lines.append(
        "  summary: "
        + " ".join(f"{k}={v}" for k, v in summary.items())
        + (" — CLEAN" if report.is_clean else " — FAILURES")
    )

    visible = [r for r in report.rows if r.category != "clean"]
    if not visible:
        lines.append("  (no actionable rows)")
        base = "\n".join(lines) + "\n"
    else:
        rule_w = max(len(r.rule_id) for r in visible)
        cat_w = max(len("CATEGORY"), max(len(r.category) for r in visible))
        cur_w = max(len("CURRENT"), max(len(r.current) for r in visible))
        inst_w = max(
            len("INSTALL"),
            max(len(r.install) if r.install is not None else 1 for r in visible),
        )
        lines.append("")
        lines.append(f"  {'CATEGORY':<{cat_w}}  {'CURRENT':<{cur_w}}  {'INSTALL':<{inst_w}}  EXP  RULE")
        for r in visible:
            inst = r.install if r.install is not None else "-"
            exp = "yes" if r.expected else "no "
            cat = f"{r.category:<{cat_w}}"
            cur = f"{r.current:<{cur_w}}"
            instc = f"{inst:<{inst_w}}"
            rule = f"{r.rule_id:<{rule_w}}"
            lines.append(f"  {cat}  {cur}  {instc}  {exp}  {rule}")
        base = "\n".join(lines) + "\n"

    if suggestions is None:
        return base
    suggestion_block = render_yaml(suggestions, report)
    if not suggestion_block:
        return base
    return base + "\n" + suggestion_block


def render_json(
    report: VerifyReport, *, suggestions: list[Suggestion] | None = None
) -> str:
    payload: dict[str, object] = {
        "host": report.host,
        "user": report.user,
        "timestamp_utc": report.timestamp_utc,
        "install_baseline_available": report.install_baseline_available,
        "is_clean": report.is_clean,
        "summary": _summary(report),
        "rows": [
            {
                "rule_id": r.rule_id,
                "current": r.current,
                "install": r.install,
                "expected": r.expected,
                "category": r.category,
            }
            for r in report.rows
        ],
    }
    if suggestions is not None:
        payload["suggested_exceptions"] = [
            {"category": s.category, "decl": s.decl.model_dump()}
            for s in suggestions
        ]
    return json.dumps(payload, indent=2)
```

- [ ] **Step 4: Run all report tests**

```bash
pytest tests/test_verify_report.py -v
```

Expected: all pass — existing tests stay green (since `suggestions` defaults to None), plus the 5 new tests pass.

- [ ] **Step 5: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/verify/report.py tests/test_verify_report.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(verify): render_table/render_json accept optional suggestions= param"
```

---

### Task 5: `apply_to_host_yaml` — full impl + happy path & idempotency tests

The most important task in the plan. Full function implementation (validate → backup → atomic write). Tests cover the happy path and idempotency now; subsequent tasks add allow_regression, backup file verification, and error-path tests.

**Files:**
- Modify: `src/ks_gen/verify/suggest.py` (add `AppendResult` + `apply_to_host_yaml`)
- Modify: `tests/test_verify_suggest.py` (append apply tests)

- [ ] **Step 1: Write failing tests for happy path + idempotency**

Append to `tests/test_verify_suggest.py`:

```python
# --- apply_to_host_yaml tests ---------------------------------------------

import textwrap
from pathlib import Path

import pytest
import yaml

from ks_gen.verify.suggest import AppendResult, apply_to_host_yaml


_BASE_HOST_YAML = textwrap.dedent(
    """\
    system: {hostname: h1}
    user:
      admin:
        name: ops
        authorized_keys: ["ssh-ed25519 A a@b"]
        sudo: nopasswd_yes
    """
)


def _write_host_yaml(tmp_path: Path, text: str = _BASE_HOST_YAML) -> Path:
    p = tmp_path / "host.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def _new_fail_report() -> VerifyReport:
    return _report(
        VerifyRow("rule_d", "fail", "fail", False, "new_fail"),
        VerifyRow("rule_e", "fail", "pass", False, "regression"),
    )


def test_apply_appends_new_fail_to_empty_exceptions(tmp_path: Path):
    host_yaml = _write_host_yaml(tmp_path)
    suggestions = build_suggestions(_new_fail_report())

    result = apply_to_host_yaml(
        suggestions=suggestions,
        host_yaml_path=host_yaml,
        allow_regression=False,
    )

    assert isinstance(result, AppendResult)
    assert result.added == ("auto-new_fail-rule_d",)
    assert result.skipped_existing == ()
    assert result.skipped_regression == ("auto-regression-rule_e",)
    assert result.path == host_yaml
    assert result.backup_path == host_yaml.with_suffix(".yaml.bak")

    after = yaml.safe_load(host_yaml.read_text(encoding="utf-8"))
    assert len(after["exceptions"]) == 1
    assert after["exceptions"][0]["id"] == "auto-new_fail-rule_d"
    assert after["exceptions"][0]["stig_rules_disabled"] == ["rule_d"]


def test_apply_is_idempotent_when_id_already_present(tmp_path: Path):
    host_yaml = _write_host_yaml(tmp_path)
    suggestions = build_suggestions(_new_fail_report())

    # First apply: writes one suggestion.
    apply_to_host_yaml(
        suggestions=suggestions, host_yaml_path=host_yaml, allow_regression=False
    )
    mtime_after_first = host_yaml.stat().st_mtime_ns

    # Second apply with same suggestions: nothing to add (already present).
    result = apply_to_host_yaml(
        suggestions=suggestions, host_yaml_path=host_yaml, allow_regression=False
    )

    assert result.added == ()
    assert result.skipped_existing == ("auto-new_fail-rule_d",)
    assert result.skipped_regression == ("auto-regression-rule_e",)
    assert host_yaml.stat().st_mtime_ns == mtime_after_first  # no second write


def test_apply_preserves_pre_existing_exceptions(tmp_path: Path):
    pre = textwrap.dedent(
        """\
        system: {hostname: h1}
        user:
          admin:
            name: ops
            authorized_keys: ["ssh-ed25519 A a@b"]
            sudo: nopasswd_yes
        exceptions:
          - id: legacy-fips-deviation
            reason: "approved by security 2026-01-01"
            stig_rules_disabled: [rule_x]
        """
    )
    host_yaml = _write_host_yaml(tmp_path, pre)
    suggestions = build_suggestions(_new_fail_report())

    apply_to_host_yaml(
        suggestions=suggestions, host_yaml_path=host_yaml, allow_regression=False
    )

    after = yaml.safe_load(host_yaml.read_text(encoding="utf-8"))
    ids = [e["id"] for e in after["exceptions"]]
    assert "legacy-fips-deviation" in ids
    assert "auto-new_fail-rule_d" in ids
    assert len(after["exceptions"]) == 2
```

- [ ] **Step 2: Run the failing tests**

```bash
pytest tests/test_verify_suggest.py -v -k apply
```

Expected: ImportError on `AppendResult` / `apply_to_host_yaml`.

- [ ] **Step 3: Add `AppendResult` + `apply_to_host_yaml` to `src/ks_gen/verify/suggest.py`**

Append to the file. First, add to the top-of-file imports:

```python
import shutil
from pathlib import Path
from typing import Any
```

Then append at the end:

```python
@dataclass(frozen=True)
class AppendResult:
    added: tuple[str, ...]               # decl ids written this call
    skipped_existing: tuple[str, ...]    # decl ids already present in host.yaml
    skipped_regression: tuple[str, ...]  # regression decl ids gated out
    path: Path                           # the host.yaml that was written
    backup_path: Path                    # host.yaml.bak


def apply_to_host_yaml(
    *,
    suggestions: list[Suggestion],
    host_yaml_path: Path,
    allow_regression: bool,
) -> AppendResult:
    """Idempotent append-only write to host.yaml's exceptions list.

    Writes <path>.bak before modifying. Round-trips the candidate through
    `HostConfig.model_validate` and only writes if validation passes.
    Raises `SuggestApplyError` on read/parse/validate/IO failure with
    host.yaml byte-identical to its pre-call state.
    """
    # Local import to avoid circular: verify/__init__.py imports suggest,
    # config doesn't depend on verify but pulling it in at module load
    # adds startup cost to verify/__init__.
    from ks_gen.config import HostConfig
    from ks_gen.verify.errors import SuggestApplyError

    # Step 1: filter by allow_regression
    to_consider: list[Suggestion] = []
    skipped_regression: list[str] = []
    for suggestion in suggestions:
        if suggestion.category == "regression" and not allow_regression:
            skipped_regression.append(suggestion.decl.id)
        else:
            to_consider.append(suggestion)

    # Step 2: read & parse
    try:
        raw = host_yaml_path.read_text(encoding="utf-8")
    except OSError as e:
        raise SuggestApplyError(f"cannot read {host_yaml_path}: {e}") from e
    try:
        data: Any = yaml.safe_load(raw) or {}
    except yaml.YAMLError as e:
        raise SuggestApplyError(
            f"host.yaml is not valid YAML: {e}; refusing to modify."
        ) from e
    if not isinstance(data, dict):
        raise SuggestApplyError(
            f"host.yaml is not a YAML mapping (got {type(data).__name__}); "
            "refusing to modify."
        )

    # Step 3: compute existing ids
    raw_exceptions = data.get("exceptions") or []
    existing_ids = {
        entry["id"]
        for entry in raw_exceptions
        if isinstance(entry, dict) and "id" in entry
    }

    # Step 4: filter idempotent
    to_apply: list[Suggestion] = []
    skipped_existing: list[str] = []
    for suggestion in to_consider:
        if suggestion.decl.id in existing_ids:
            skipped_existing.append(suggestion.decl.id)
        else:
            to_apply.append(suggestion)

    backup_path = host_yaml_path.with_suffix(host_yaml_path.suffix + ".bak")

    if not to_apply:
        # Idempotent no-op: skip all I/O including backup.
        return AppendResult(
            added=(),
            skipped_existing=tuple(skipped_existing),
            skipped_regression=tuple(skipped_regression),
            path=host_yaml_path,
            backup_path=backup_path,
        )

    # Step 5: build candidate
    candidate = dict(data)
    candidate["exceptions"] = list(raw_exceptions) + [
        s.decl.model_dump() for s in to_apply
    ]

    # Step 6: validate via pydantic — refuse to write a candidate that
    # wouldn't load. Order: validate -> backup -> write.
    try:
        HostConfig.model_validate(candidate)
    except Exception as e:
        raise SuggestApplyError(
            f"applied host.yaml would fail validation: {e}; original untouched."
        ) from e

    # Step 7: backup (after validation passes)
    try:
        shutil.copy2(host_yaml_path, backup_path)
    except OSError as e:
        raise SuggestApplyError(
            f"cannot write backup {backup_path}: {e}; original untouched."
        ) from e

    # Step 8: atomic write
    tmp = host_yaml_path.with_suffix(host_yaml_path.suffix + ".tmp")
    try:
        tmp.write_text(
            yaml.safe_dump(candidate, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
            newline="\n",
        )
        tmp.replace(host_yaml_path)
    except OSError as e:
        raise SuggestApplyError(
            f"cannot write {host_yaml_path}: {e}"
        ) from e

    return AppendResult(
        added=tuple(s.decl.id for s in to_apply),
        skipped_existing=tuple(skipped_existing),
        skipped_regression=tuple(skipped_regression),
        path=host_yaml_path,
        backup_path=backup_path,
    )
```

- [ ] **Step 4: Run the apply tests**

```bash
pytest tests/test_verify_suggest.py -v -k apply
```

Expected: 3 happy-path + idempotency tests pass.

- [ ] **Step 5: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/verify/suggest.py tests/test_verify_suggest.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(verify): apply_to_host_yaml() — validate-then-backup-then-write"
```

---

### Task 6: `apply_to_host_yaml` — allow_regression tests

The function already supports `allow_regression`; this task pins it with tests.

**Files:**
- Modify: `tests/test_verify_suggest.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_verify_suggest.py`:

```python
def test_apply_allow_regression_true_writes_regressions(tmp_path: Path):
    host_yaml = _write_host_yaml(tmp_path)
    suggestions = build_suggestions(_new_fail_report())

    result = apply_to_host_yaml(
        suggestions=suggestions,
        host_yaml_path=host_yaml,
        allow_regression=True,
    )

    assert result.added == ("auto-new_fail-rule_d", "auto-regression-rule_e")
    assert result.skipped_regression == ()

    after = yaml.safe_load(host_yaml.read_text(encoding="utf-8"))
    ids = [e["id"] for e in after["exceptions"]]
    assert ids == ["auto-new_fail-rule_d", "auto-regression-rule_e"]


def test_apply_allow_regression_false_skips_regressions_only(tmp_path: Path):
    host_yaml = _write_host_yaml(tmp_path)
    suggestions = build_suggestions(_new_fail_report())

    result = apply_to_host_yaml(
        suggestions=suggestions,
        host_yaml_path=host_yaml,
        allow_regression=False,
    )

    # new_fail flowed through, regression was held back
    assert result.added == ("auto-new_fail-rule_d",)
    assert result.skipped_regression == ("auto-regression-rule_e",)

    after = yaml.safe_load(host_yaml.read_text(encoding="utf-8"))
    ids = [e["id"] for e in after["exceptions"]]
    assert ids == ["auto-new_fail-rule_d"]
```

- [ ] **Step 2: Run the tests**

```bash
pytest tests/test_verify_suggest.py -v -k allow_regression
```

Expected: PASS (apply already handles allow_regression in Task 5; these tests pin the behavior).

- [ ] **Step 3: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_verify_suggest.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "test(verify): pin apply_to_host_yaml allow_regression filtering"
```

---

### Task 7: `apply_to_host_yaml` — backup file behavior

Tests that `host.yaml.bak` is created on write, matches the pre-apply content byte-for-byte, gets overwritten on subsequent writes, and is NOT created when there's nothing to apply.

**Files:**
- Modify: `tests/test_verify_suggest.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_verify_suggest.py`:

```python
def test_apply_writes_backup_matching_pre_apply_content(tmp_path: Path):
    host_yaml = _write_host_yaml(tmp_path)
    pre_content = host_yaml.read_text(encoding="utf-8")
    suggestions = build_suggestions(_new_fail_report())

    apply_to_host_yaml(
        suggestions=suggestions, host_yaml_path=host_yaml, allow_regression=False
    )

    backup = host_yaml.with_suffix(".yaml.bak")
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == pre_content


def test_apply_overwrites_existing_backup(tmp_path: Path):
    host_yaml = _write_host_yaml(tmp_path)
    suggestions_v1 = build_suggestions(_new_fail_report())

    # First apply creates .bak from the original
    apply_to_host_yaml(
        suggestions=suggestions_v1, host_yaml_path=host_yaml, allow_regression=False
    )
    # Now main has 1 entry; .bak has 0
    backup = host_yaml.with_suffix(".yaml.bak")
    assert "exceptions" not in yaml.safe_load(backup.read_text(encoding="utf-8")) or \
           yaml.safe_load(backup.read_text(encoding="utf-8")).get("exceptions") in (None, [])

    # Second apply with a different rule overwrites .bak with the
    # now-1-entry main
    new_report = _report(VerifyRow("rule_f", "fail", "fail", False, "new_fail"))
    suggestions_v2 = build_suggestions(new_report)
    apply_to_host_yaml(
        suggestions=suggestions_v2, host_yaml_path=host_yaml, allow_regression=False
    )

    backup_after = yaml.safe_load(backup.read_text(encoding="utf-8"))
    backup_ids = [e["id"] for e in backup_after["exceptions"]]
    assert backup_ids == ["auto-new_fail-rule_d"]  # the previous main state


def test_apply_no_op_does_not_create_backup(tmp_path: Path):
    host_yaml = _write_host_yaml(tmp_path)
    # No failing rows -> no suggestions -> nothing to apply
    suggestions: list[Suggestion] = []

    apply_to_host_yaml(
        suggestions=suggestions, host_yaml_path=host_yaml, allow_regression=False
    )

    backup = host_yaml.with_suffix(".yaml.bak")
    assert not backup.exists()
```

- [ ] **Step 2: Run the tests**

```bash
pytest tests/test_verify_suggest.py -v -k "backup or no_op"
```

Expected: PASS.

- [ ] **Step 3: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_verify_suggest.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "test(verify): pin apply_to_host_yaml backup file rotation"
```

---

### Task 8: `apply_to_host_yaml` — error paths

Tests for malformed host.yaml, schema-rejecting candidates, and the invariant that the original file is untouched on failure.

**Files:**
- Modify: `tests/test_verify_suggest.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_verify_suggest.py`:

```python
from ks_gen.verify.errors import SuggestApplyError


def test_apply_refuses_yaml_list_at_top_level(tmp_path: Path):
    host_yaml = tmp_path / "host.yaml"
    host_yaml.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    suggestions = build_suggestions(_new_fail_report())

    with pytest.raises(SuggestApplyError, match="not a YAML mapping"):
        apply_to_host_yaml(
            suggestions=suggestions,
            host_yaml_path=host_yaml,
            allow_regression=False,
        )

    # Original file untouched
    assert host_yaml.read_text(encoding="utf-8") == "- not\n- a\n- mapping\n"
    assert not (tmp_path / "host.yaml.bak").exists()


def test_apply_refuses_invalid_yaml_syntax(tmp_path: Path):
    host_yaml = tmp_path / "host.yaml"
    host_yaml.write_text("key: : : ::\n  broken\n", encoding="utf-8")
    suggestions = build_suggestions(_new_fail_report())

    with pytest.raises(SuggestApplyError, match="not valid YAML"):
        apply_to_host_yaml(
            suggestions=suggestions,
            host_yaml_path=host_yaml,
            allow_regression=False,
        )

    assert not (tmp_path / "host.yaml.bak").exists()


def test_apply_refuses_schema_rejecting_candidate(tmp_path: Path):
    # host.yaml is loadable as YAML but violates HostConfig (no admin keys
    # with an unset password). When we try to append, candidate validation
    # fails. No write, no backup.
    bad = textwrap.dedent(
        """\
        system: {hostname: h1}
        user:
          admin:
            name: ops
            # neither password nor authorized_keys -> pydantic rejects
        """
    )
    host_yaml = _write_host_yaml(tmp_path, bad)
    pre_content = host_yaml.read_text(encoding="utf-8")
    suggestions = build_suggestions(_new_fail_report())

    with pytest.raises(SuggestApplyError, match="would fail validation"):
        apply_to_host_yaml(
            suggestions=suggestions,
            host_yaml_path=host_yaml,
            allow_regression=False,
        )

    assert host_yaml.read_text(encoding="utf-8") == pre_content
    assert not (tmp_path / "host.yaml.bak").exists()


def test_apply_with_empty_host_yaml_file_treats_as_empty_mapping(tmp_path: Path):
    host_yaml = tmp_path / "host.yaml"
    host_yaml.write_text("", encoding="utf-8")
    # Empty file -> data = {} -> candidate = {"exceptions": [...]}
    # But the candidate must still satisfy HostConfig, which requires
    # `system` and `user.admin` — so validation will reject. Verify the
    # specific failure surfaces as SuggestApplyError, not a raw pydantic
    # ValidationError.
    suggestions = build_suggestions(_new_fail_report())

    with pytest.raises(SuggestApplyError, match="would fail validation"):
        apply_to_host_yaml(
            suggestions=suggestions,
            host_yaml_path=host_yaml,
            allow_regression=False,
        )
```

- [ ] **Step 2: Run the failing tests**

```bash
pytest tests/test_verify_suggest.py -v -k "refuses or empty_host_yaml"
```

Expected: PASS — the apply impl from Task 5 already raises `SuggestApplyError` for these cases.

- [ ] **Step 3: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_verify_suggest.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "test(verify): pin apply_to_host_yaml error paths (malformed yaml, schema reject)"
```

---

### Task 9: CLI `--suggest-exceptions` flag (read-only)

Wires the flag into `verify_cmd`. No apply yet — just computes suggestions and threads them into the renderers.

**Files:**
- Modify: `src/ks_gen/cli.py`
- Modify: `tests/test_cli/test_verify.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli/test_verify.py`:

```python
def _new_fail_report() -> VerifyReport:
    return VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(
            VerifyRow("rule_d", "fail", "fail", False, "new_fail"),
            VerifyRow("rule_e", "fail", "pass", False, "regression"),
        ),
        install_baseline_available=True,
    )


def test_verify_suggest_exceptions_appends_yaml_block(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with (
        patch("ks_gen.cli.check_tools"),
        patch("ks_gen.cli.run_verify", return_value=_new_fail_report()),
    ):
        result = runner.invoke(
            app,
            ["verify", "--host", "h1", "--config", str(cfg), "--suggest-exceptions"],
        )
    assert result.exit_code == int(ExitCode.VERIFY_FAIL)
    assert "Suggested exception entries" in result.stdout
    assert "auto-new_fail-rule_d" in result.stdout
    assert "auto-regression-rule_e" in result.stdout


def test_verify_suggest_exceptions_json_includes_array(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with (
        patch("ks_gen.cli.check_tools"),
        patch("ks_gen.cli.run_verify", return_value=_new_fail_report()),
    ):
        result = runner.invoke(
            app,
            [
                "verify", "--host", "h1", "--config", str(cfg),
                "--suggest-exceptions", "--format", "json",
            ],
        )
    import json as _json
    payload = _json.loads(result.stdout)
    assert "suggested_exceptions" in payload
    assert len(payload["suggested_exceptions"]) == 2
```

You'll also need this import at the top of the test file (skip if already present):

```python
from ks_gen.loader import ExitCode
```

- [ ] **Step 2: Run the failing tests**

```bash
pytest tests/test_cli/test_verify.py -v -k suggest_exceptions
```

Expected: failure — typer reports `--suggest-exceptions` as an unknown option.

- [ ] **Step 3: Update `src/ks_gen/cli.py`**

Modify two areas of `cli.py`:

**(a)** Add to the imports at the top:

```python
from ks_gen.verify.suggest import build_suggestions
```

**(b)** Add the new flag parameter to `verify_cmd`'s signature (between `no_drift` and `timeout`):

```python
    suggest_exceptions: bool = typer.Option(
        False,
        "--suggest-exceptions",
        help="Render ready-to-paste ExceptionDecl YAML for new_fail and regression rules.",
    ),
```

**(c)** Replace the render call inside `_do(workdir)`. Find:

```python
        if format_ == "json":
            typer.echo(render_json(report))
        else:
            typer.echo(render_table(report))
```

Replace with:

```python
        suggestions = build_suggestions(report) if suggest_exceptions else None
        if format_ == "json":
            typer.echo(render_json(report, suggestions=suggestions))
        else:
            typer.echo(render_table(report, suggestions=suggestions))
```

- [ ] **Step 4: Run all verify CLI tests**

```bash
pytest tests/test_cli/test_verify.py -v
```

Expected: all pass — pre-existing tests stay green (since the renderers' `suggestions=None` default preserves output), plus the 2 new tests pass.

- [ ] **Step 5: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/cli.py tests/test_cli/test_verify.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(verify): add --suggest-exceptions flag to verify CLI"
```

---

### Task 10: CLI `--apply` flag (implies `--suggest-exceptions`)

Wires the apply path. New_fail only by default; regression-category writes still gated to Task 11.

**Files:**
- Modify: `src/ks_gen/cli.py`
- Modify: `tests/test_cli/test_verify.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli/test_verify.py`:

```python
def test_verify_apply_writes_new_fail_to_host_yaml(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with (
        patch("ks_gen.cli.check_tools"),
        patch("ks_gen.cli.run_verify", return_value=_new_fail_report()),
    ):
        result = runner.invoke(
            app,
            ["verify", "--host", "h1", "--config", str(cfg), "--apply"],
        )

    assert result.exit_code == int(ExitCode.VERIFY_FAIL)
    # Suggestions also rendered because --apply implies --suggest-exceptions
    assert "Suggested exception entries" in result.stdout
    # host.yaml now has the new_fail exception, NOT the regression
    import yaml as _yaml
    after = _yaml.safe_load(cfg.read_text(encoding="utf-8"))
    ids = [e["id"] for e in after.get("exceptions", [])]
    assert ids == ["auto-new_fail-rule_d"]
    # Backup exists
    assert (tmp_path / "host.yaml.bak").exists()
    # Stderr summary mentions the regression was held back
    assert "auto-regression-rule_e" in result.stderr or \
           "auto-regression-rule_e" in result.output
```

- [ ] **Step 2: Run the failing test**

```bash
pytest tests/test_cli/test_verify.py::test_verify_apply_writes_new_fail_to_host_yaml -v
```

Expected: failure — typer reports `--apply` as unknown.

- [ ] **Step 3: Update `src/ks_gen/cli.py`**

**(a)** Add to the top imports:

```python
from ks_gen.verify.suggest import apply_to_host_yaml
```

(The `build_suggestions` import is already in place from Task 9. Adjust the import line to combine if cleaner.)

**(b)** Add the `--apply` parameter to `verify_cmd`'s signature (between `suggest_exceptions` and `timeout`):

```python
    apply: bool = typer.Option(
        False,
        "--apply",
        help=(
            "Append the suggestions to host.yaml after a backup + schema "
            "round-trip. Implies --suggest-exceptions. Regression-category "
            "suggestions require --allow-regression."
        ),
    ),
```

**(c)** Update the renderer-feeding logic in `_do(workdir)`. Replace the block from Task 9:

```python
        suggestions = build_suggestions(report) if suggest_exceptions else None
        if format_ == "json":
            typer.echo(render_json(report, suggestions=suggestions))
        else:
            typer.echo(render_table(report, suggestions=suggestions))
```

With:

```python
        want_suggestions = suggest_exceptions or apply
        suggestions = build_suggestions(report) if want_suggestions else None
        if format_ == "json":
            typer.echo(render_json(report, suggestions=suggestions))
        else:
            typer.echo(render_table(report, suggestions=suggestions))

        if apply and suggestions:
            try:
                result = apply_to_host_yaml(
                    suggestions=suggestions,
                    host_yaml_path=config,
                    allow_regression=False,
                )
            except VerifyError as e:
                typer.echo(f"ks-gen verify: apply failed: {e}", err=True)
                raise typer.Exit(code=int(e.exit_code)) from None
            _echo_apply_summary(result)
```

**(d)** Add the helper at module scope (above `verify_cmd`):

```python
def _echo_apply_summary(result: "AppendResult") -> None:
    if result.added:
        typer.echo(
            f"ks-gen verify: applied {len(result.added)} suggestion(s): "
            f"{', '.join(result.added)} (backup at {result.backup_path})",
            err=True,
        )
    if result.skipped_existing:
        typer.echo(
            f"ks-gen verify: skipped {len(result.skipped_existing)} already-present: "
            f"{', '.join(result.skipped_existing)}",
            err=True,
        )
    if result.skipped_regression:
        typer.echo(
            f"ks-gen verify: skipped {len(result.skipped_regression)} regression "
            f"(use --allow-regression to apply): {', '.join(result.skipped_regression)}",
            err=True,
        )
    if not (result.added or result.skipped_existing or result.skipped_regression):
        typer.echo("ks-gen verify: nothing to apply", err=True)
```

And add the forward-import for `AppendResult` near the top:

```python
from ks_gen.verify.suggest import AppendResult, apply_to_host_yaml, build_suggestions
```

(Adjust the existing single import line accordingly.)

- [ ] **Step 4: Run all verify CLI tests**

```bash
pytest tests/test_cli/test_verify.py -v
```

Expected: all pass.

- [ ] **Step 5: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/cli.py tests/test_cli/test_verify.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(verify): add --apply flag (writes new_fail suggestions to host.yaml)"
```

---

### Task 11: CLI `--allow-regression` flag + no-effect-without-apply note

**Files:**
- Modify: `src/ks_gen/cli.py`
- Modify: `tests/test_cli/test_verify.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_cli/test_verify.py`:

```python
def test_verify_apply_allow_regression_writes_regression_too(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with (
        patch("ks_gen.cli.check_tools"),
        patch("ks_gen.cli.run_verify", return_value=_new_fail_report()),
    ):
        result = runner.invoke(
            app,
            [
                "verify", "--host", "h1", "--config", str(cfg),
                "--apply", "--allow-regression",
            ],
        )

    assert result.exit_code == int(ExitCode.VERIFY_FAIL)
    import yaml as _yaml
    after = _yaml.safe_load(cfg.read_text(encoding="utf-8"))
    ids = [e["id"] for e in after.get("exceptions", [])]
    assert ids == ["auto-new_fail-rule_d", "auto-regression-rule_e"]


def test_verify_allow_regression_without_apply_prints_note(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with (
        patch("ks_gen.cli.check_tools"),
        patch("ks_gen.cli.run_verify", return_value=_new_fail_report()),
    ):
        result = runner.invoke(
            app,
            [
                "verify", "--host", "h1", "--config", str(cfg),
                "--suggest-exceptions", "--allow-regression",
            ],
        )

    # host.yaml is NOT modified
    import yaml as _yaml
    after = _yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert "exceptions" not in after or after["exceptions"] in (None, [])
    # The note appears on stderr
    assert "--allow-regression has no effect without --apply" in (result.stderr or result.output)
```

- [ ] **Step 2: Run the failing tests**

```bash
pytest tests/test_cli/test_verify.py -v -k "allow_regression"
```

Expected: failure — typer reports `--allow-regression` as unknown.

- [ ] **Step 3: Update `src/ks_gen/cli.py`**

**(a)** Add the `--allow-regression` parameter to `verify_cmd`'s signature (between `apply` and `timeout`):

```python
    allow_regression: bool = typer.Option(
        False,
        "--allow-regression",
        help=(
            "Allow --apply to write regression-category suggestions. No effect "
            "without --apply; the safety story is intentional."
        ),
    ),
```

**(b)** Add the no-effect note near the top of `verify_cmd` (after the `--format` validation, before `_do`):

```python
    if allow_regression and not apply:
        typer.echo(
            "ks-gen verify: --allow-regression has no effect without --apply",
            err=True,
        )
```

**(c)** Update the `apply_to_host_yaml` call inside `_do(workdir)` to pass the flag:

```python
                result = apply_to_host_yaml(
                    suggestions=suggestions,
                    host_yaml_path=config,
                    allow_regression=allow_regression,
                )
```

- [ ] **Step 4: Run all verify CLI tests**

```bash
pytest tests/test_cli/test_verify.py -v
```

Expected: all pass.

- [ ] **Step 5: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/cli.py tests/test_cli/test_verify.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(verify): add --allow-regression flag for regression-category apply"
```

---

### Task 12: Update `MANUAL.md` §8.5

Add a subsection covering the three new flags with one worked example.

**Files:**
- Modify: `MANUAL.md` (append to §8.5 or add a new §8.5.x)

- [ ] **Step 1: Read the current §8.5 block**

```bash
grep -n "^### 8\.5\|^## 9\." MANUAL.md | head -5
```

Note the start of §8.5 and the next section header. The new content goes near the end of §8.5, before the next major section.

- [ ] **Step 2: Append a subsection at the end of §8.5**

Using the `Edit` tool, find the last paragraph of §8.5 in `MANUAL.md` (just before the next `### ` or `## ` heading) and append after it:

```markdown
#### Auto-suggesting exception entries

When `verify` reports `new_fail` or `regression` rules, three new flags
help close the audit loop:

- `--suggest-exceptions` — render one `ExceptionDecl` per failing rule
  (`new_fail` and `regression` both), formatted for paste into
  `host.yaml`'s `exceptions:` list. Each suggestion's `id` is
  `auto-<category>-<rule_id>`; its `reason` starts with `TODO:` and
  carries the verify-run context (host, date, current/install states).
- `--apply` — append the suggestions to `host.yaml` after writing a
  backup at `host.yaml.bak` (single rotating slot) and round-tripping
  the candidate through `HostConfig.model_validate()`. The original
  file is byte-identical to its pre-call state on any failure path
  (yaml-parse error, schema-rejecting candidate, IO error). Implies
  `--suggest-exceptions`.
- `--allow-regression` — let `--apply` write regression-category
  suggestions in addition to `new_fail`. The split is deliberate:
  regressions represent rules that passed at install but now fail,
  which is more often a real correctness drift than a legitimate new
  exception. The two-flag dance forces an explicit operator decision.

Worked example:

```bash
ks-gen verify --host web01.example.com --config build/web01/host.yaml \
              --suggest-exceptions
# (prints the table report, then a "## Suggested exception entries"
# block of YAML you can paste into host.yaml's exceptions: list)

ks-gen verify --host web01.example.com --config build/web01/host.yaml \
              --apply
# (also writes the new_fail suggestions to host.yaml; .bak preserves
# the prior content; regression-category suggestions are skipped with
# a stderr note)

ks-gen verify --host web01.example.com --config build/web01/host.yaml \
              --apply --allow-regression
# (also writes regression-category suggestions)
```

**Formatting caveat.** `--apply` uses PyYAML to round-trip
`host.yaml`. Comments and quoting style choices in the original file
are not preserved. The `host.yaml.bak` is the recovery path. Operators
who maintain hand-written comments in `host.yaml` should hand-paste
the rendered suggestions instead of using `--apply`.

Re-running `--apply` with the same suggestions is idempotent: each
already-present `auto-<category>-<rule_id>` id is skipped (no second
write, mtime unchanged), so verifying once and applying twice doesn't
duplicate entries.
```

- [ ] **Step 3: Run the smoke test (no code change → just sanity)**

```bash
pytest tests/test_smoke.py -v
```

Expected: all pass.

- [ ] **Step 4: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add MANUAL.md
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "docs(manual): verify --suggest-exceptions / --apply / --allow-regression"
```

---

### Task 13: Final CI parity + branch push + PR

- [ ] **Step 1: Run the full local CI parity chain one more time**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 2: Verify all commits on the branch are signed**

```bash
git log --format="%h %G? %s" main..HEAD
```

Expected: every line shows `G`. If any show `N`, stop and investigate.

- [ ] **Step 3: Push the branch**

```bash
git push -u origin impl/v0.8.0-verify-suggest-exceptions
```

Expected: branch published.

- [ ] **Step 4: Open the pull request**

```bash
gh pr create --title "feat(verify): auto-suggest exception entries (closes #14)" \
  --body "$(cat <<'EOF'
## Summary
- Closes #14. Adds `--suggest-exceptions`, `--apply`, and `--allow-regression` to `ks-gen verify`.
- New module `src/ks_gen/verify/suggest.py` with `build_suggestions`, `render_yaml`, and `apply_to_host_yaml` (idempotent append-only, validate-before-write, single-rotating-slot backup).
- `render_table` / `render_json` accept an optional `suggestions=` kwarg; behavior unchanged when None.
- Two-flag safety: `--apply` writes `new_fail` only; `--allow-regression` is required to also write regression-category suggestions. The split enforces the issue's stated invariant against rubber-stamping real correctness regressions.
- Adds `SuggestApplyError` (exit code `CONFIG_INVALID`) for malformed host.yaml / schema-rejecting candidate / IO failure.
- Updates MANUAL.md §8.5 with the worked example and the PyYAML formatting caveat.

## Test plan
- [ ] CI green on 3.11 / 3.12 / 3.13
- [ ] Manual smoke: `ks-gen verify --host <real-host> --config <host.yaml> --suggest-exceptions` against a host with `new_fail` / `regression` rows
- [ ] Manual smoke: `--apply` writes only `new_fail`; `host.yaml.bak` exists; re-run is a no-op
- [ ] Manual smoke: `--apply --allow-regression` writes both categories

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed.

---

## Acceptance Verification (post-merge checklist)

Maps to the spec's acceptance criteria:

1. **Suggestion text output** — `test_verify_suggest_exceptions_appends_yaml_block` (Task 9).
2. **JSON `suggested_exceptions` array** — `test_verify_suggest_exceptions_json_includes_array` (Task 9); `test_render_json_without_suggestions_omits_key` confirms backward compat (Task 4).
3. **`--apply` writes only `new_fail`** — `test_verify_apply_writes_new_fail_to_host_yaml` (Task 10).
4. **`--apply --allow-regression` writes regressions** — `test_verify_apply_allow_regression_writes_regression_too` (Task 11).
5. **Idempotent re-run** — `test_apply_is_idempotent_when_id_already_present` (Task 5).
6. **Pydantic-rejected candidate leaves host.yaml untouched** — `test_apply_refuses_schema_rejecting_candidate` (Task 8).
7. **`tests/test_verify_suggest.py` coverage** — every documented edge case has a positive and a negative test (Tasks 2, 3, 5–8).
8. **CI green on 3.11/3.12/3.13** — Task 13 Step 1 (local) and CI on the PR.
