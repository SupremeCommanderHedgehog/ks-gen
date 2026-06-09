# Verify workstation-captured baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `verify --capture-baseline <path>` (writes the fresh-current ARF to a workstation file) and `verify --baseline <path>` (uses that file as the drift baseline in place of `/root/oscap-remediation-results.xml`). Closes #11. Ships the design at `docs/superpowers/specs/2026-06-09-verify-capture-baseline-design.md`.

**Architecture:** New `src/ks_gen/verify/baseline.py` with pure `read_baseline` / `orphan_rule_ids` functions. `VerifyReport` gains optional `baseline: BaselineReport | None` field. `run_verify` gains mutually-exclusive `baseline_path` and `capture_to` params (capture writes `arfs.current_text` from the existing `collect_arfs` call to disk after the normal report builds — no new transport function needed). Renderers surface a header line + footer orphan note (text) / `baseline` block (JSON). Two new CLI flags with a mutual-exclusion check at both CLI and library layers. No new exit codes — capture and baseline-driven reconcile both use existing reconcile semantics.

**Tech Stack:** Python 3.11+, stdlib `xml.etree.ElementTree` (no new deps), typer, pytest + syrupy + monkeypatch + tmp_path. CI parity: `ruff check && ruff format --check && mypy && pytest -q`.

**Branch:** `impl/v0.10.0-verify-capture-baseline` (create in Pre-flight). Depends on v0.9.0's `tailoring_drift` field being on main; PR #39 must merge first.

---

## Pre-flight

- [ ] **Step 1: Confirm v0.9.0 is on main**

```bash
git switch main
git pull --ff-only origin main
git log --oneline -5
```

Expected: a recent commit mentioning v0.9.0 / tailoring-drift / PR #39 merge. If PR #39 is still open, STOP — this plan stacks on v0.9.0 features (`VerifyReport.tailoring_drift`, the v0.10.0 `BaselineReport` field will sit alongside it). Two options if you must proceed before #39 merges: (a) base this branch on `impl/v0.9.0-verify-tailoring-drift` instead of main and accept the stacked-PR review burden; (b) wait. Default is (b).

- [ ] **Step 2: Confirm v0.9.0 features are importable**

```bash
python -c "from ks_gen.verify.reconcile import VerifyReport; assert 'tailoring_drift' in {f.name for f in __import__('dataclasses').fields(VerifyReport)}; print('v0.9.0 present')"
```

Expected: `v0.9.0 present`. If `AssertionError`, you're branching too early; stop.

- [ ] **Step 3: Create and switch to feature branch**

```bash
git switch -c impl/v0.10.0-verify-capture-baseline
git branch --show-current
# expected: impl/v0.10.0-verify-capture-baseline
git status --short
# expected: only .claude/ and .scratch/ untracked
```

- [ ] **Step 4: Confirm CI parity baseline is green**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green. Note the test count — it's the post-v0.9.0 baseline (should be 502 or higher). Subsequent task headings cite test counts assuming **502 baseline**; if your baseline is different, adjust the deltas (each new test you add increments by one).

---

### Task 1: Add `BaselineReport` dataclass + `baseline` field on `VerifyReport`

**Files:**
- Create: `src/ks_gen/verify/baseline.py` (data classes only at this step)
- Modify: `src/ks_gen/verify/reconcile.py` (add import + field)
- Test: `tests/test_verify_baseline.py` (new, shape test)
- Test: `tests/test_verify_reconcile.py` (add field-default test)

This task lands the dataclasses so subsequent tasks have stable shapes. No parse/orphan logic yet.

- [ ] **Step 1: Write the failing shape test**

Create `tests/test_verify_baseline.py`:

```python
from __future__ import annotations

from ks_gen.verify.baseline import BaselineReport, ReadBaseline


def test_baseline_report_shape() -> None:
    report = BaselineReport(
        path="./baseline.arf.xml",
        captured_utc="2026-06-05T09:30:00Z",
        orphans=("rule_x", "rule_y"),
    )
    assert report.path == "./baseline.arf.xml"
    assert report.captured_utc == "2026-06-05T09:30:00Z"
    assert report.orphans == ("rule_x", "rule_y")


def test_read_baseline_shape() -> None:
    from ks_gen.verify.arf import RuleResult

    rb = ReadBaseline(
        results={"rule_a": RuleResult(rule_id="rule_a", result="pass")},
        captured_utc=None,
        path=__import__("pathlib").Path("./b.arf.xml"),
    )
    assert "rule_a" in rb.results
    assert rb.captured_utc is None
```

Append to `tests/test_verify_reconcile.py`:

```python
def test_verify_report_baseline_defaults_to_none() -> None:
    from ks_gen.verify.reconcile import VerifyReport

    report = VerifyReport(
        host="h",
        user="u",
        timestamp_utc="2026-06-09T00:00:00Z",
        rows=(),
        install_baseline_available=True,
    )
    assert report.baseline is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_verify_baseline.py tests/test_verify_reconcile.py -v -k baseline
```

Expected: 3 tests FAIL — `ModuleNotFoundError: ks_gen.verify.baseline` and `baseline` field missing on `VerifyReport`.

- [ ] **Step 3: Create the baseline module with the two dataclasses**

Create `src/ks_gen/verify/baseline.py`:

```python
"""Workstation-captured baseline ARF — load, orphan-detect, attach to VerifyReport.

Pure file/parse logic — no SSH, no transport. `read_baseline` loads a
captured ARF; `orphan_rule_ids` computes the rules-in-baseline-but-not-
current set that signals SSG-upgrade staleness.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ks_gen.verify.arf import RuleResult


@dataclass(frozen=True)
class ReadBaseline:
    """A captured ARF loaded from disk.

    `results` is the parsed `{rule_id: RuleResult}`; `captured_utc` is the
    ARF's `<TestResult start-time="...">` attribute, or None if absent;
    `path` is where it was loaded from (kept for reports).
    """

    results: dict[str, RuleResult]
    captured_utc: str | None
    path: Path


@dataclass(frozen=True)
class BaselineReport:
    """Reportable summary of which baseline drove this verify run.

    Attached to `VerifyReport.baseline` when `--baseline` was used.
    `path` is the operator-supplied string (so it survives JSON
    serialization without Path-conversion concerns).
    """

    path: str
    captured_utc: str | None
    orphans: tuple[str, ...]
```

- [ ] **Step 4: Add the field to `VerifyReport`**

Edit `src/ks_gen/verify/reconcile.py`. Add the import at the top (alongside `from ks_gen.verify.tailoring_drift import TailoringDriftReport`) and the field on `VerifyReport`. The new top section becomes:

```python
from ks_gen.verify.arf import RuleResult
from ks_gen.verify.baseline import BaselineReport
from ks_gen.verify.tailoring_drift import TailoringDriftReport
```

