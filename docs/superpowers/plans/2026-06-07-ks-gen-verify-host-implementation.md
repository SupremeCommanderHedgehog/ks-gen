# ks-gen verify --host Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `ks-gen verify --host <addr> --config host.yaml` — re-runs oscap on a deployed host via ssh + passwordless sudo, parses the fresh ARF + the install-time ARF persisted on the host, and reconciles failures against the expected-exception set derived from `host.yaml`.

**Architecture:** New `src/ks_gen/verify/` package with seven modules (one responsibility each: ssh subprocess wrappers, remote orchestration, ARF parsing, reconciliation, rendering, errors, package-level `run_verify`). Pure functions wherever possible. `verify_cmd` is added to `cli.py`; two new `ExitCode` members are added to `loader.py`. No new runtime dependencies — stdlib `subprocess`, `xml.etree.ElementTree`, `tempfile`, `shlex`, `shutil`.

**Tech Stack:** Python 3.11+, Typer (CLI), pydantic v2 (config), pytest, syrupy (snapshot tests), stdlib `xml.etree.ElementTree` (ARF parsing), system `ssh`/`scp` (transport).

**Spec:** `docs/superpowers/specs/2026-06-07-ks-gen-verify-host-design.md`
**Tracks:** [issue #5](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/5)
**Deferred (out of scope, tracked separately):** #10–#17

**Convention notes from the existing repo (read before starting):**
- Project CLAUDE.md mandates the full CI chain before pushing: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`. Run it after every task that touches code.
- Commits are conventional-commits style (`feat:`, `fix:`, `test:`, `docs:`, `style:`, `refactor:`, `chore:`, `ci:`), always signed with the user's GPG key. The harness's git config + user-level CLAUDE.md handle signing.
- Tests live flat under `tests/` (e.g., `tests/test_arf.py`) or in `tests/test_cli/` for CLI subcommand tests. Snapshots use syrupy under `tests/golden/__snapshots__/`. The verify tests follow the flat pattern: `tests/test_verify_arf.py`, `tests/test_verify_reconcile.py`, etc. — *not* a nested `tests/verify/` dir (the spec was approximate on this; the plan locks in the existing convention).
- The `minimal_cfg` fixture at `tests/conftest.py` is the standard `HostConfig` for tests.
- `src/` layout; imports are `from ks_gen.xxx`.
- mypy is `strict`; every new function gets type annotations.

---

## Task 1: Add ExitCode members + verify.errors module

**Files:**
- Modify: `src/ks_gen/loader.py` (extend `ExitCode` enum)
- Create: `src/ks_gen/verify/__init__.py` (empty for now)
- Create: `src/ks_gen/verify/errors.py`
- Create: `tests/test_verify_errors.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_verify_errors.py`:

```python
from __future__ import annotations

import pytest

from ks_gen.loader import ExitCode
from ks_gen.verify.errors import (
    ArfMissingError,
    ArfParseError,
    OscapInvocationError,
    SshConnectError,
    SudoPromptError,
    ToolMissingError,
    VerifyError,
)


def test_new_exit_codes_added() -> None:
    assert ExitCode.VERIFY_FAIL == 6
    assert ExitCode.TRANSPORT_FAIL == 7


@pytest.mark.parametrize(
    "cls,expected_exit",
    [
        (SshConnectError, ExitCode.TRANSPORT_FAIL),
        (SudoPromptError, ExitCode.TRANSPORT_FAIL),
        (OscapInvocationError, ExitCode.TRANSPORT_FAIL),
        (ArfMissingError, ExitCode.TRANSPORT_FAIL),
        (ArfParseError, ExitCode.TRANSPORT_FAIL),
        (ToolMissingError, ExitCode.TOOL_MISSING),
    ],
)
def test_error_maps_to_exit_code(cls: type[VerifyError], expected_exit: ExitCode) -> None:
    err = cls("a message")
    assert err.exit_code == expected_exit
    assert str(err) == "a message"


def test_verify_error_is_exception() -> None:
    with pytest.raises(VerifyError):
        raise SshConnectError("x")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_verify_errors.py -v`
Expected: collection error (`ModuleNotFoundError: No module named 'ks_gen.verify'`) or `AttributeError` for `ExitCode.VERIFY_FAIL`.

- [ ] **Step 3: Extend ExitCode**

Edit `src/ks_gen/loader.py`, replace the existing `ExitCode` block:

```python
class ExitCode(IntEnum):
    OK = 0
    USAGE = 1
    CONFIG_INVALID = 2
    RULE_CONFLICT = 3
    LINT_FAIL = 4
    TOOL_MISSING = 5
    VERIFY_FAIL = 6
    TRANSPORT_FAIL = 7
```

- [ ] **Step 4: Create the verify package**

Create `src/ks_gen/verify/__init__.py` with a single line:

```python
"""Post-install host verification — re-run oscap, reconcile against host.yaml."""
```

Create `src/ks_gen/verify/errors.py`:

```python
from __future__ import annotations

from ks_gen.loader import ExitCode


class VerifyError(Exception):
    """Base class for ks-gen verify failures. Subclasses set exit_code."""

    exit_code: ExitCode = ExitCode.TRANSPORT_FAIL


class SshConnectError(VerifyError):
    """ssh exit 255 — host unreachable, key rejected, kex failure."""


class SudoPromptError(VerifyError):
    """sudo -n returned 'a password is required' or non-zero before oscap ran."""


class OscapInvocationError(VerifyError):
    """oscap exit not in {0, 2}. Tailoring missing, profile typo, ssg unpopulated, OOM."""


class ArfMissingError(VerifyError):
    """oscap claimed success but the ARF file isn't on the host or pulled 0 bytes."""


class ArfParseError(VerifyError):
    """ARF is XML but doesn't look like SCAP ARF — wrong namespace, no TestResult."""


class ToolMissingError(VerifyError):
    """system ssh or scp not on PATH."""

    exit_code: ExitCode = ExitCode.TOOL_MISSING
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_verify_errors.py -v`
Expected: 8 passed.

- [ ] **Step 6: Run the full CI chain**

Run: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/ks_gen/loader.py src/ks_gen/verify/__init__.py src/ks_gen/verify/errors.py tests/test_verify_errors.py
git commit -S -m "feat(verify): exit codes + error hierarchy

Adds ExitCode.VERIFY_FAIL (6) and ExitCode.TRANSPORT_FAIL (7), and the
VerifyError hierarchy in src/ks_gen/verify/errors.py: SshConnectError,
SudoPromptError, OscapInvocationError, ArfMissingError, ArfParseError,
ToolMissingError. Foundation for ks-gen verify (#5)."
```

---

## Task 2: ARF parser (verify/arf.py)

**Files:**
- Create: `src/ks_gen/verify/arf.py`
- Create: `tests/test_verify_arf.py`
- Create: `tests/fixtures/arf-clean.xml`
- Create: `tests/fixtures/arf-mixed.xml`
- Create: `tests/fixtures/arf-incomplete.xml`

- [ ] **Step 1: Create fixture ARFs**

Create `tests/fixtures/arf-clean.xml` (3 rules, all pass):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<arf:asset-report-collection xmlns:arf="http://scap.nist.gov/schema/asset-reporting-format/1.1">
  <arf:reports>
    <arf:report id="r1">
      <arf:content>
        <TestResult xmlns="http://checklists.nist.gov/xccdf/1.2" id="xccdf_org.test_TR">
          <rule-result idref="xccdf_org.ssgproject.content_rule_rule_a">
            <result>pass</result>
          </rule-result>
          <rule-result idref="xccdf_org.ssgproject.content_rule_rule_b">
            <result>pass</result>
          </rule-result>
          <rule-result idref="xccdf_org.ssgproject.content_rule_rule_c">
            <result>pass</result>
          </rule-result>
        </TestResult>
      </arf:content>
    </arf:report>
  </arf:reports>
</arf:asset-report-collection>
```

Create `tests/fixtures/arf-mixed.xml` (3 pass, 2 fail, 1 error):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<arf:asset-report-collection xmlns:arf="http://scap.nist.gov/schema/asset-reporting-format/1.1">
  <arf:reports>
    <arf:report id="r1">
      <arf:content>
        <TestResult xmlns="http://checklists.nist.gov/xccdf/1.2" id="xccdf_org.test_TR">
          <rule-result idref="xccdf_org.ssgproject.content_rule_rule_a">
            <result>pass</result>
          </rule-result>
          <rule-result idref="xccdf_org.ssgproject.content_rule_rule_b">
            <result>pass</result>
          </rule-result>
          <rule-result idref="xccdf_org.ssgproject.content_rule_rule_c">
            <result>pass</result>
          </rule-result>
          <rule-result idref="xccdf_org.ssgproject.content_rule_rule_d">
            <result>fail</result>
          </rule-result>
          <rule-result idref="xccdf_org.ssgproject.content_rule_rule_e">
            <result>fail</result>
          </rule-result>
          <rule-result idref="xccdf_org.ssgproject.content_rule_rule_f">
            <result>error</result>
          </rule-result>
        </TestResult>
      </arf:content>
    </arf:report>
  </arf:reports>
</arf:asset-report-collection>
```

Create `tests/fixtures/arf-incomplete.xml` (well-formed XML, no TestResult):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<some-other-root>
  <body>not an ARF</body>
</some-other-root>
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_verify_arf.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from ks_gen.verify.arf import RuleResult, parse_arf
from ks_gen.verify.errors import ArfParseError

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_arf_returns_all_results_by_rule_id() -> None:
    results = parse_arf(_read("arf-clean.xml"))
    assert set(results) == {
        "xccdf_org.ssgproject.content_rule_rule_a",
        "xccdf_org.ssgproject.content_rule_rule_b",
        "xccdf_org.ssgproject.content_rule_rule_c",
    }
    assert all(isinstance(r, RuleResult) for r in results.values())
    assert all(r.result == "pass" for r in results.values())


def test_parse_arf_preserves_each_result_state() -> None:
    results = parse_arf(_read("arf-mixed.xml"))
    assert results["xccdf_org.ssgproject.content_rule_rule_a"].result == "pass"
    assert results["xccdf_org.ssgproject.content_rule_rule_d"].result == "fail"
    assert results["xccdf_org.ssgproject.content_rule_rule_f"].result == "error"


def test_parse_arf_raises_on_malformed_xml() -> None:
    with pytest.raises(ArfParseError, match="well-formed"):
        parse_arf("<not really xml")


def test_parse_arf_raises_on_xml_without_test_result() -> None:
    with pytest.raises(ArfParseError, match="TestResult"):
        parse_arf(_read("arf-incomplete.xml"))


def test_parse_arf_normalizes_unknown_result_state() -> None:
    weird = """\
<?xml version="1.0"?>
<TestResult xmlns="http://checklists.nist.gov/xccdf/1.2">
  <rule-result idref="xccdf_org.ssgproject.content_rule_rule_x">
    <result>weirdstate</result>
  </rule-result>
</TestResult>
"""
    results = parse_arf(weird)
    assert results["xccdf_org.ssgproject.content_rule_rule_x"].result == "unknown"


def test_parse_arf_skips_rule_results_without_idref() -> None:
    no_idref = """\
<?xml version="1.0"?>
<TestResult xmlns="http://checklists.nist.gov/xccdf/1.2">
  <rule-result>
    <result>pass</result>
  </rule-result>
  <rule-result idref="xccdf_org.ssgproject.content_rule_keep">
    <result>pass</result>
  </rule-result>
</TestResult>
"""
    results = parse_arf(no_idref)
    assert list(results) == ["xccdf_org.ssgproject.content_rule_keep"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_verify_arf.py -v`
Expected: `ModuleNotFoundError: No module named 'ks_gen.verify.arf'`.

- [ ] **Step 4: Implement arf.py**

Create `src/ks_gen/verify/arf.py`:

```python
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

from ks_gen.verify.errors import ArfParseError

VALID_RESULTS: frozenset[str] = frozenset(
    {
        "pass",
        "fail",
        "notapplicable",
        "notchecked",
        "notselected",
        "error",
        "unknown",
        "fixed",
        "informational",
    }
)


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    result: str


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_arf(text: str) -> dict[str, RuleResult]:
    """Parse an XCCDF ARF (or bare XCCDF results XML) into {rule_id: RuleResult}.

    Tolerant of namespace variation: matches elements by local-name. Result states
    outside the XCCDF vocabulary are normalized to 'unknown' rather than rejected.
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ArfParseError(f"ARF is not well-formed XML: {e}") from e

    results: dict[str, RuleResult] = {}
    found_test_result = _localname(root.tag) == "TestResult"

    for elem in root.iter():
        local = _localname(elem.tag)
        if local == "TestResult":
            found_test_result = True
        if local != "rule-result":
            continue
        rule_id = elem.get("idref")
        if not rule_id:
            continue
        for child in elem:
            if _localname(child.tag) != "result":
                continue
            state = (child.text or "").strip()
            if state not in VALID_RESULTS:
                state = "unknown"
            results[rule_id] = RuleResult(rule_id=rule_id, result=state)
            break

    if not found_test_result:
        raise ArfParseError(
            "XML has no TestResult element — not an XCCDF/ARF document"
        )

    return results
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_verify_arf.py -v`
Expected: 6 passed.

- [ ] **Step 6: Run the full CI chain**

Run: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/ks_gen/verify/arf.py tests/test_verify_arf.py tests/fixtures/arf-clean.xml tests/fixtures/arf-mixed.xml tests/fixtures/arf-incomplete.xml
git commit -S -m "feat(verify): ARF parser

parse_arf(text) -> {rule_id: RuleResult}. Stdlib ElementTree, namespace-
tolerant via local-name matching. Unknown result states normalize to
'unknown' rather than raising. Three fixture ARFs cover the test
matrix (clean / mixed / incomplete-XML)."
```

---

## Task 3: Reconciliation (verify/reconcile.py)

**Files:**
- Create: `src/ks_gen/verify/reconcile.py`
- Create: `tests/test_verify_reconcile.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_verify_reconcile.py`:

```python
from __future__ import annotations

import pytest

from ks_gen.verify.arf import RuleResult
from ks_gen.verify.reconcile import (
    VerifyReport,
    VerifyRow,
    build_report,
    categorize,
)


@pytest.mark.parametrize(
    "current,install,expected,want",
    [
        ("pass", "pass", False, "clean"),
        ("pass", "fail", False, "clean"),
        ("pass", None, False, "clean"),
        ("fixed", "fail", False, "clean"),
        ("notapplicable", "fail", False, "clean"),
        ("notselected", "fail", False, "clean"),
        ("informational", "fail", False, "clean"),
        ("fail", "pass", True, "expected_fail"),
        ("fail", "pass", False, "regression"),
        ("fail", "fixed", False, "regression"),
        ("fail", "notapplicable", False, "regression"),
        ("fail", "fail", False, "new_fail"),
        ("fail", None, False, "new_fail"),
        ("fail", "error", False, "new_fail"),
        ("error", "pass", False, "incomplete"),
        ("notchecked", "pass", False, "incomplete"),
        ("unknown", "pass", False, "incomplete"),
    ],
)
def test_categorize_matrix(
    current: str, install: str | None, expected: bool, want: str
) -> None:
    assert categorize(current, install, expected) == want


def test_build_report_groups_rules_into_categories() -> None:
    current = {
        "rule_a": RuleResult("rule_a", "pass"),
        "rule_b": RuleResult("rule_b", "fail"),
        "rule_c": RuleResult("rule_c", "fail"),
        "rule_d": RuleResult("rule_d", "fail"),
        "rule_e": RuleResult("rule_e", "error"),
    }
    install = {
        "rule_a": RuleResult("rule_a", "pass"),
        "rule_b": RuleResult("rule_b", "fail"),
        "rule_c": RuleResult("rule_c", "pass"),
        "rule_d": RuleResult("rule_d", "fail"),
        "rule_e": RuleResult("rule_e", "pass"),
    }
    expected_failures = {"rule_d"}
    report = build_report(
        current=current,
        install=install,
        expected_failures=expected_failures,
        host="h1",
        user="ops",
        timestamp_utc="2026-06-07T00:00:00Z",
    )
    by_id = {r.rule_id: r for r in report.rows}
    assert by_id["rule_a"].category == "clean"
    assert by_id["rule_b"].category == "new_fail"
    assert by_id["rule_c"].category == "regression"
    assert by_id["rule_d"].category == "expected_fail"
    assert by_id["rule_e"].category == "incomplete"
    assert report.install_baseline_available is True
    assert report.is_clean is False


def test_build_report_clean_when_no_actionable_failures() -> None:
    current = {"rule_a": RuleResult("rule_a", "pass")}
    report = build_report(
        current=current,
        install={"rule_a": RuleResult("rule_a", "pass")},
        expected_failures=set(),
        host="h1",
        user="ops",
        timestamp_utc="ts",
    )
    assert report.is_clean is True


def test_build_report_install_none_drops_install_column() -> None:
    current = {"rule_a": RuleResult("rule_a", "fail")}
    report = build_report(
        current=current,
        install=None,
        expected_failures=set(),
        host="h1",
        user="ops",
        timestamp_utc="ts",
    )
    assert report.install_baseline_available is False
    assert report.rows[0].install is None
    assert report.rows[0].category == "new_fail"


def test_build_report_rules_only_in_install_are_ignored() -> None:
    current = {"rule_a": RuleResult("rule_a", "pass")}
    install = {
        "rule_a": RuleResult("rule_a", "pass"),
        "rule_old": RuleResult("rule_old", "pass"),
    }
    report = build_report(
        current=current,
        install=install,
        expected_failures=set(),
        host="h1",
        user="ops",
        timestamp_utc="ts",
    )
    assert [r.rule_id for r in report.rows] == ["rule_a"]


def test_build_report_rows_are_sorted_by_rule_id() -> None:
    current = {
        "rule_z": RuleResult("rule_z", "pass"),
        "rule_a": RuleResult("rule_a", "pass"),
        "rule_m": RuleResult("rule_m", "pass"),
    }
    report = build_report(
        current=current,
        install=None,
        expected_failures=set(),
        host="h1",
        user="ops",
        timestamp_utc="ts",
    )
    assert [r.rule_id for r in report.rows] == ["rule_a", "rule_m", "rule_z"]


def test_verify_row_is_frozen() -> None:
    row = VerifyRow(
        rule_id="r",
        current="pass",
        install=None,
        expected=False,
        category="clean",
    )
    with pytest.raises(Exception):
        row.category = "new_fail"  # type: ignore[misc]


def test_verify_report_is_immutable_tuple_of_rows() -> None:
    report = VerifyReport(
        host="h",
        user="u",
        timestamp_utc="t",
        rows=(),
        install_baseline_available=False,
    )
    assert isinstance(report.rows, tuple)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_verify_reconcile.py -v`
Expected: `ModuleNotFoundError: No module named 'ks_gen.verify.reconcile'`.

- [ ] **Step 3: Implement reconcile.py**

Create `src/ks_gen/verify/reconcile.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ks_gen.verify.arf import RuleResult

Category = Literal["clean", "expected_fail", "new_fail", "regression", "incomplete"]

CLEAN_CURRENT_STATES: frozenset[str] = frozenset(
    {"pass", "fixed", "notapplicable", "notselected", "informational"}
)
INCOMPLETE_STATES: frozenset[str] = frozenset({"error", "notchecked", "unknown"})


def categorize(current: str, install: str | None, expected: bool) -> Category:
    """Single-rule reconciliation logic. See spec §7.3."""
    if current in CLEAN_CURRENT_STATES:
        return "clean"
    if current in INCOMPLETE_STATES:
        return "incomplete"
    # current is fail (or any other non-clean, non-incomplete state)
    if expected:
        return "expected_fail"
    if install is None or install in INCOMPLETE_STATES:
        return "new_fail"
    if install in CLEAN_CURRENT_STATES:
        return "regression"
    # install is fail
    return "new_fail"


@dataclass(frozen=True)
class VerifyRow:
    rule_id: str
    current: str
    install: str | None
    expected: bool
    category: Category


@dataclass(frozen=True)
class VerifyReport:
    host: str
    user: str
    timestamp_utc: str
    rows: tuple[VerifyRow, ...]
    install_baseline_available: bool

    @property
    def is_clean(self) -> bool:
        return not any(r.category in ("new_fail", "regression") for r in self.rows)


def build_report(
    *,
    current: dict[str, RuleResult],
    install: dict[str, RuleResult] | None,
    expected_failures: set[str],
    host: str,
    user: str,
    timestamp_utc: str,
) -> VerifyReport:
    rows: list[VerifyRow] = []
    for rule_id in sorted(current):
        cur_state = current[rule_id].result
        inst_state = install[rule_id].result if install and rule_id in install else None
        is_expected = rule_id in expected_failures
        rows.append(
            VerifyRow(
                rule_id=rule_id,
                current=cur_state,
                install=inst_state,
                expected=is_expected,
                category=categorize(cur_state, inst_state, is_expected),
            )
        )
    return VerifyReport(
        host=host,
        user=user,
        timestamp_utc=timestamp_utc,
        rows=tuple(rows),
        install_baseline_available=install is not None,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_verify_reconcile.py -v`
Expected: 22 passed (17 parametrized categorize cases + 5 other tests).

- [ ] **Step 5: Run the full CI chain**

Run: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/verify/reconcile.py tests/test_verify_reconcile.py
git commit -S -m "feat(verify): three-way reconciliation

categorize(current, install, expected) implements the table from spec
§7.3. build_report() composes per-rule categorizations into a frozen
VerifyReport with a sorted tuple of VerifyRow and an is_clean property
that's False iff any rule is new_fail or regression. Rules only in
install (removed from current eval) are ignored."
```

---

## Task 4: Report rendering (verify/report.py)

**Files:**
- Create: `src/ks_gen/verify/report.py`
- Create: `tests/test_verify_report.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_verify_report.py`:

```python
from __future__ import annotations

import json

from syrupy.assertion import SnapshotAssertion

from ks_gen.verify.reconcile import VerifyReport, VerifyRow
from ks_gen.verify.report import render_json, render_table


def _make_report(
    rows: tuple[VerifyRow, ...], baseline: bool = True
) -> VerifyReport:
    return VerifyReport(
        host="h1.example.com",
        user="opsadmin",
        timestamp_utc="2026-06-07T12:00:00Z",
        rows=rows,
        install_baseline_available=baseline,
    )


def test_render_table_clean_report(snapshot: SnapshotAssertion) -> None:
    report = _make_report(
        (VerifyRow("xccdf_org.ssgproject.content_rule_a", "pass", "pass", False, "clean"),)
    )
    assert render_table(report) == snapshot


def test_render_table_one_of_each_category(snapshot: SnapshotAssertion) -> None:
    report = _make_report(
        (
            VerifyRow("xccdf_org.ssgproject.content_rule_a", "pass", "pass", False, "clean"),
            VerifyRow("xccdf_org.ssgproject.content_rule_b", "fail", "fail", False, "new_fail"),
            VerifyRow("xccdf_org.ssgproject.content_rule_c", "fail", "pass", False, "regression"),
            VerifyRow("xccdf_org.ssgproject.content_rule_d", "fail", "pass", True, "expected_fail"),
            VerifyRow(
                "xccdf_org.ssgproject.content_rule_e", "error", "pass", False, "incomplete"
            ),
        )
    )
    assert render_table(report) == snapshot


def test_render_table_no_baseline_shows_banner(snapshot: SnapshotAssertion) -> None:
    report = _make_report(
        (VerifyRow("xccdf_org.ssgproject.content_rule_a", "fail", None, False, "new_fail"),),
        baseline=False,
    )
    assert render_table(report) == snapshot


def test_render_json_shape() -> None:
    report = _make_report(
        (
            VerifyRow("rule_a", "pass", "pass", False, "clean"),
            VerifyRow("rule_b", "fail", None, False, "new_fail"),
        )
    )
    out = render_json(report)
    payload = json.loads(out)
    assert payload["host"] == "h1.example.com"
    assert payload["user"] == "opsadmin"
    assert payload["timestamp_utc"] == "2026-06-07T12:00:00Z"
    assert payload["install_baseline_available"] is True
    assert payload["is_clean"] is False
    assert payload["summary"] == {
        "clean": 1,
        "expected_fail": 0,
        "new_fail": 1,
        "regression": 0,
        "incomplete": 0,
    }
    assert payload["rows"] == [
        {
            "rule_id": "rule_a",
            "current": "pass",
            "install": "pass",
            "expected": False,
            "category": "clean",
        },
        {
            "rule_id": "rule_b",
            "current": "fail",
            "install": None,
            "expected": False,
            "category": "new_fail",
        },
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_verify_report.py -v`
Expected: `ModuleNotFoundError: No module named 'ks_gen.verify.report'`.

- [ ] **Step 3: Implement report.py**

Create `src/ks_gen/verify/report.py`:

```python
from __future__ import annotations

import json
from collections import Counter

from ks_gen.verify.reconcile import VerifyReport


def _summary(report: VerifyReport) -> dict[str, int]:
    counts: Counter[str] = Counter(r.category for r in report.rows)
    return {
        "clean": counts.get("clean", 0),
        "expected_fail": counts.get("expected_fail", 0),
        "new_fail": counts.get("new_fail", 0),
        "regression": counts.get("regression", 0),
        "incomplete": counts.get("incomplete", 0),
    }


def render_table(report: VerifyReport) -> str:
    """Plain-text report. Omits `clean` rows by default to keep output focused."""
    lines: list[str] = []
    lines.append(f"verify host={report.host} user={report.user} at={report.timestamp_utc}")
    if not report.install_baseline_available:
        lines.append(
            "  NOTE: drift comparison skipped — install-time ARF not present on host"
        )
    summary = _summary(report)
    lines.append(
        "  summary: "
        + " ".join(f"{k}={v}" for k, v in summary.items())
        + (" — CLEAN" if report.is_clean else " — FAILURES")
    )

    visible = [r for r in report.rows if r.category != "clean"]
    if not visible:
        lines.append("  (no actionable rows)")
        return "\n".join(lines) + "\n"

    rule_w = max(len(r.rule_id) for r in visible)
    cat_w = max(len(r.category) for r in visible)
    lines.append("")
    lines.append(
        f"  {'CATEGORY':<{cat_w}}  {'CURRENT':<8}  {'INSTALL':<8}  EXP  RULE"
    )
    for r in visible:
        inst = r.install if r.install is not None else "-"
        exp = "yes" if r.expected else "no "
        lines.append(
            f"  {r.category:<{cat_w}}  {r.current:<8}  {inst:<8}  {exp}  {r.rule_id:<{rule_w}}"
        )
    return "\n".join(lines) + "\n"


def render_json(report: VerifyReport) -> str:
    payload = {
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
    return json.dumps(payload, indent=2)
```

- [ ] **Step 4: Run test to capture initial snapshots**

Run: `pytest tests/test_verify_report.py --snapshot-update -v`
Expected: 4 passed, 3 snapshots written.

- [ ] **Step 5: Confirm snapshot file contents look right**

Run: `pytest tests/test_verify_report.py -v`
Expected: 4 passed (replay).

Inspect `tests/__snapshots__/test_verify_report.ambr` (or wherever syrupy writes it for flat `tests/` layout) — confirm the table snapshots are readable and the no-baseline banner appears.

- [ ] **Step 6: Run the full CI chain**

Run: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/ks_gen/verify/report.py tests/test_verify_report.py tests/__snapshots__/test_verify_report.ambr
git commit -S -m "feat(verify): table + JSON renderers

render_table(): plain-text, omits clean rows, shows a no-baseline
banner when install_baseline_available is False. render_json(): full
payload including a per-category summary and the is_clean derived
field. Snapshots cover clean, mixed-category, and no-baseline cases."
```

---

## Task 5: SSH subprocess wrapper (verify/ssh.py)

**Files:**
- Create: `src/ks_gen/verify/ssh.py`
- Create: `tests/test_verify_ssh.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_verify_ssh.py`:

```python
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from ks_gen.verify.errors import SshConnectError, ToolMissingError
from ks_gen.verify.ssh import SshResult, check_tools, scp_pull, ssh_exec


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_check_tools_passes_when_ssh_and_scp_present() -> None:
    with patch("ks_gen.verify.ssh.shutil.which", side_effect=lambda t: f"/usr/bin/{t}"):
        check_tools()


def test_check_tools_raises_when_ssh_missing() -> None:
    def which(tool: str) -> str | None:
        return None if tool == "ssh" else f"/usr/bin/{tool}"

    with patch("ks_gen.verify.ssh.shutil.which", side_effect=which), pytest.raises(
        ToolMissingError, match="ssh"
    ):
        check_tools()


def test_ssh_exec_returns_result_on_zero_exit() -> None:
    with patch("ks_gen.verify.ssh.subprocess.run", return_value=_completed(0, "out", "")) as run:
        result = ssh_exec("host", "user", "ls /", extra_opts=["-o", "StrictHostKeyChecking=yes"])
    assert result == SshResult(stdout="out", stderr="", exit_code=0)
    args = run.call_args.args[0]
    assert args[0] == "ssh"
    assert "-o" in args and "BatchMode=yes" in args
    assert "StrictHostKeyChecking=yes" in args
    assert args[-2] == "user@host"
    assert args[-1] == "ls /"


def test_ssh_exec_exit_255_raises_ssh_connect_error() -> None:
    stderr = "ssh: connect to host h port 22: Connection refused\n"
    with patch(
        "ks_gen.verify.ssh.subprocess.run", return_value=_completed(255, "", stderr)
    ), pytest.raises(SshConnectError, match="Connection refused"):
        ssh_exec("host", "user", "ls /")


def test_ssh_exec_timeout_raises_ssh_connect_error() -> None:
    with patch(
        "ks_gen.verify.ssh.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["ssh"], timeout=1),
    ), pytest.raises(SshConnectError, match="timed out"):
        ssh_exec("host", "user", "ls /", timeout=1)


def test_ssh_exec_file_not_found_raises_tool_missing() -> None:
    with patch(
        "ks_gen.verify.ssh.subprocess.run", side_effect=FileNotFoundError()
    ), pytest.raises(ToolMissingError, match="ssh"):
        ssh_exec("host", "user", "ls /")


def test_ssh_exec_returns_nonzero_exit_without_raising() -> None:
    # nonzero != 255 (e.g. oscap exit 2) is the remote command's exit, not transport
    with patch("ks_gen.verify.ssh.subprocess.run", return_value=_completed(2, "", "rules failed")):
        result = ssh_exec("host", "user", "oscap ...")
    assert result.exit_code == 2


def test_scp_pull_invokes_scp_with_user_host_remote_target(tmp_path: Path) -> None:
    local = tmp_path / "out.xml"
    with patch("ks_gen.verify.ssh.subprocess.run", return_value=_completed(0)) as run:
        scp_pull("host", "user", "/root/file.xml", local, extra_opts=["-q"])
    args = run.call_args.args[0]
    assert args[0] == "scp"
    assert "-q" in args
    assert "user@host:/root/file.xml" in args
    assert str(local) in args


def test_scp_pull_nonzero_exit_raises_ssh_connect_error(tmp_path: Path) -> None:
    with patch(
        "ks_gen.verify.ssh.subprocess.run", return_value=_completed(1, "", "scp: not found")
    ), pytest.raises(SshConnectError, match="scp"):
        scp_pull("host", "user", "/r", tmp_path / "x")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_verify_ssh.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement ssh.py**

Create `src/ks_gen/verify/ssh.py`:

```python
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ks_gen.verify.errors import SshConnectError, ToolMissingError


@dataclass(frozen=True)
class SshResult:
    stdout: str
    stderr: str
    exit_code: int


def check_tools() -> None:
    for tool in ("ssh", "scp"):
        if not shutil.which(tool):
            raise ToolMissingError(f"required tool not on PATH: {tool}")


def _first_stderr_line(stderr: str) -> str:
    for line in stderr.splitlines():
        if line.strip():
            return line.strip()
    return ""


def ssh_exec(
    host: str,
    user: str,
    remote_cmd: str,
    *,
    extra_opts: list[str] | None = None,
    timeout: float | None = None,
) -> SshResult:
    cmd: list[str] = ["ssh", "-o", "BatchMode=yes"]
    if extra_opts:
        cmd.extend(extra_opts)
    cmd.append(f"{user}@{host}")
    cmd.append(remote_cmd)

    try:
        proc = subprocess.run(  # noqa: S603 — args are constructed from caller-provided strings
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as e:
        raise SshConnectError(f"ssh timed out after {timeout}s") from e
    except FileNotFoundError as e:
        raise ToolMissingError("ssh not on PATH") from e

    if proc.returncode == 255:
        raise SshConnectError(f"ssh exit 255: {_first_stderr_line(proc.stderr)}")

    return SshResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)


def scp_pull(
    host: str,
    user: str,
    remote_path: str,
    local_path: Path,
    *,
    extra_opts: list[str] | None = None,
    timeout: float | None = None,
) -> None:
    cmd: list[str] = ["scp", "-o", "BatchMode=yes"]
    if extra_opts:
        cmd.extend(extra_opts)
    cmd.append(f"{user}@{host}:{remote_path}")
    cmd.append(str(local_path))

    try:
        proc = subprocess.run(  # noqa: S603
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as e:
        raise SshConnectError(f"scp timed out after {timeout}s") from e
    except FileNotFoundError as e:
        raise ToolMissingError("scp not on PATH") from e

    if proc.returncode != 0:
        raise SshConnectError(
            f"scp exit {proc.returncode}: {_first_stderr_line(proc.stderr)}"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_verify_ssh.py -v`
Expected: 9 passed.

- [ ] **Step 5: Run the full CI chain**

Run: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/verify/ssh.py tests/test_verify_ssh.py
git commit -S -m "feat(verify): ssh/scp subprocess wrappers

ssh_exec()/scp_pull() build subprocess calls with -o BatchMode=yes
(no interactive prompts), append caller-provided extra_opts (raw
--ssh-opts pass-through), and translate FileNotFoundError to
ToolMissingError. Exit 255 from ssh and any nonzero from scp raise
SshConnectError with the first non-blank stderr line. Other nonzero
ssh exits pass through (remote command exits, not transport)."
```

---

## Task 6: Refactor exceptions_report.py to expose expected_failure_rule_ids

**Files:**
- Modify: `src/ks_gen/exceptions_report.py`
- Modify: `tests/test_exceptions_report.py` (add coverage for the new helper)

This task extracts the "set of XCCDF rule ids tailored-out by host.yaml" computation into a reusable helper so `verify` can derive it without re-implementing or parsing the rendered markdown. `render_exceptions_md` continues to produce byte-identical output (golden snapshots must not change).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_exceptions_report.py`:

```python
def test_expected_failure_rule_ids_includes_rule_exceptions(minimal_cfg):
    from ks_gen.exceptions_report import expected_failure_rule_ids

    ids = expected_failure_rule_ids(minimal_cfg)
    # rules like banner_text, sshd ciphers etc. tailor specific XCCDF rules out
    assert any("banner" in rid for rid in ids)
    assert any("sshd" in rid or "ssh" in rid for rid in ids)


def test_expected_failure_rule_ids_includes_declared_exceptions(minimal_cfg):
    from ks_gen.config import ExceptionDecl
    from ks_gen.exceptions_report import expected_failure_rule_ids

    cfg = minimal_cfg.model_copy(
        update={
            "exceptions": [
                ExceptionDecl(
                    id="no-luks",
                    reason="Cloud volumes encrypted by provider.",
                    stig_rules_disabled=["xccdf_org.ssgproject.content_rule_encrypt_partitions"],
                )
            ]
        }
    )
    ids = expected_failure_rule_ids(cfg)
    assert "xccdf_org.ssgproject.content_rule_encrypt_partitions" in ids


def test_expected_failure_rule_ids_returns_a_set(minimal_cfg):
    from ks_gen.exceptions_report import expected_failure_rule_ids

    ids = expected_failure_rule_ids(minimal_cfg)
    assert isinstance(ids, set)
    assert all(isinstance(rid, str) for rid in ids)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_exceptions_report.py -v`
Expected: 3 new tests fail with `ImportError` on `expected_failure_rule_ids`.

- [ ] **Step 3: Add the helper and re-use it inside render_exceptions_md**

Edit `src/ks_gen/exceptions_report.py`. Add this function above `render_exceptions_md`:

```python
def expected_failure_rule_ids(cfg: HostConfig) -> set[str]:
    """Return the set of XCCDF rule ids tailored out by host.yaml.

    Sources: each applicable rule's exception_entry().stig_rules_disabled,
    plus every declared exception in cfg.exceptions. Used by both the
    exceptions.md renderer and `ks-gen verify` (to know which oscap failures
    are expected vs. actionable).
    """
    from ks_gen.registry import load_rules
    from ks_gen.topo import topo_sort

    ids: set[str] = set()
    for r in topo_sort(load_rules()):
        if not r.applies(cfg):
            continue
        entry = r.exception_entry(cfg)
        if entry is None:
            continue
        ids.update(entry.stig_rules_disabled)
    for ex in cfg.exceptions:
        ids.update(ex.stig_rules_disabled)
    return ids
```

The function imports `load_rules`/`topo_sort` inside the body to avoid an import cycle if `exceptions_report` ever ends up in the registry/topo dependency chain. Existing `render_exceptions_md` is unchanged — golden snapshots continue to pass.

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_exceptions_report.py -v`
Expected: all previous tests still pass + 3 new tests pass.

- [ ] **Step 5: Confirm golden snapshots are unaffected**

Run: `pytest tests/golden/ -v`
Expected: all pass (no snapshot drift — render_exceptions_md output is unchanged).

- [ ] **Step 6: Run the full CI chain**

Run: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/ks_gen/exceptions_report.py tests/test_exceptions_report.py
git commit -S -m "refactor(exceptions_report): extract expected_failure_rule_ids

Hoists the 'rule ids tailored out by host.yaml' computation into a
reusable helper. render_exceptions_md output is unchanged (golden
snapshots intact); ks-gen verify will use the helper to derive the
expected-exception set without parsing rendered markdown."
```

---

## Task 7: Remote orchestration (verify/remote.py)

**Files:**
- Create: `src/ks_gen/verify/remote.py`
- Create: `tests/test_verify_remote.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_verify_remote.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from ks_gen.verify.errors import (
    ArfMissingError,
    OscapInvocationError,
    SudoPromptError,
)
from ks_gen.verify.remote import CollectedArfs, collect_arfs, probe_sudo
from ks_gen.verify.ssh import SshResult

# --- probe_sudo --------------------------------------------------------------


def test_probe_sudo_passes_when_sudo_n_true_succeeds() -> None:
    with patch(
        "ks_gen.verify.remote.ssh_exec", return_value=SshResult("", "", 0)
    ) as ssh:
        probe_sudo("h", "u", ssh_extra_opts=[])
    assert ssh.call_args.args[2] == "sudo -n true"


def test_probe_sudo_raises_on_nonzero_sudo_n_true() -> None:
    with patch(
        "ks_gen.verify.remote.ssh_exec",
        return_value=SshResult("", "sudo: a password is required", 1),
    ), pytest.raises(SudoPromptError, match="passwordless"):
        probe_sudo("h", "u", ssh_extra_opts=[])


# --- collect_arfs ------------------------------------------------------------


def _build_cfg():
    from ks_gen.config import AdminUser, HostConfig, System, User

    return HostConfig(
        system=System(hostname="h"),
        user=User(admin=AdminUser(name="u", authorized_keys=["k a@b"], sudo="nopasswd_yes")),
    )


def test_collect_arfs_runs_oscap_pulls_current_and_install(tmp_path: Path) -> None:
    cfg = _build_cfg()
    call_log: list[tuple[str, ...]] = []

    def fake_ssh(host: str, user: str, cmd: str, **kw: object) -> SshResult:
        call_log.append(("ssh", cmd))
        if cmd == "sudo -n true":
            return SshResult("", "", 0)
        if cmd == "sudo -n test -r /root/tailoring.xml":
            return SshResult("", "", 0)
        if "oscap xccdf eval" in cmd:
            return SshResult("", "", 2)  # rules failed = normal
        if cmd == "sudo -n test -r /root/oscap-remediation-results.xml":
            return SshResult("", "", 0)
        if cmd.startswith("sudo -n rm"):
            return SshResult("", "", 0)
        raise AssertionError(f"unexpected ssh cmd: {cmd}")

    def fake_scp(host: str, user: str, remote: str, local: Path, **kw: object) -> None:
        call_log.append(("scp", remote))
        local.write_text("<TestResult/>", encoding="utf-8")

    with patch("ks_gen.verify.remote.ssh_exec", side_effect=fake_ssh), patch(
        "ks_gen.verify.remote.scp_pull", side_effect=fake_scp
    ):
        result = collect_arfs(
            cfg=cfg,
            host="h",
            user="u",
            workdir=tmp_path,
            no_drift=False,
            ssh_extra_opts=[],
            timeout=600,
        )

    assert isinstance(result, CollectedArfs)
    assert "<TestResult/>" in result.current_text
    assert result.install_text == "<TestResult/>"
    assert ("scp", "/tmp/ksgen-verify-current.arf.xml") in call_log
    assert ("scp", "/root/oscap-remediation-results.xml") in call_log


def test_collect_arfs_skips_install_baseline_when_no_drift(tmp_path: Path) -> None:
    cfg = _build_cfg()

    def fake_ssh(host: str, user: str, cmd: str, **kw: object) -> SshResult:
        if cmd == "sudo -n true":
            return SshResult("", "", 0)
        if cmd == "sudo -n test -r /root/tailoring.xml":
            return SshResult("", "", 0)
        if "oscap xccdf eval" in cmd:
            return SshResult("", "", 0)
        if cmd.startswith("sudo -n rm"):
            return SshResult("", "", 0)
        if "oscap-remediation-results" in cmd:
            raise AssertionError("install baseline should not be probed when no_drift=True")
        return SshResult("", "", 0)

    def fake_scp(host: str, user: str, remote: str, local: Path, **kw: object) -> None:
        if "oscap-remediation-results" in remote:
            raise AssertionError("install baseline should not be scp'd when no_drift=True")
        local.write_text("<TestResult/>", encoding="utf-8")

    with patch("ks_gen.verify.remote.ssh_exec", side_effect=fake_ssh), patch(
        "ks_gen.verify.remote.scp_pull", side_effect=fake_scp
    ):
        result = collect_arfs(
            cfg=cfg,
            host="h",
            user="u",
            workdir=tmp_path,
            no_drift=True,
            ssh_extra_opts=[],
            timeout=600,
        )
    assert result.install_text is None


def test_collect_arfs_install_baseline_missing_is_soft_fail(tmp_path: Path) -> None:
    cfg = _build_cfg()

    def fake_ssh(host: str, user: str, cmd: str, **kw: object) -> SshResult:
        if cmd == "sudo -n true":
            return SshResult("", "", 0)
        if cmd == "sudo -n test -r /root/tailoring.xml":
            return SshResult("", "", 0)
        if "oscap xccdf eval" in cmd:
            return SshResult("", "", 0)
        if cmd == "sudo -n test -r /root/oscap-remediation-results.xml":
            return SshResult("", "", 1)
        if cmd.startswith("sudo -n rm"):
            return SshResult("", "", 0)
        return SshResult("", "", 0)

    def fake_scp(host: str, user: str, remote: str, local: Path, **kw: object) -> None:
        local.write_text("<TestResult/>", encoding="utf-8")

    with patch("ks_gen.verify.remote.ssh_exec", side_effect=fake_ssh), patch(
        "ks_gen.verify.remote.scp_pull", side_effect=fake_scp
    ):
        result = collect_arfs(
            cfg=cfg,
            host="h",
            user="u",
            workdir=tmp_path,
            no_drift=False,
            ssh_extra_opts=[],
            timeout=600,
        )
    assert result.install_text is None


def test_collect_arfs_raises_when_tailoring_missing(tmp_path: Path) -> None:
    cfg = _build_cfg()

    def fake_ssh(host: str, user: str, cmd: str, **kw: object) -> SshResult:
        if cmd == "sudo -n true":
            return SshResult("", "", 0)
        if cmd == "sudo -n test -r /root/tailoring.xml":
            return SshResult("", "", 1)
        return SshResult("", "", 0)

    with patch("ks_gen.verify.remote.ssh_exec", side_effect=fake_ssh), patch(
        "ks_gen.verify.remote.scp_pull"
    ), pytest.raises(OscapInvocationError, match="tailoring"):
        collect_arfs(
            cfg=cfg,
            host="h",
            user="u",
            workdir=tmp_path,
            no_drift=False,
            ssh_extra_opts=[],
            timeout=600,
        )


def test_collect_arfs_raises_when_oscap_exit_not_in_0_or_2(tmp_path: Path) -> None:
    cfg = _build_cfg()

    def fake_ssh(host: str, user: str, cmd: str, **kw: object) -> SshResult:
        if cmd == "sudo -n true":
            return SshResult("", "", 0)
        if cmd == "sudo -n test -r /root/tailoring.xml":
            return SshResult("", "", 0)
        if "oscap xccdf eval" in cmd:
            return SshResult("", "scap-security-guide not installed", 127)
        if cmd.startswith("sudo -n rm"):
            return SshResult("", "", 0)
        return SshResult("", "", 0)

    with patch("ks_gen.verify.remote.ssh_exec", side_effect=fake_ssh), patch(
        "ks_gen.verify.remote.scp_pull"
    ), pytest.raises(OscapInvocationError, match="127"):
        collect_arfs(
            cfg=cfg,
            host="h",
            user="u",
            workdir=tmp_path,
            no_drift=False,
            ssh_extra_opts=[],
            timeout=600,
        )


def test_collect_arfs_raises_when_current_arf_is_empty(tmp_path: Path) -> None:
    cfg = _build_cfg()

    def fake_ssh(host: str, user: str, cmd: str, **kw: object) -> SshResult:
        if cmd == "sudo -n true":
            return SshResult("", "", 0)
        if cmd == "sudo -n test -r /root/tailoring.xml":
            return SshResult("", "", 0)
        if "oscap xccdf eval" in cmd:
            return SshResult("", "", 0)
        if cmd.startswith("sudo -n rm"):
            return SshResult("", "", 0)
        return SshResult("", "", 0)

    def fake_scp(host: str, user: str, remote: str, local: Path, **kw: object) -> None:
        local.write_text("", encoding="utf-8")  # empty

    with patch("ks_gen.verify.remote.ssh_exec", side_effect=fake_ssh), patch(
        "ks_gen.verify.remote.scp_pull", side_effect=fake_scp
    ), pytest.raises(ArfMissingError):
        collect_arfs(
            cfg=cfg,
            host="h",
            user="u",
            workdir=tmp_path,
            no_drift=False,
            ssh_extra_opts=[],
            timeout=600,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_verify_remote.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement remote.py**

Create `src/ks_gen/verify/remote.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ks_gen.config import HostConfig
from ks_gen.verify.errors import (
    ArfMissingError,
    OscapInvocationError,
    SudoPromptError,
)
from ks_gen.verify.ssh import ssh_exec, scp_pull

REMOTE_CURRENT_ARF = "/tmp/ksgen-verify-current.arf.xml"
REMOTE_INSTALL_ARF = "/root/oscap-remediation-results.xml"
REMOTE_TAILORING = "/root/tailoring.xml"


@dataclass(frozen=True)
class CollectedArfs:
    current_text: str
    install_text: str | None


def probe_sudo(host: str, user: str, *, ssh_extra_opts: list[str]) -> None:
    result = ssh_exec(host, user, "sudo -n true", extra_opts=ssh_extra_opts)
    if result.exit_code != 0:
        raise SudoPromptError(
            f"sudo prompt detected on {host} as {user}: passwordless sudo is required"
        )


def _oscap_command(cfg: HostConfig) -> str:
    return (
        "sudo -n oscap xccdf eval "
        f"--tailoring-file {REMOTE_TAILORING} "
        f"--profile xccdf_org.ssgproject.content_profile_{cfg.meta.profile} "
        "--fetch-remote-resources "
        f"--results-arf {REMOTE_CURRENT_ARF} "
        f"/usr/share/xml/scap/ssg/content/{cfg.meta.scap_content}"
    )


def collect_arfs(
    *,
    cfg: HostConfig,
    host: str,
    user: str,
    workdir: Path,
    no_drift: bool,
    ssh_extra_opts: list[str],
    timeout: int,
) -> CollectedArfs:
    probe_sudo(host, user, ssh_extra_opts=ssh_extra_opts)

    tailoring_check = ssh_exec(
        host, user, f"sudo -n test -r {REMOTE_TAILORING}", extra_opts=ssh_extra_opts
    )
    if tailoring_check.exit_code != 0:
        raise OscapInvocationError(
            f"install-time tailoring not present at {REMOTE_TAILORING} "
            f"— host may not have been provisioned by ks-gen"
        )

    try:
        oscap_result = ssh_exec(
            host,
            user,
            _oscap_command(cfg),
            extra_opts=ssh_extra_opts,
            timeout=timeout,
        )
        if oscap_result.exit_code not in (0, 2):
            stderr_first = (oscap_result.stderr.splitlines() or [""])[0]
            raise OscapInvocationError(
                f"oscap exit {oscap_result.exit_code}: {stderr_first}"
            )

        local_current = workdir / "current.arf.xml"
        scp_pull(
            host,
            user,
            REMOTE_CURRENT_ARF,
            local_current,
            extra_opts=ssh_extra_opts,
        )
        if not local_current.exists() or local_current.stat().st_size == 0:
            raise ArfMissingError(
                f"pulled current ARF is empty or missing: {local_current}"
            )
        current_text = local_current.read_text(encoding="utf-8")

        install_text: str | None = None
        if not no_drift:
            check = ssh_exec(
                host,
                user,
                f"sudo -n test -r {REMOTE_INSTALL_ARF}",
                extra_opts=ssh_extra_opts,
            )
            if check.exit_code == 0:
                local_install = workdir / "install.arf.xml"
                scp_pull(
                    host,
                    user,
                    REMOTE_INSTALL_ARF,
                    local_install,
                    extra_opts=ssh_extra_opts,
                )
                if local_install.exists() and local_install.stat().st_size > 0:
                    install_text = local_install.read_text(encoding="utf-8")

        return CollectedArfs(current_text=current_text, install_text=install_text)
    finally:
        try:
            ssh_exec(
                host,
                user,
                f"sudo -n rm -f {REMOTE_CURRENT_ARF}",
                extra_opts=ssh_extra_opts,
            )
        except Exception:
            # Best-effort cleanup; never mask the primary error.
            pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_verify_remote.py -v`
Expected: 7 passed.

- [ ] **Step 5: Run the full CI chain**

Run: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/verify/remote.py tests/test_verify_remote.py
git commit -S -m "feat(verify): remote orchestration (probe sudo + collect ARFs)

probe_sudo() probes sudo -n true and raises SudoPromptError on
nonzero. collect_arfs() probes tailoring presence, runs oscap (exit
0 or 2 only), pulls the current ARF (raises ArfMissingError on empty),
then opportunistically pulls /root/oscap-remediation-results.xml
unless --no-drift was set. Best-effort tmpfile cleanup in finally."
```

---

## Task 8: Wire it all together — run_verify in verify/__init__.py

**Files:**
- Modify: `src/ks_gen/verify/__init__.py`
- Create: `tests/test_verify_run.py`
- Create: `tests/fixtures/arf-install-baseline.xml`

- [ ] **Step 1: Create the install-baseline fixture**

The integration test compares `arf-mixed.xml` (post-drift state) against an
all-pass install-time baseline. Create `tests/fixtures/arf-install-baseline.xml`
with the same six rule ids as `arf-mixed.xml`, all `pass`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<arf:asset-report-collection xmlns:arf="http://scap.nist.gov/schema/asset-reporting-format/1.1">
  <arf:reports>
    <arf:report id="r1">
      <arf:content>
        <TestResult xmlns="http://checklists.nist.gov/xccdf/1.2" id="xccdf_org.test_TR">
          <rule-result idref="xccdf_org.ssgproject.content_rule_rule_a">
            <result>pass</result>
          </rule-result>
          <rule-result idref="xccdf_org.ssgproject.content_rule_rule_b">
            <result>pass</result>
          </rule-result>
          <rule-result idref="xccdf_org.ssgproject.content_rule_rule_c">
            <result>pass</result>
          </rule-result>
          <rule-result idref="xccdf_org.ssgproject.content_rule_rule_d">
            <result>pass</result>
          </rule-result>
          <rule-result idref="xccdf_org.ssgproject.content_rule_rule_e">
            <result>pass</result>
          </rule-result>
          <rule-result idref="xccdf_org.ssgproject.content_rule_rule_f">
            <result>pass</result>
          </rule-result>
        </TestResult>
      </arf:content>
    </arf:report>
  </arf:reports>
</arf:asset-report-collection>
```

- [ ] **Step 2: Write the failing integration test**

Create `tests/test_verify_run.py`:

```python
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from ks_gen.config import AdminUser, ExceptionDecl, HostConfig, System, User
from ks_gen.verify import run_verify
from ks_gen.verify.remote import CollectedArfs

FIXTURES = Path(__file__).parent / "fixtures"


def _cfg() -> HostConfig:
    return HostConfig(
        system=System(hostname="h"),
        user=User(admin=AdminUser(name="ops", authorized_keys=["k a@b"], sudo="nopasswd_yes")),
        exceptions=[
            ExceptionDecl(
                id="rule-d-accepted",
                reason="known-failing on STIG-strict cloud baseline",
                stig_rules_disabled=["xccdf_org.ssgproject.content_rule_rule_d"],
            ),
        ],
    )


def test_run_verify_end_to_end_drives_real_arf_through_reconcile(tmp_path: Path) -> None:
    current = (FIXTURES / "arf-mixed.xml").read_text(encoding="utf-8")
    install = (FIXTURES / "arf-install-baseline.xml").read_text(encoding="utf-8")

    with patch(
        "ks_gen.verify.collect_arfs",
        return_value=CollectedArfs(current_text=current, install_text=install),
    ):
        report = run_verify(
            cfg=_cfg(),
            host="h",
            user="ops",
            workdir=tmp_path,
            no_drift=False,
            ssh_extra_opts=[],
            timeout=600,
        )

    by_id = {r.rule_id: r for r in report.rows}
    # rule_d declared as exception → expected_fail
    assert (
        by_id["xccdf_org.ssgproject.content_rule_rule_d"].category == "expected_fail"
    )
    # rule_e: install=pass, current=fail, no exception → regression
    assert by_id["xccdf_org.ssgproject.content_rule_rule_e"].category == "regression"
    # rule_f: install=pass, current=error → incomplete
    assert by_id["xccdf_org.ssgproject.content_rule_rule_f"].category == "incomplete"
    # rule_a/b/c: pass → clean
    for rid in ("rule_a", "rule_b", "rule_c"):
        assert (
            by_id[f"xccdf_org.ssgproject.content_rule_{rid}"].category == "clean"
        )
    assert report.install_baseline_available is True
    assert report.is_clean is False


def test_run_verify_install_text_none_degrades_gracefully(tmp_path: Path) -> None:
    current = (FIXTURES / "arf-clean.xml").read_text(encoding="utf-8")
    with patch(
        "ks_gen.verify.collect_arfs",
        return_value=CollectedArfs(current_text=current, install_text=None),
    ):
        report = run_verify(
            cfg=_cfg(),
            host="h",
            user="ops",
            workdir=tmp_path,
            no_drift=True,
            ssh_extra_opts=[],
            timeout=600,
        )
    assert report.install_baseline_available is False
    assert report.is_clean is True
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_verify_run.py -v`
Expected: `ImportError` on `run_verify`.

- [ ] **Step 4: Implement run_verify**

Replace `src/ks_gen/verify/__init__.py` (currently just a docstring) with:

```python
"""Post-install host verification — re-run oscap, reconcile against host.yaml."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ks_gen.config import HostConfig
from ks_gen.exceptions_report import expected_failure_rule_ids
from ks_gen.verify.arf import parse_arf
from ks_gen.verify.reconcile import VerifyReport, build_report
from ks_gen.verify.remote import collect_arfs


def run_verify(
    *,
    cfg: HostConfig,
    host: str,
    user: str,
    workdir: Path,
    no_drift: bool = False,
    ssh_extra_opts: list[str] | None = None,
    timeout: int = 600,
) -> VerifyReport:
    expected = expected_failure_rule_ids(cfg)
    arfs = collect_arfs(
        cfg=cfg,
        host=host,
        user=user,
        workdir=workdir,
        no_drift=no_drift,
        ssh_extra_opts=ssh_extra_opts or [],
        timeout=timeout,
    )
    current = parse_arf(arfs.current_text)
    install = parse_arf(arfs.install_text) if arfs.install_text else None
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return build_report(
        current=current,
        install=install,
        expected_failures=expected,
        host=host,
        user=user,
        timestamp_utc=timestamp,
    )


__all__ = ["run_verify"]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_verify_run.py -v`
Expected: 2 passed.

- [ ] **Step 6: Run the full CI chain**

Run: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/ks_gen/verify/__init__.py tests/test_verify_run.py tests/fixtures/arf-install-baseline.xml
git commit -S -m "feat(verify): run_verify wires arf + reconcile + remote

run_verify() derives the expected-failure set from host.yaml,
delegates ARF collection to remote.collect_arfs, parses both ARFs,
and returns a VerifyReport. Integration test drives real fixture ARFs
through the full pipeline with collect_arfs patched."
```

---

## Task 9: CLI command (cli.verify_cmd)

**Files:**
- Modify: `src/ks_gen/cli.py`
- Create: `tests/test_cli/test_verify.py`

- [ ] **Step 1: Write the failing CLI test**

Create `tests/test_cli/test_verify.py`:

```python
from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from ks_gen.cli import app
from ks_gen.verify.errors import (
    OscapInvocationError,
    SshConnectError,
    SudoPromptError,
    ToolMissingError,
)
from ks_gen.verify.reconcile import VerifyReport, VerifyRow

VALID_YAML = textwrap.dedent(
    """\
    system: {hostname: h1}
    user:
      admin:
        name: ops
        authorized_keys: ["ssh-ed25519 A a@b"]
        sudo: nopasswd_yes
    """
)


def _write_cfg(tmp_path: Path) -> Path:
    p = tmp_path / "host.yaml"
    p.write_text(VALID_YAML, encoding="utf-8")
    return p


def _clean_report() -> VerifyReport:
    return VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-07T12:00:00Z",
        rows=(VerifyRow("rule_a", "pass", "pass", False, "clean"),),
        install_baseline_available=True,
    )


def _failing_report() -> VerifyReport:
    return VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-07T12:00:00Z",
        rows=(VerifyRow("rule_b", "fail", "pass", False, "regression"),),
        install_baseline_available=True,
    )


def test_verify_exits_0_on_clean_report(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with patch("ks_gen.cli.run_verify", return_value=_clean_report()), patch(
        "ks_gen.cli.check_tools"
    ):
        result = runner.invoke(app, ["verify", "--host", "h1", "--config", str(cfg)])
    assert result.exit_code == 0, result.output


def test_verify_exits_6_on_failing_report(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with patch("ks_gen.cli.run_verify", return_value=_failing_report()), patch(
        "ks_gen.cli.check_tools"
    ):
        result = runner.invoke(app, ["verify", "--host", "h1", "--config", str(cfg)])
    assert result.exit_code == 6


@pytest.mark.parametrize(
    "error,expected_exit,fragment",
    [
        (SshConnectError("Connection refused"), 7, "transport"),
        (SudoPromptError("passwordless"), 7, "sudo"),
        (OscapInvocationError("tailoring"), 7, "oscap"),
    ],
)
def test_verify_maps_verify_errors_to_exit_codes(
    tmp_path: Path, error: Exception, expected_exit: int, fragment: str
) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with patch("ks_gen.cli.run_verify", side_effect=error), patch(
        "ks_gen.cli.check_tools"
    ):
        result = runner.invoke(app, ["verify", "--host", "h1", "--config", str(cfg)])
    assert result.exit_code == expected_exit
    assert fragment in result.output.lower()


def test_verify_exit_5_when_ssh_not_on_path(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with patch("ks_gen.cli.check_tools", side_effect=ToolMissingError("ssh")):
        result = runner.invoke(app, ["verify", "--host", "h1", "--config", str(cfg)])
    assert result.exit_code == 5


def test_verify_exit_2_when_config_invalid(tmp_path: Path) -> None:
    cfg = tmp_path / "host.yaml"
    cfg.write_text("not-a-mapping", encoding="utf-8")
    runner = CliRunner()
    with patch("ks_gen.cli.check_tools"):
        result = runner.invoke(app, ["verify", "--host", "h1", "--config", str(cfg)])
    assert result.exit_code == 2


def test_verify_format_json_emits_json(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with patch("ks_gen.cli.run_verify", return_value=_clean_report()), patch(
        "ks_gen.cli.check_tools"
    ):
        result = runner.invoke(
            app, ["verify", "--host", "h1", "--config", str(cfg), "--format", "json"]
        )
    assert result.exit_code == 0
    assert '"host":' in result.output
    assert '"is_clean": true' in result.output


def test_verify_resolves_user_from_host_yaml_when_not_passed(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    captured_user: list[str] = []

    def fake_run(**kwargs: object) -> VerifyReport:
        captured_user.append(str(kwargs["user"]))
        return _clean_report()

    with patch("ks_gen.cli.run_verify", side_effect=fake_run), patch("ks_gen.cli.check_tools"):
        result = runner.invoke(app, ["verify", "--host", "h1", "--config", str(cfg)])
    assert result.exit_code == 0
    assert captured_user == ["ops"]


def test_verify_user_flag_overrides_config(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    captured_user: list[str] = []

    def fake_run(**kwargs: object) -> VerifyReport:
        captured_user.append(str(kwargs["user"]))
        return _clean_report()

    with patch("ks_gen.cli.run_verify", side_effect=fake_run), patch("ks_gen.cli.check_tools"):
        result = runner.invoke(
            app, ["verify", "--host", "h1", "--config", str(cfg), "--user", "audit"]
        )
    assert result.exit_code == 0
    assert captured_user == ["audit"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli/test_verify.py -v`
Expected: many failures — `ks_gen.cli` doesn't export `run_verify` / `check_tools`, no `verify` command yet.

- [ ] **Step 3: Add verify_cmd to cli.py**

Edit `src/ks_gen/cli.py`. Add imports at the top with the other imports:

```python
import shlex
import tempfile

from ks_gen.verify import run_verify
from ks_gen.verify.errors import VerifyError
from ks_gen.verify.report import render_json, render_table
from ks_gen.verify.ssh import check_tools
```

Append the new command to `cli.py` (after `iso_cmd`, before the `if __name__ == "__main__":` guard):

```python
@app.command(
    name="verify",
    help="Re-run oscap on a deployed host and reconcile against host.yaml.",
)
def verify_cmd(
    host: str = typer.Option(..., "--host"),
    config: Path = typer.Option(  # noqa: B008
        ..., "--config", "-c", exists=True, dir_okay=False, readable=True
    ),
    user: str | None = typer.Option(None, "--user"),
    ssh_opts: str = typer.Option("", "--ssh-opts"),
    format_: str = typer.Option("table", "--format"),
    arf_out: Path | None = typer.Option(  # noqa: B008
        None, "--arf-out", file_okay=False
    ),
    keep_arf: bool = typer.Option(False, "--keep-arf"),
    no_drift: bool = typer.Option(False, "--no-drift"),
    timeout: int = typer.Option(600, "--timeout"),
) -> None:
    try:
        cfg = load_host_config(config, sets=[])
    except ConfigError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=int(e.exit_code)) from None

    try:
        check_tools()
    except VerifyError as e:
        typer.echo(f"ks-gen verify: {e}", err=True)
        raise typer.Exit(code=int(e.exit_code)) from None

    resolved_user = user or cfg.user.admin.name
    extra_opts = shlex.split(ssh_opts) if ssh_opts else []

    def _do(workdir: Path) -> None:
        try:
            report = run_verify(
                cfg=cfg,
                host=host,
                user=resolved_user,
                workdir=workdir,
                no_drift=no_drift,
                ssh_extra_opts=extra_opts,
                timeout=timeout,
            )
        except VerifyError as e:
            label = type(e).__name__.removesuffix("Error").lower()
            typer.echo(f"ks-gen verify: transport failure: {label}: {e}", err=True)
            raise typer.Exit(code=int(e.exit_code)) from None

        if format_ == "json":
            typer.echo(render_json(report))
        else:
            typer.echo(render_table(report))

        if not report.is_clean:
            raise typer.Exit(code=int(ExitCode.VERIFY_FAIL))

    if arf_out is not None or keep_arf:
        target = arf_out or Path(tempfile.mkdtemp(prefix="ksgen-verify-"))
        target.mkdir(parents=True, exist_ok=True)
        _do(target)
    else:
        with tempfile.TemporaryDirectory(prefix="ksgen-verify-") as tmpdir:
            _do(Path(tmpdir))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli/test_verify.py -v`
Expected: 10 passed (7 single tests + 1 test parametrized 3 ways).

The test wording (`"transport"`, `"sudo"`, `"oscap"` lowercase substring
matches) is the operator-grep contract — keep it stable from here on. If any
test fails on wording, change the implementation to match the test, not the
test to match a typo.

- [ ] **Step 5: Run the full CI chain**

Run: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/cli.py tests/test_cli/test_verify.py
git commit -S -m "feat(verify): cli verify_cmd

Adds 'ks-gen verify --host <addr> --config host.yaml' with --user,
--ssh-opts, --format, --arf-out, --keep-arf, --no-drift, --timeout.
Resolves the ssh user from cfg.user.admin.name if --user is omitted.
Maps VerifyError subclasses to their exit_code (TOOL_MISSING=5,
TRANSPORT_FAIL=7); clean report → 0, dirty report → VERIFY_FAIL (6)."
```

---

## Task 10: Documentation

**Files:**
- Modify: `MANUAL.md`
- Modify: `README.md`
- Modify: `MINIMAL-TEST.md`

The wording below is illustrative — adapt it to the existing voice of each document. The point of this task is to ensure each doc explains the command, prerequisites, output, and exit codes consistently.

- [ ] **Step 1: Add a "Post-install verification" section to MANUAL.md**

Find the most appropriate location in `MANUAL.md` (likely after the section on install-time `oscap` execution, e.g. §3.x or a new top-level section after §3) and add:

````markdown
## Post-install verification — `ks-gen verify`

After a host is installed, re-evaluate it against its tailoring and reconcile any failures
against the exception set declared in `host.yaml`:

```
ks-gen verify --host <addr> --config hosts/<name>/host.yaml
```

### Prerequisites

- `ssh` and `scp` on the workstation's PATH.
- The admin user provisioned by the kickstart (`cfg.user.admin.name`) reachable via SSH,
  with the workstation's key in their `~/.ssh/authorized_keys`.
- **Passwordless sudo** for that user. The wizard defaults to `sudo: nopasswd_yes`; the
  locked-password-requires-nopasswd validator enforces it whenever the admin has no password.
  Hosts not configured this way will fail with `ks-gen verify: sudo prompt detected ...`.
- `/root/tailoring.xml` present on the host (placed there by every ks-gen install). Hosts
  not provisioned by ks-gen are not supported.

### Output

By default, a plain-text table grouped by category, omitting rules that are clean:

```
verify host=h1.example.com user=ops at=2026-06-07T12:00:00Z
  summary: clean=412 expected_fail=3 new_fail=1 regression=2 incomplete=0 — FAILURES

  CATEGORY    CURRENT  INSTALL  EXP  RULE
  regression  fail     pass     no   xccdf_org.ssgproject.content_rule_<id>
  ...
```

`--format json` emits the same data as a JSON document suitable for machine consumption.

### Drift comparison

`verify` pulls the install-time ARF from `/root/oscap-remediation-results.xml` (written by
the install-time `%post` block) and compares per-rule results. A rule that fails now but
passed at install is reported as `regression`. If the install-time ARF is missing
(e.g., rotated or deleted), the drift comparison is skipped and a banner is printed; the
compliance check still runs.

Pass `--no-drift` to skip the install-baseline pull entirely.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | All evaluated rules pass; no drift detected. |
| 2 | `host.yaml` invalid. |
| 5 | `ssh` or `scp` not on PATH. |
| 6 | At least one rule fails on the live host (`new_fail` or `regression`). |
| 7 | Transport failure: ssh unreachable, sudo prompt, oscap not runnable, ARF parse error. |

### Out of scope

Single-host, on-demand only. Batch / fleet sweeps, captured-baseline mode, tailoring drift
detection, on-host self-check timers, history tracking, HTML report generation, and
exception auto-suggest are tracked separately (issues #10–#17).
````

- [ ] **Step 2: Add `verify` to the README command summary**

In `README.md`, find the command summary table or list (it lists `gen`, `iso`, `lint`, `new`, `rules`, `schema`) and add a row/bullet for `verify`:

```markdown
- `ks-gen verify --host <addr> --config <host.yaml>` — re-run oscap on a deployed host,
  reconcile failures against `host.yaml`, report compliance + drift.
```

- [ ] **Step 3: Add an optional final step to MINIMAL-TEST.md**

At the end of the Hyper-V acceptance walkthrough in `MINIMAL-TEST.md`, add:

```markdown
## (Optional) Step N — Verify the installed host

Once the VM boots and you can SSH in as the admin user, close the loop with:

```
ks-gen verify --host <vm-ip> --config <path/to/host.yaml>
```

Expected: exit code 0 and a summary line ending with `— CLEAN`. Any `new_fail` or
`regression` rows mean the install didn't fully apply the intended state, or the
host has drifted from install-time baseline.
```

- [ ] **Step 4: Run the full CI chain**

Run: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
Expected: clean (docs-only changes don't affect tests).

- [ ] **Step 5: Commit**

```bash
git add MANUAL.md README.md MINIMAL-TEST.md
git commit -S -m "docs(verify): operator docs for ks-gen verify

MANUAL.md: new 'Post-install verification' section covering
prerequisites, output format, drift comparison, exit codes, scope.
README.md: command summary entry. MINIMAL-TEST.md: optional verify
step closing the Hyper-V acceptance loop."
```

---

## Final verification

- [ ] **Step 1: Confirm the full CI chain passes from a clean state**

Run: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
Expected: clean.

- [ ] **Step 2: Confirm command shape**

Run: `python -m ks_gen.cli verify --help`
Expected: help text lists `--host`, `--config`, `--user`, `--ssh-opts`, `--format`,
`--arf-out`, `--keep-arf`, `--no-drift`, `--timeout`.

- [ ] **Step 3: Decide on release**

This closes issue #5. Two options:

1. Tag `v0.3.0` from main once Task 10 is committed.
2. Merge to main via PR, leave tagging for when more v0.3 work lands (e.g., one of #6–#9 from the v0.2 backlog).

The project's recent pattern (per `project_ks_gen` memory) is to tag minor releases that bundle multiple PRs, so option 2 is the default unless a single feature warrants its own minor bump.