And the `VerifyReport` dataclass becomes:

```python
@dataclass(frozen=True)
class VerifyReport:
    host: str
    user: str
    timestamp_utc: str
    rows: tuple[VerifyRow, ...]
    install_baseline_available: bool
    tailoring_drift: TailoringDriftReport | None = None
    baseline: BaselineReport | None = None

    @property
    def is_clean(self) -> bool:
        return not any(r.category in ("new_fail", "regression") for r in self.rows)

    @property
    def has_tailoring_drift(self) -> bool:
        """True iff a drift check ran AND found at least one delta.

        `None` means the check didn't run (default). An empty
        `TailoringDriftReport` with matching profile_ids returns False.
        """
        d = self.tailoring_drift
        if d is None:
            return False
        return bool(d.added or d.removed or d.changed) or (
            d.profile_id_expected != d.profile_id_deployed
        )
```

NOTE: place `baseline` AFTER `tailoring_drift` so dataclass ordering rules (non-defaulted before defaulted) aren't violated and so the field-order in the JSON output matches what the rest of the codebase reads.

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_verify_baseline.py tests/test_verify_reconcile.py -v -k baseline
```

Expected: 3 PASS.

- [ ] **Step 6: Confirm existing reconcile / report / run tests still pass**

```bash
pytest tests/test_verify_reconcile.py tests/test_verify_report.py tests/test_verify_run.py -q
```

Expected: all green — the default-None field doesn't break existing constructors.

- [ ] **Step 7: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 505 passed (baseline 502 + 3 new).

- [ ] **Step 8: Commit**

```bash
git add src/ks_gen/verify/baseline.py src/ks_gen/verify/reconcile.py tests/test_verify_baseline.py tests/test_verify_reconcile.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(verify): BaselineReport + ReadBaseline dataclasses, baseline field on VerifyReport"
```

---

### Task 2: `read_baseline` — TDD

**Files:**
- Modify: `src/ks_gen/verify/baseline.py` (add function)
- Modify: `tests/test_verify_baseline.py` (add tests)

`read_baseline` loads a file, parses it through `parse_arf` for results, and does its own minimal walk for the `<TestResult start-time="...">` attribute. Failures map to existing error classes — no new error types.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_verify_baseline.py`. Add `read_baseline` to the existing import block at the top of the file (don't add mid-file imports):

```python
from pathlib import Path

import pytest

from ks_gen.loader import ConfigError, ExitCode
from ks_gen.verify.baseline import read_baseline
from ks_gen.verify.errors import ArfMissingError, ArfParseError


def _arf_with_start_time(start_time: str | None = "2026-06-05T09:30:00Z") -> str:
    """Build a minimal but valid ARF with optional start-time attribute."""
    attr = f' start-time="{start_time}"' if start_time is not None else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<arf:asset-report-collection xmlns:arf="http://scap.nist.gov/schema/asset-reporting-format/1.1">'
        "<arf:reports><arf:report id=\"r1\"><arf:content>"
        f'<TestResult xmlns="http://checklists.nist.gov/xccdf/1.2" id="xccdf_org.test_TR"{attr}>'
        '<rule-result idref="xccdf_org.ssgproject.content_rule_rule_a">'
        "<result>pass</result>"
        "</rule-result>"
        "</TestResult>"
        "</arf:content></arf:report></arf:reports>"
        "</arf:asset-report-collection>"
    )


def test_read_baseline_happy_path(tmp_path: Path) -> None:
    arf = tmp_path / "b.arf.xml"
    arf.write_text(_arf_with_start_time(), encoding="utf-8")

    result = read_baseline(arf)

    assert result.path == arf
    assert result.captured_utc == "2026-06-05T09:30:00Z"
    assert "xccdf_org.ssgproject.content_rule_rule_a" in result.results
    assert result.results["xccdf_org.ssgproject.content_rule_rule_a"].result == "pass"


def test_read_baseline_no_start_time_returns_none(tmp_path: Path) -> None:
    arf = tmp_path / "b.arf.xml"
    arf.write_text(_arf_with_start_time(start_time=None), encoding="utf-8")

    result = read_baseline(arf)

    assert result.captured_utc is None


def test_read_baseline_missing_file_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as exc_info:
        read_baseline(tmp_path / "does-not-exist.arf.xml")
    assert exc_info.value.exit_code == ExitCode.USAGE


def test_read_baseline_empty_file_raises_arf_missing(tmp_path: Path) -> None:
    arf = tmp_path / "empty.arf.xml"
    arf.write_text("", encoding="utf-8")

    with pytest.raises(ArfMissingError, match="empty"):
        read_baseline(arf)


def test_read_baseline_garbage_raises_arf_parse_error(tmp_path: Path) -> None:
    arf = tmp_path / "garbage.arf.xml"
    arf.write_text("<not-xml", encoding="utf-8")

    with pytest.raises(ArfParseError, match="well-formed"):
        read_baseline(arf)


def test_read_baseline_no_test_result_raises_arf_parse_error(tmp_path: Path) -> None:
    arf = tmp_path / "no-tr.arf.xml"
    arf.write_text(
        '<?xml version="1.0"?><root xmlns="http://example.com"><other/></root>',
        encoding="utf-8",
    )

    with pytest.raises(ArfParseError, match="TestResult"):
        read_baseline(arf)


def test_read_baseline_directory_raises_config_error(tmp_path: Path) -> None:
    """A directory at the path is a USAGE error, not a parse error."""
    with pytest.raises(ConfigError) as exc_info:
        read_baseline(tmp_path)
    assert exc_info.value.exit_code == ExitCode.USAGE
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_verify_baseline.py -v
```

Expected: 7 tests FAIL with `ImportError: cannot import name 'read_baseline'`.

- [ ] **Step 3: Implement `read_baseline`**

Append to `src/ks_gen/verify/baseline.py`. Add `import xml.etree.ElementTree as ET` to the top of the file alongside existing imports. Then add:

```python
import xml.etree.ElementTree as ET

from ks_gen.loader import ConfigError, ExitCode
from ks_gen.verify.arf import parse_arf
from ks_gen.verify.errors import ArfMissingError


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _extract_start_time(text: str) -> str | None:
    """Find the first <TestResult> element and return its start-time attribute.

    Returns None if no TestResult exists or the attribute is absent.
    `read_baseline` calls `parse_arf` separately for the rule results, so this
    helper only walks for the timestamp.
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    for elem in root.iter():
        if _localname(elem.tag) == "TestResult":
            return elem.get("start-time")
    return None


def read_baseline(path: Path) -> ReadBaseline:
    """Read and parse a captured baseline ARF from disk.

    Raises:
        ConfigError(USAGE): path missing, unreadable, or not a regular file.
        ArfMissingError: file exists but is 0 bytes.
        ArfParseError: malformed XML or no <TestResult>.
    """
    if not path.exists():
        raise ConfigError(f"--baseline path does not exist: {path}", ExitCode.USAGE)
    if not path.is_file():
        raise ConfigError(f"--baseline path is not a regular file: {path}", ExitCode.USAGE)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"--baseline path unreadable: {path}: {e}", ExitCode.USAGE) from e
    if not text:
        raise ArfMissingError(f"baseline file is empty: {path}")

    results = parse_arf(text)   # raises ArfParseError on malformed / no-TestResult
    captured_utc = _extract_start_time(text)
    return ReadBaseline(results=results, captured_utc=captured_utc, path=path)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_verify_baseline.py -v
```

Expected: 9 PASS (2 shape tests from Task 1 + 7 new).

- [ ] **Step 5: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 512 passed (505 + 7 new).

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/verify/baseline.py tests/test_verify_baseline.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(verify): read_baseline — load captured ARF with start-time extraction"
```

---

### Task 3: `orphan_rule_ids` — TDD

**Files:**
- Modify: `src/ks_gen/verify/baseline.py` (add function)
- Modify: `tests/test_verify_baseline.py` (add tests)

Pure set-difference, sorted, deduped. Surfaces the SSG-upgrade-staleness signal.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_verify_baseline.py` (add `orphan_rule_ids` to the existing import block at the top — don't add mid-file imports):

```python
from ks_gen.verify.arf import RuleResult
from ks_gen.verify.baseline import orphan_rule_ids


def _rr(rule_id: str, result: str = "pass") -> RuleResult:
    return RuleResult(rule_id=rule_id, result=result)  # type: ignore[arg-type]


def test_orphan_rule_ids_baseline_subset_of_current_returns_empty() -> None:
    baseline = {"r1": _rr("r1"), "r2": _rr("r2")}
    current = {"r1": _rr("r1"), "r2": _rr("r2"), "r3": _rr("r3")}
    assert orphan_rule_ids(baseline, current) == ()


def test_orphan_rule_ids_baseline_has_extras_returns_those() -> None:
    baseline = {"r1": _rr("r1"), "r2": _rr("r2"), "r_stale": _rr("r_stale")}
    current = {"r1": _rr("r1"), "r2": _rr("r2")}
    assert orphan_rule_ids(baseline, current) == ("r_stale",)


def test_orphan_rule_ids_sorted_alphabetically() -> None:
    baseline = {"r_z": _rr("r_z"), "r_a": _rr("r_a"), "r_m": _rr("r_m")}
    current: dict[str, RuleResult] = {}
    assert orphan_rule_ids(baseline, current) == ("r_a", "r_m", "r_z")


def test_orphan_rule_ids_empty_inputs_returns_empty() -> None:
    assert orphan_rule_ids({}, {}) == ()


def test_orphan_rule_ids_empty_baseline_returns_empty() -> None:
    current = {"r1": _rr("r1")}
    assert orphan_rule_ids({}, current) == ()


def test_orphan_rule_ids_empty_current_returns_all_baseline() -> None:
    baseline = {"r1": _rr("r1"), "r2": _rr("r2")}
    assert orphan_rule_ids(baseline, {}) == ("r1", "r2")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_verify_baseline.py -v -k orphan
```

Expected: 6 tests FAIL with `ImportError: cannot import name 'orphan_rule_ids'`.

- [ ] **Step 3: Implement `orphan_rule_ids`**

Append to `src/ks_gen/verify/baseline.py`:

```python
def orphan_rule_ids(
    baseline_results: dict[str, RuleResult],
    current_results: dict[str, RuleResult],
) -> tuple[str, ...]:
    """rule_ids present in baseline but absent from current, sorted.

    The 'stale baseline' signal — typically caused by an SSG upgrade
    between capture and verify. Returns a sorted tuple for stable
    rendering and JSON output.
    """
    return tuple(sorted(set(baseline_results) - set(current_results)))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_verify_baseline.py -v -k orphan
```

Expected: 6 PASS.

- [ ] **Step 5: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 518 passed (512 + 6 new).

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/verify/baseline.py tests/test_verify_baseline.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(verify): orphan_rule_ids — set-difference for stale-baseline detection"
```

---

### Task 4: `run_verify` integration — `baseline_path` and `capture_to` params

**Note on the spec's `capture_current_arf` helper.** The spec mentions a
`capture_current_arf` helper in `verify/remote.py` as a readability aid.
During plan review the implementation revealed the helper has no caller:
capture mode runs a normal verify (current + install ARFs both needed
for the in-band report) and writes `arfs.current_text` from the
existing `collect_arfs` output. Adding the helper would ship dead code.
This plan elects to NOT implement the helper; revisit if a future
follow-up genuinely needs a no-install-pull capture path.

**Files:**
- Modify: `src/ks_gen/verify/__init__.py` (extend `run_verify`)
- Modify: `tests/test_verify_run.py` (add tests)

`baseline_path` triggers the load-baseline-first path; `capture_to` triggers the write-current-after path. Mutually exclusive — `ConfigError(USAGE)` if both set.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_verify_run.py`:

```python
def test_run_verify_capture_to_writes_current_arf(tmp_path: Path) -> None:
    """When capture_to is set, the current ARF is written to that path."""
    from ks_gen.verify import run_verify
    from ks_gen.verify.remote import CollectedArfs

    current = (FIXTURES / "arf-clean.xml").read_text(encoding="utf-8")
    install = (FIXTURES / "arf-install-baseline.xml").read_text(encoding="utf-8")
    out = tmp_path / "captured.arf.xml"

    with patch(
        "ks_gen.verify.collect_arfs",
        return_value=CollectedArfs(current_text=current, install_text=install),
    ):
        report = run_verify(
            cfg=_cfg(),
            host="h",
            user="ops",
            workdir=tmp_path,
            capture_to=out,
            ssh_extra_opts=[],
            timeout=600,
        )

    assert out.exists()
    assert out.read_text(encoding="utf-8") == current
    assert report.baseline is None  # capture mode doesn't populate baseline


def test_run_verify_baseline_path_uses_file_instead_of_install(tmp_path: Path) -> None:
    """When baseline_path is set, the captured file replaces install ARF and
    collect_arfs is called with no_drift=True."""
    from ks_gen.verify import run_verify
    from ks_gen.verify.remote import CollectedArfs

    current = (FIXTURES / "arf-mixed.xml").read_text(encoding="utf-8")
    baseline_arf = (FIXTURES / "arf-install-baseline.xml").read_text(encoding="utf-8")
    baseline_path = tmp_path / "baseline.arf.xml"
    baseline_path.write_text(baseline_arf, encoding="utf-8")

    captured_kwargs: dict[str, object] = {}

    def fake_collect(**kwargs: object) -> CollectedArfs:
        captured_kwargs.update(kwargs)
        return CollectedArfs(current_text=current, install_text=None)

    with patch("ks_gen.verify.collect_arfs", side_effect=fake_collect):
        report = run_verify(
            cfg=_cfg(),
            host="h",
            user="ops",
            workdir=tmp_path,
            baseline_path=baseline_path,
            ssh_extra_opts=[],
            timeout=600,
        )

    assert captured_kwargs["no_drift"] is True
    assert report.baseline is not None
    assert report.baseline.path == str(baseline_path)
    # rule_e was pass in install baseline, fail in mixed → regression
    by_id = {r.rule_id: r for r in report.rows}
    assert by_id["xccdf_org.ssgproject.content_rule_rule_e"].category == "regression"


def test_run_verify_baseline_path_populates_orphans(tmp_path: Path) -> None:
    """Stale baseline: rules in baseline absent from current become orphans."""
    from ks_gen.verify import run_verify
    from ks_gen.verify.remote import CollectedArfs

    # Build a current ARF with only rule_a; baseline has rule_a + rule_stale.
    current_xml = (
        '<?xml version="1.0"?>'
        '<TestResult xmlns="http://checklists.nist.gov/xccdf/1.2">'
        '<rule-result idref="xccdf_org.ssgproject.content_rule_rule_a">'
        "<result>pass</result>"
        "</rule-result>"
        "</TestResult>"
    )
    baseline_xml = (
        '<?xml version="1.0"?>'
        '<TestResult xmlns="http://checklists.nist.gov/xccdf/1.2">'
        '<rule-result idref="xccdf_org.ssgproject.content_rule_rule_a">'
        "<result>pass</result>"
        "</rule-result>"
        '<rule-result idref="xccdf_org.ssgproject.content_rule_rule_stale">'
        "<result>pass</result>"
        "</rule-result>"
        "</TestResult>"
    )
    baseline_path = tmp_path / "stale.arf.xml"
    baseline_path.write_text(baseline_xml, encoding="utf-8")

    with patch(
        "ks_gen.verify.collect_arfs",
        return_value=CollectedArfs(current_text=current_xml, install_text=None),
    ):
        report = run_verify(
            cfg=_cfg(),
            host="h",
            user="ops",
            workdir=tmp_path,
            baseline_path=baseline_path,
            ssh_extra_opts=[],
            timeout=600,
        )

    assert report.baseline is not None
    assert report.baseline.orphans == (
        "xccdf_org.ssgproject.content_rule_rule_stale",
    )


def test_run_verify_baseline_path_and_capture_to_both_set_raises(tmp_path: Path) -> None:
    """Library-layer mutual-exclusion check."""
    import pytest

    from ks_gen.loader import ConfigError, ExitCode
    from ks_gen.verify import run_verify

    baseline_path = tmp_path / "b.arf"
    capture_to = tmp_path / "c.arf"
    baseline_path.write_text("<TestResult/>", encoding="utf-8")

    with pytest.raises(ConfigError) as exc_info:
        run_verify(
            cfg=_cfg(),
            host="h",
            user="ops",
            workdir=tmp_path,
            baseline_path=baseline_path,
            capture_to=capture_to,
            ssh_extra_opts=[],
            timeout=600,
        )
    assert exc_info.value.exit_code == ExitCode.USAGE
    assert "mutually exclusive" in str(exc_info.value)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_verify_run.py -v -k baseline_path or capture_to
```

Expected: 4 FAIL — `baseline_path` / `capture_to` not parameters of `run_verify`.

- [ ] **Step 3: Extend `run_verify`**

Replace `src/ks_gen/verify/__init__.py` with this full content:

```python
"""Post-install host verification — re-run oscap, reconcile against host.yaml."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from ks_gen.config import HostConfig
from ks_gen.exceptions_report import expected_failure_rule_ids
from ks_gen.loader import ConfigError, ExitCode
from ks_gen.verify.arf import parse_arf
from ks_gen.verify.baseline import BaselineReport, orphan_rule_ids, read_baseline
from ks_gen.verify.errors import TailoringParseError
from ks_gen.verify.reconcile import VerifyReport, build_report
from ks_gen.verify.remote import collect_arfs, collect_deployed_tailoring
from ks_gen.verify.tailoring_drift import (
    compare_tailorings,
    parse_tailoring_xml,
)
from ks_gen.writer import render_tailoring


def run_verify(
    *,
    cfg: HostConfig,
    host: str,
    user: str,
    workdir: Path,
    no_drift: bool = False,
    check_tailoring: bool = False,
    baseline_path: Path | None = None,
    capture_to: Path | None = None,
    ssh_extra_opts: list[str] | None = None,
    timeout: int = 600,
) -> VerifyReport:
    """Re-run oscap on `host` and reconcile against `cfg`'s exception set.

    SSHs to `host` as `user` (requires passwordless sudo), runs
    `oscap xccdf eval` against the install-time `/root/tailoring.xml`, pulls
    both the fresh ARF and (unless `no_drift`) the install-time ARF at
    `/root/oscap-remediation-results.xml`, then categorizes each rule as
    clean / expected_fail / new_fail / regression / incomplete.

    When `check_tailoring` is True, also pulls `/root/tailoring.xml`, re-renders
    the expected tailoring from `cfg`, and attaches a `TailoringDriftReport` to
    the returned report. The pull happens before the compliance run so a
    missing tailoring fails fast.

    When `baseline_path` is set, the captured ARF at that path replaces the
    install-time ARF for reconcile (the install pull is skipped entirely),
    and a `BaselineReport` is attached to the returned report. When
    `capture_to` is set, the fresh-current ARF is written to that path
    AFTER the normal install-driven verify report is built. `baseline_path`
    and `capture_to` are mutually exclusive.

    Args:
        cfg: HostConfig loaded from the operator's host.yaml. The exception
            set is derived from cfg.exceptions + each applicable rule's
            exception_entry().
        host, user: SSH target.
        workdir: scratch directory for the pulled ARFs (existing or to be
            created by the caller). Files are not cleaned up by this
            function — the caller decides via `tempfile.TemporaryDirectory`
            or `--arf-out`/`--keep-arf`.
        no_drift: skip the install-time-ARF probe and pull entirely; the
            returned report has `install_baseline_available=False`. Forced
            True internally when `baseline_path` is set (the captured
            baseline already fills the install slot).
        check_tailoring: when True, pull `/root/tailoring.xml` from `host`,
            re-render the expected tailoring from `cfg`, and attach a
            `TailoringDriftReport` to the returned report. The pull happens
            before the compliance run so a missing tailoring fails fast.
        baseline_path: workstation path to a previously-captured ARF.
            Replaces the install-time ARF for drift reconcile. The
            `BaselineReport` attached to the returned report carries the
            path, captured timestamp, and orphan rule_ids.
        capture_to: workstation path to write the fresh-current ARF.
            The normal verify report still prints (install-driven reconcile);
            this just persists `arfs.current_text` for later use via
            `--baseline`.
        ssh_extra_opts: extra args appended to every `ssh`/`scp` invocation
            (e.g. `["-F", "/path/to/ssh_config"]`). `None` is normalized to
            an empty list.
        timeout: oscap-run timeout in seconds (default 600). The ssh and
            scp transport calls themselves are uncapped.

    Returns:
        A VerifyReport. Use `report.is_clean` for an at-a-glance pass/fail,
        `report.has_tailoring_drift` for intent-vs-deployed drift, and
        `report.baseline` to see which captured baseline drove the report
        (None means install ARF, or nothing, was used).

    Raises:
        ConfigError(USAGE): both `baseline_path` and `capture_to` set, or
            the baseline path is missing/unreadable/not a regular file.
        SudoPromptError: passwordless sudo unavailable for `user` on `host`.
        OscapInvocationError: tailoring missing, oscap exit not in {0, 2},
            or `cfg.meta.scap_content` not installed on `host`.
        ArfMissingError: oscap reported success but the ARF file is empty
            or absent, OR the captured baseline file is 0 bytes.
        ArfParseError: ARF text is not well-formed XML or has no TestResult.
        SshConnectError: ssh/scp transport failure.
        ToolMissingError: system `ssh` or `scp` not on PATH.
        TailoringParseError: malformed deployed or re-rendered tailoring XML
            (only when `check_tailoring=True`). Message names the side.
    """
    if baseline_path is not None and capture_to is not None:
        raise ConfigError(
            "--baseline and --capture-baseline are mutually exclusive",
            ExitCode.USAGE,
        )

    extra_opts = ssh_extra_opts or []

    # Load baseline first (fail fast on missing/malformed before any SSH).
    baseline_loaded = read_baseline(baseline_path) if baseline_path is not None else None
    effective_no_drift = no_drift or baseline_loaded is not None

    tailoring_drift = None
    if check_tailoring:
        deployed_xml = collect_deployed_tailoring(
            host=host,
            user=user,
            workdir=workdir,
            ssh_extra_opts=extra_opts,
        )
        expected_xml = render_tailoring(cfg)
        try:
            parsed_deployed = parse_tailoring_xml(deployed_xml)
        except TailoringParseError as e:
            raise TailoringParseError(
                f"failed to parse deployed tailoring at /root/tailoring.xml: {e}"
            ) from e
        try:
            parsed_expected = parse_tailoring_xml(expected_xml)
        except TailoringParseError as e:
            raise TailoringParseError(
                f"failed to parse re-rendered tailoring (ks-gen renderer bug?): {e}"
            ) from e
        tailoring_drift = compare_tailorings(parsed_expected, parsed_deployed)

    expected = expected_failure_rule_ids(cfg)
    arfs = collect_arfs(
        cfg=cfg,
        host=host,
        user=user,
        workdir=workdir,
        no_drift=effective_no_drift,
        ssh_extra_opts=extra_opts,
        timeout=timeout,
    )
    current = parse_arf(arfs.current_text)

    # `install` slot: prefer the loaded baseline; else fall back to the
    # install ARF (when present). `install_baseline_available` stays True
    # when either source drives reconcile.
    if baseline_loaded is not None:
        install: dict[str, object] | None = baseline_loaded.results
        install_available = True
    elif arfs.install_text is not None:
        install = parse_arf(arfs.install_text)
        install_available = True
    else:
        install = None
        install_available = False

    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = build_report(
        current=current,
        install=install,   # type: ignore[arg-type]
        expected_failures=expected,
        host=host,
        user=user,
        timestamp_utc=timestamp,
    )
    # Note: build_report's signature uses `install_baseline_available =
    # install is not None`. That keeps the field semantically aligned for
    # both install-ARF and captured-baseline cases.
    _ = install_available  # held for future use; build_report already computes it

    if tailoring_drift is not None:
        report = replace(report, tailoring_drift=tailoring_drift)

    if baseline_loaded is not None:
        baseline_report = BaselineReport(
            path=str(baseline_path),
            captured_utc=baseline_loaded.captured_utc,
            orphans=orphan_rule_ids(baseline_loaded.results, current),
        )
        report = replace(report, baseline=baseline_report)

    if capture_to is not None:
        capture_to.write_text(arfs.current_text, encoding="utf-8", newline="\n")

    return report


__all__ = ["VerifyReport", "run_verify"]
```

NOTE: the `install` annotation as `dict[str, object] | None` is a workaround for type-narrowing through the two-branch assignment. `build_report` expects `dict[str, RuleResult] | None`; the type ignore at the call site documents the unsafe narrowing. If mypy doesn't accept the workaround, replace with a `cast(dict[str, RuleResult] | None, install)` at the call site.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_verify_run.py -v
```

Expected: all PASS (existing + 4 new).

- [ ] **Step 5: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 522 passed (518 + 4 new).

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/verify/__init__.py tests/test_verify_run.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(verify): run_verify gains baseline_path + capture_to params"
```

---

### Task 5: `render_table` and `render_json` surface the baseline

**Files:**
- Modify: `src/ks_gen/verify/report.py`
- Modify: `tests/test_verify_report.py` (add tests + syrupy snapshots)

Table gets a `baseline:` header line and (when orphans) a `NOTE:` footer line. JSON gets a top-level `baseline` block. Backward-compat: absent when `report.baseline is None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_verify_report.py`:

```python
def test_render_table_includes_baseline_header_when_present(snapshot) -> None:
    from ks_gen.verify.baseline import BaselineReport
    from ks_gen.verify.reconcile import VerifyReport, VerifyRow
    from ks_gen.verify.report import render_table

    baseline = BaselineReport(
        path="./baseline.arf.xml",
        captured_utc="2026-06-05T09:30:00Z",
        orphans=("xccdf_org.ssgproject.content_rule_rule_stale",),
    )
    report = VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(VerifyRow("rule_b", "fail", "pass", False, "regression"),),
        install_baseline_available=True,
        baseline=baseline,
    )
    out = render_table(report)
    assert out == snapshot


def test_render_table_baseline_header_without_timestamp(snapshot) -> None:
    """When captured_utc is None, the parenthetical reads (timestamp unknown)."""
    from ks_gen.verify.baseline import BaselineReport
    from ks_gen.verify.reconcile import VerifyReport
    from ks_gen.verify.report import render_table

    baseline = BaselineReport(
        path="./baseline.arf.xml",
        captured_utc=None,
        orphans=(),
    )
    report = VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(),
        install_baseline_available=True,
        baseline=baseline,
    )
    out = render_table(report)
    assert out == snapshot


def test_render_table_no_baseline_section_when_field_none() -> None:
    from ks_gen.verify.reconcile import VerifyReport
    from ks_gen.verify.report import render_table

    report = VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(),
        install_baseline_available=True,
    )
    out = render_table(report)
    assert "baseline:" not in out
    assert "may be stale" not in out


def test_render_json_includes_baseline_when_present(snapshot) -> None:
    from ks_gen.verify.baseline import BaselineReport
    from ks_gen.verify.reconcile import VerifyReport
    from ks_gen.verify.report import render_json

    baseline = BaselineReport(
        path="./baseline.arf.xml",
        captured_utc="2026-06-05T09:30:00Z",
        orphans=("xccdf_org.ssgproject.content_rule_rule_stale",),
    )
    report = VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(),
        install_baseline_available=True,
        baseline=baseline,
    )
    assert render_json(report) == snapshot


def test_render_json_no_baseline_key_when_field_is_none() -> None:
    import json as _json

    from ks_gen.verify.reconcile import VerifyReport
    from ks_gen.verify.report import render_json

    report = VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(),
        install_baseline_available=True,
    )
    payload = _json.loads(render_json(report))
    assert "baseline" not in payload
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_verify_report.py -v -k baseline
```

Expected: 5 FAIL — header line missing, JSON key missing, snapshots not yet recorded.

- [ ] **Step 3: Update `render_table` and `render_json`**

Edit `src/ks_gen/verify/report.py`. Two surgical changes:

(a) In `render_table`, after the `verify host=... user=... at=...` line and before the `install_baseline_available` NOTE, add the baseline header line when present. The relevant top of `render_table` becomes:

```python
    lines: list[str] = []
    lines.append(f"verify host={report.host} user={report.user} at={report.timestamp_utc}")
    if report.baseline is not None:
        ts = report.baseline.captured_utc or "timestamp unknown"
        prefix = "captured " if report.baseline.captured_utc else ""
        lines.append(f"  baseline: {report.baseline.path} ({prefix}{ts})")
    if not report.install_baseline_available:
        lines.append("  NOTE: drift comparison skipped — install-time ARF not present on host")
```

(b) Just before the existing `if report.tailoring_drift is not None:` block at the bottom of `render_table`, add a stale-baseline footer note when orphans are present. The relevant tail becomes:

```python
        base = "\n".join(lines) + "\n"

    if report.baseline is not None and report.baseline.orphans:
        n = len(report.baseline.orphans)
        plural = "rule" if n == 1 else "rules"
        base = (
            base
            + f"  NOTE: {n} {plural} in baseline not present in current ARF "
            "— baseline may be stale (SSG upgraded?)\n"
        )

    if report.tailoring_drift is not None:
        drift_section = render_drift_section(report.tailoring_drift)
        if drift_section:
            base = base + "\n" + drift_section
    ...
```

(c) In `render_json`, add the `baseline` block after the existing `tailoring_drift` block:

```python
    baseline = report.baseline
    if baseline is not None:
        payload["baseline"] = {
            "path": baseline.path,
            "captured_utc": baseline.captured_utc,
            "orphans": list(baseline.orphans),
        }
    return json.dumps(payload, indent=2)
```

NOTE: be careful with the existing structure of `render_table` — there are TWO different code paths (visible rows vs no visible rows) where `base` gets assembled. The orphan footer must go AFTER both paths converge on `base`. If you're not sure where the converge point is, re-read the existing function once and place the orphan-note block immediately AFTER the `if not visible: ... else: ...` block but BEFORE the `if report.tailoring_drift is not None:` block.

- [ ] **Step 4: Regenerate the new snapshots**

```bash
pytest tests/test_verify_report.py -k baseline --snapshot-update
```

- [ ] **Step 5: Re-run tests to verify they pass**

```bash
pytest tests/test_verify_report.py -v
```

Expected: all PASS — existing snapshots untouched, 3 new snapshots added.

- [ ] **Step 6: Inspect the new snapshots — confirm no existing snapshot modified**

```bash
git diff tests/__snapshots__/test_verify_report.ambr
```

Expected: only new `# name:` blocks appended (alphabetically positioned by syrupy); existing entries byte-for-byte unchanged. If the diff shows modifications to existing snapshots, STOP and investigate before committing.

- [ ] **Step 7: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 527 passed (522 + 5 new).

- [ ] **Step 8: Commit**

```bash
git add src/ks_gen/verify/report.py tests/test_verify_report.py tests/__snapshots__/test_verify_report.ambr
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(verify): render_table/render_json surface captured baseline + orphan note"
```

---

### Task 6: CLI `--capture-baseline` and `--baseline` flags

**Files:**
- Modify: `src/ks_gen/cli.py:174-310` (verify command)
- Modify: `tests/test_cli/test_verify.py` (add tests)

Two new flags. Mutual-exclusion check at the CLI layer (friendly error before `run_verify` is called). `run_verify`'s library-layer check is the safety net.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli/test_verify.py`:

```python
def test_verify_capture_baseline_threads_through(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    out = tmp_path / "captured.arf"
    runner = CliRunner()
    captured: dict[str, object] = {}

    def fake_run_verify(**kwargs: object) -> VerifyReport:
        captured.update(kwargs)
        return _clean_report()

    with (
        patch("ks_gen.cli.run_verify", side_effect=fake_run_verify),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(
            app,
            ["verify", "--host", "h1", "--config", str(cfg), "--capture-baseline", str(out)],
        )
    assert result.exit_code == 0, result.output
    assert captured["capture_to"] == out


def test_verify_baseline_threads_through(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    baseline = tmp_path / "baseline.arf"
    baseline.write_text("<TestResult/>", encoding="utf-8")
    runner = CliRunner()
    captured: dict[str, object] = {}

    def fake_run_verify(**kwargs: object) -> VerifyReport:
        captured.update(kwargs)
        return _clean_report()

    with (
        patch("ks_gen.cli.run_verify", side_effect=fake_run_verify),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(
            app,
            ["verify", "--host", "h1", "--config", str(cfg), "--baseline", str(baseline)],
        )
    assert result.exit_code == 0, result.output
    assert captured["baseline_path"] == baseline


def test_verify_baseline_and_capture_baseline_mutually_exclusive(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    baseline = tmp_path / "b.arf"
    capture = tmp_path / "c.arf"
    baseline.write_text("<TestResult/>", encoding="utf-8")
    runner = CliRunner()

    with patch("ks_gen.cli.check_tools"):
        result = runner.invoke(
            app,
            [
                "verify",
                "--host", "h1",
                "--config", str(cfg),
                "--baseline", str(baseline),
                "--capture-baseline", str(capture),
            ],
        )
    assert result.exit_code == 1, result.output  # USAGE
    assert "mutually exclusive" in result.output


def test_verify_baseline_missing_file_exit_usage(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    missing = tmp_path / "does-not-exist.arf"

    with (
        patch("ks_gen.cli.run_verify", side_effect=__import__("ks_gen.loader", fromlist=["ConfigError"]).ConfigError(
            f"--baseline path does not exist: {missing}",
            __import__("ks_gen.loader", fromlist=["ExitCode"]).ExitCode.USAGE,
        )),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(
            app,
            ["verify", "--host", "h1", "--config", str(cfg), "--baseline", str(missing)],
        )
    assert result.exit_code == 1, result.output  # USAGE
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_cli/test_verify.py -v -k "baseline or capture_baseline"
```

Expected: 4 FAIL — flags unknown, mutual exclusion not enforced.

- [ ] **Step 3: Add the flags and the mutual-exclusion check**

Edit `src/ks_gen/cli.py`. Three changes inside `verify_cmd`:

(a) Add two new `typer.Option` parameters. Insert them in the parameter list immediately after `check_tailoring`:

```python
    capture_baseline: Path | None = typer.Option(
        None,
        "--capture-baseline",
        help=(
            "Write the freshly-captured ARF to this path on the workstation. "
            "Use the saved file later via --baseline. Mutually exclusive with --baseline."
        ),
    ),
    baseline: Path | None = typer.Option(
        None,
        "--baseline",
        help=(
            "Use this workstation-side ARF as the drift baseline instead of the "
            "host's /root/oscap-remediation-results.xml. Skips the install-ARF "
            "pull. Mutually exclusive with --capture-baseline."
        ),
    ),
```

(b) After the existing `--format` check and the `--allow-regression`-without-`--apply` warning, add the mutual-exclusion check (BEFORE the `try: cfg = load_host_config(...)` block so it fires fast):

```python
    if baseline is not None and capture_baseline is not None:
        typer.echo(
            "ks-gen verify: --baseline and --capture-baseline are mutually exclusive",
            err=True,
        )
        raise typer.Exit(code=int(ExitCode.USAGE))
```

(c) Thread the two new params into the `run_verify` call inside `_do`. The call becomes:

```python
            report = run_verify(
                cfg=cfg,
                host=host,
                user=resolved_user,
                workdir=workdir,
                no_drift=no_drift,
                check_tailoring=check_tailoring,
                baseline_path=baseline,
                capture_to=capture_baseline,
                ssh_extra_opts=extra_opts,
                timeout=timeout,
            )
```

(d) Wrap the `run_verify` invocation to also catch `ConfigError` (the library-layer mutual-exclusion + missing-baseline-file errors). The existing exception handler in `_do` only catches `VerifyError`. Add a sibling handler:

```python
        try:
            report = run_verify(...)   # the call from (c)
        except ConfigError as e:
            typer.echo(f"ks-gen verify: {e}", err=True)
            raise typer.Exit(code=int(e.exit_code)) from None
        except VerifyError as e:
            ...                          # existing handler
```

NOTE: `ConfigError` is already imported at the top of `cli.py` (from the `gen` command flow). Confirm the import exists; if not, add `from ks_gen.loader import ConfigError`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_cli/test_verify.py -v
```

Expected: PASS (existing + 4 new).

- [ ] **Step 5: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 531 passed (527 + 4 new).

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/cli.py tests/test_cli/test_verify.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(cli): verify --capture-baseline + --baseline flags with mutual-exclusion check"
```

---

### Task 7: MANUAL.md §8.6 + README sentence

**Files:**
- Modify: `MANUAL.md` (add §8.6 subsection — peer to §8.5 `Detecting tailoring drift`)
- Modify: `README.md` (one sentence)

- [ ] **Step 1: Locate the §8.5 `Detecting tailoring drift` subsection in MANUAL.md**

```bash
grep -n "Detecting tailoring drift\|tailoring-drift\|check-tailoring" MANUAL.md | head -10
```

Identify the heading level used for the `Detecting tailoring drift` subsection (added in v0.9.0 PR #39). The new `Capturing and using a workstation baseline` subsection goes immediately after it, peer-level (same heading depth).

- [ ] **Step 2: Add the new MANUAL.md subsection**

Insert after the §8.5 subsection (match its heading level — likely `####`):

```markdown
#### Capturing and using a workstation baseline

`ks-gen verify --capture-baseline <path>` runs oscap on the host as
usual, then writes the resulting ARF to `<path>` on your workstation.
The normal verify report still prints — capture is a side effect of a
regular verify run, not a separate operation.

`ks-gen verify --baseline <path>` uses that captured file as the drift
baseline instead of the host's `/root/oscap-remediation-results.xml`.
The install ARF is not pulled at all when `--baseline` is set.

The two flags are mutually exclusive in a single invocation — capturing
and using a baseline are two operator intents on two different days.

**When to use this.** Two common scenarios:

1. **Post-install manual review.** You finish a kickstart install, SSH
   in, fix some failing rules by hand or accept others as exceptions
   in `host.yaml`. You want future verify runs to treat the reviewed
   state as ground truth, not the dirty install state. Capture the
   baseline after review:

   ```
   ks-gen verify --capture-baseline ./baseline.arf.xml \
       --host host.example.com --config host.yaml
   # ... review the report ...
   # From now on:
   ks-gen verify --baseline ./baseline.arf.xml \
       --host host.example.com --config host.yaml
   ```

2. **SSG upgrade staleness.** Months later, `scap-security-guide`
   upgrades and adds/removes rules. The install ARF on the host
   references rule IDs that no longer exist in the current SCAP
   content. Verify can't reliably distinguish "rule passed" from "rule
   no longer evaluated" against a stale install ARF — recapture against
   the new SSG to refresh.

**Stale-baseline warning.** When the captured baseline references rules
that don't exist in the current ARF (typically caused by an SSG upgrade
between capture and verify), the report shows:

```
  NOTE: 7 rules in baseline not present in current ARF — baseline may be stale (SSG upgraded?)
```

Doesn't change exit codes — pure information. The JSON output's
`baseline.orphans` array lists the affected rule IDs.

**File format.** Same XCCDF ARF that `oscap xccdf eval` produces —
verbatim. An operator can hand-produce one with stock `oscap` (without
ks-gen) and feed it in via `--baseline`. The capture flow simply
relocates what's already there.

**Doesn't replace `host.yaml` exceptions.** Captured baseline and
declared exceptions are orthogonal axes:
- `host.yaml` exceptions = "this failing rule is intentional; never
  surface it as a problem"
- Captured baseline = "the reconcile diff should be measured against
  THIS state, not against install state"

Use both together when appropriate.

**JSON output.** `verify --format json --baseline <path>` adds a
top-level `baseline` key with `path`, `captured_utc`, and `orphans`.
The key is omitted when `--baseline` isn't set.
```

NOTE: if the inline code block delimiter inside the MANUAL subsection conflicts with the surrounding markdown fence convention, use a four-backtick outer fence (consistent with the §8.5 subsection from v0.9.0).

- [ ] **Step 3: Add the README sentence**

In `README.md`, append to the verify blurb (after the v0.9.0 `--check-tailoring` sentence):

```markdown
Use `--capture-baseline <path>` and `--baseline <path>` to reconcile against an operator-captured ARF instead of the install-time ARF.
```

- [ ] **Step 4: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 531 passed (docs-only change shouldn't shift the count).

- [ ] **Step 5: Commit**

```bash
git add MANUAL.md README.md
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "docs: verify --capture-baseline / --baseline — MANUAL §8.6 + README sentence"
```

---

### Task 8: Final integration check + push

**Files:** (none — verification + branch push)

- [ ] **Step 1: Re-run the full CI parity chain from a clean slate**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 531 passed.

- [ ] **Step 2: Confirm commit history**

```bash
git log --oneline 24120e2..HEAD
```

Expected: 7 implementation commits (Tasks 1-7). If the count differs, investigate before pushing.

- [ ] **Step 3: Confirm signatures**

```bash
git log --format="%h %G? %s" 24120e2..HEAD
```

Expected: every line starts with the commit hash followed by `G`. No `N`.

- [ ] **Step 4: Push the branch**

```bash
git push -u origin impl/v0.10.0-verify-capture-baseline
```

Expected: branch pushed. If GitHub rejects with `GH007: Your push would publish a private email address`, STOP and tell the user — don't fall back to the noreply form silently.

- [ ] **Step 5: Open the PR**

```bash
gh pr create --title "feat(verify): --capture-baseline / --baseline (#11)" --body "$(cat <<'EOF'
## Summary

Closes #11. Opt-in `ks-gen verify --capture-baseline <path>` writes
the fresh-current ARF to a workstation file; `ks-gen verify --baseline
<path>` uses that file as the drift baseline instead of the host's
`/root/oscap-remediation-results.xml`. Mutually exclusive in a single
invocation.

Addresses two scenarios from the issue body:
- **Manual post-install review.** Operator can "freeze" a reviewed
  state as the baseline instead of accepting the dirty install state.
- **SSG upgrade staleness.** Recapture against new SSG when the
  install ARF references rules that no longer exist.

Reuses `parse_arf` and `categorize()` — the baseline simply fills the
slot previously held by the install ARF. Stale baselines surface
non-fatally as a footer note + JSON `baseline.orphans` array.

## Test plan

- [ ] Local CI parity green: `ruff check && ruff format --check && mypy && pytest -q` (531 passed)
- [ ] `verify --capture-baseline ./b.arf` against reachable host → writes `./b.arf` + prints normal report
- [ ] `verify --baseline ./b.arf` → uses captured baseline, skips install-ARF pull, exits per normal reconcile
- [ ] `verify --baseline ./b.arf --capture-baseline ./c.arf` → exit 1 (USAGE)
- [ ] `verify --baseline ./does-not-exist.arf` → exit 1 (USAGE) with friendly message
- [ ] `verify --format json --baseline ./b.arf` JSON has `baseline.path / captured_utc / orphans`; without `--baseline`, key is absent (backward-compatible)
- [ ] `verify --baseline ./b.arf --check-tailoring` composes — both report sections appear

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL returned. Capture for follow-up.

---

## Self-review

After all tasks complete, verify against the spec at
`docs/superpowers/specs/2026-06-09-verify-capture-baseline-design.md`:

- [ ] **Spec §Goals coverage:**
  - `--capture-baseline <path>` flag → Task 6 ✓ (CLI), Task 4 ✓ (`capture_to` param)
  - `--baseline <path>` flag → Task 6 ✓ (CLI), Task 4 ✓ (`baseline_path` param)
  - Mutual exclusion → Task 4 ✓ (library-layer), Task 6 ✓ (CLI-layer)
  - Reconcile semantics unchanged → Task 4 (`build_report(install=baseline.results, ...)`) ✓
  - Stale-baseline visibility → Task 3 (orphan_rule_ids), Task 5 (footer + JSON) ✓
  - Backward-compat (no flags = byte-identical to v0.9.0) → Task 4 default `None` ✓
- [ ] **Spec §Architecture coverage:**
  - `verify/baseline.py` with `read_baseline` + `orphan_rule_ids` → Tasks 2, 3 ✓
  - `capture_current_arf` helper in `verify/remote.py` → Intentionally elided (see note before Task 4) — dead code, no caller in the implementation
  - `VerifyReport.baseline` field + `BaselineReport` shape → Task 1 ✓
  - `run_verify` integration with mutually-exclusive params → Task 4 ✓
  - `render_table` + `render_json` extensions → Task 5 ✓
  - Two CLI flags + CLI-layer mutual-exclusion → Task 6 ✓
- [ ] **Spec §Edge cases — sanity check:**
  - Captured ARF has no start-time → Task 2 test ✓
  - Baseline references rules absent from current → Task 3 test + Task 4 test ✓
  - Capture against oscap-exit-2 host → handled by `collect_arfs` reuse (existing) ✓
  - `--capture-baseline <path>` parent dir missing → not explicitly tested; relies on `Path.write_text` raising OSError that surfaces. Worth noting; may want a follow-up test if review flags it.
  - Baseline file is directory → Task 2 test ✓
  - `--baseline` + `--capture-baseline` both set → Task 4 test + Task 6 test ✓
  - Baseline identical to current → reconcile clean, orphans=() — covered implicitly in Task 4 integration tests
  - 0-rule-result ARF → not explicitly tested but follows from `parse_arf` behavior; documented as "accepted" in spec
- [ ] **Spec §Documentation:**
  - MANUAL §8.6 → Task 7 ✓
  - README sentence → Task 7 ✓
- [ ] **Spec §Acceptance:**
  - All conditions covered by the test plan in Task 8's PR body ✓

No placeholders. No "TBD". Types referenced (`ReadBaseline`,
`BaselineReport`, `RuleResult`, `ConfigError`, `ArfMissingError`,
`ArfParseError`) are all defined in earlier tasks or the existing
codebase. Function names match across tasks (`read_baseline`,
`orphan_rule_ids`, `capture_current_arf`).
