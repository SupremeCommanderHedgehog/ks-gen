# Verify tailoring drift detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in `--check-tailoring` flag to `ks-gen verify` that scp-pulls `/root/tailoring.xml`, re-renders the expected tailoring locally from the workstation `host.yaml`, and reports a per-op diff. Compliance against a stale tailoring becomes visible instead of silently "clean". Closes #12. Ships the design at `docs/superpowers/specs/2026-06-09-verify-tailoring-drift-design.md`.

**Architecture:** New `src/ks_gen/verify/tailoring_drift.py` with pure parse/compare/render functions. New `collect_deployed_tailoring` in `verify/remote.py`. `VerifyReport` gains an optional `tailoring_drift` field. `run_verify` gains a `check_tailoring` bool param. Renderers append a drift section (table) / `tailoring_drift` key (JSON). New `ExitCode.TAILORING_DRIFT = 8`, ranked below `VERIFY_FAIL`. The re-render path extracts a tiny helper from `writer.build_bundle` so verify doesn't render ks.cfg + exceptions just to throw them away.

**Tech Stack:** Python 3.11+, stdlib `xml.etree.ElementTree` (no new dep), pydantic 2.x, typer, pytest + syrupy + monkeypatch + tmp_path for testing. CI parity: `ruff check && ruff format --check && mypy && pytest -q`.

**Branch:** `impl/v0.9.0-verify-tailoring-drift` (create in Pre-flight). Spec at commit `ef9c723` on main.

---

## Pre-flight

- [ ] **Step 1: Create and switch to feature branch**

```bash
git switch -c impl/v0.9.0-verify-tailoring-drift
git branch --show-current
# expected: impl/v0.9.0-verify-tailoring-drift
git log -1 --format="%h %s"
# expected: ef9c723 docs(specs): verify tailoring drift detection design (#12)
git status --short
# expected: only .claude/ and .scratch/ untracked
```

- [ ] **Step 2: Confirm CI parity baseline is green**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 456 passed (the v0.8.0 baseline).

---

### Task 1: Add `TAILORING_DRIFT` to `ExitCode`

**Files:**
- Modify: `src/ks_gen/loader.py:13-22` (extend `ExitCode` enum)
- Test: `tests/test_loader.py` (add one test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_loader.py`:

```python
def test_exit_code_tailoring_drift_is_8() -> None:
    from ks_gen.loader import ExitCode

    assert int(ExitCode.TAILORING_DRIFT) == 8
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_loader.py::test_exit_code_tailoring_drift_is_8 -v
```

Expected: FAIL with `AttributeError: TAILORING_DRIFT` (or `ExitCode has no member 'TAILORING_DRIFT'`).

- [ ] **Step 3: Add the enum member**

Edit `src/ks_gen/loader.py` — extend the `ExitCode` IntEnum class (currently ends at `TRANSPORT_FAIL = 7`):

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
    TAILORING_DRIFT = 8
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_loader.py::test_exit_code_tailoring_drift_is_8 -v
```

Expected: PASS.

- [ ] **Step 5: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 457 passed.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/loader.py tests/test_loader.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(loader): add ExitCode.TAILORING_DRIFT=8"
```

---

### Task 2: Add `TailoringParseError` to `verify/errors.py`

**Files:**
- Modify: `src/ks_gen/verify/errors.py` (append one class at end)
- Test: `tests/test_verify_errors.py` (add one test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_verify_errors.py`:

```python
def test_tailoring_parse_error_has_verify_fail_exit_code() -> None:
    from ks_gen.loader import ExitCode
    from ks_gen.verify.errors import TailoringParseError, VerifyError

    err = TailoringParseError("garbage")
    assert isinstance(err, VerifyError)
    assert err.exit_code == ExitCode.VERIFY_FAIL
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_verify_errors.py::test_tailoring_parse_error_has_verify_fail_exit_code -v
```

Expected: FAIL with `ImportError: cannot import name 'TailoringParseError'`.

- [ ] **Step 3: Append the new class**

Append to `src/ks_gen/verify/errors.py`:

```python
class TailoringParseError(VerifyError):
    """Tailoring XML failed to parse — malformed XML or missing <Profile>.

    Exit code is VERIFY_FAIL (6); the parse failure is treated as a verify
    failure rather than a transport failure because the bytes arrived but
    aren't usable. Message text names which side failed (deployed vs
    re-rendered) so the operator knows whether to suspect host tampering
    or a ks-gen renderer regression."""

    exit_code: ExitCode = ExitCode.VERIFY_FAIL
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_verify_errors.py::test_tailoring_parse_error_has_verify_fail_exit_code -v
```

Expected: PASS.

- [ ] **Step 5: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 458 passed.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/verify/errors.py tests/test_verify_errors.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(verify): add TailoringParseError(VerifyError) with VERIFY_FAIL exit code"
```

---

### Task 3: Extract `render_tailoring(cfg)` from `writer.build_bundle`

**Files:**
- Modify: `src/ks_gen/writer.py` (extract helper; build_bundle calls into it)
- Test: `tests/test_writer.py` (add one round-trip test)

The helper is verbatim the existing rules-loading + topo + applicable + tailoring-op collection logic. `build_bundle` still produces the same `Bundle` byte-for-byte; verify also calls the helper.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_writer.py`:

```python
def test_render_tailoring_matches_build_bundle_tailoring_xml() -> None:
    """render_tailoring(cfg) produces the same XML as build_bundle(cfg).tailoring_xml,
    modulo the embedded timestamp in <xccdf:version time="...">."""
    import re

    from ks_gen.config import AdminUser, HostConfig, System, User
    from ks_gen.writer import build_bundle, render_tailoring

    cfg = HostConfig(
        system=System(hostname="h"),
        user=User(
            admin=AdminUser(name="ops", authorized_keys=["ssh-ed25519 A a@b"], sudo="nopasswd_yes")
        ),
    )
    bundle_xml = build_bundle(cfg).tailoring_xml
    direct_xml = render_tailoring(cfg)

    # Strip the timestamp before comparison — datetime.now(UTC) embedded in
    # the version header differs between the two renders.
    strip = re.compile(r'time="[^"]*"')
    assert strip.sub('time=""', bundle_xml) == strip.sub('time=""', direct_xml)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_writer.py::test_render_tailoring_matches_build_bundle_tailoring_xml -v
```

Expected: FAIL with `ImportError: cannot import name 'render_tailoring'`.

- [ ] **Step 3: Extract the helper**

Edit `src/ks_gen/writer.py` — add `render_tailoring` and refactor `build_bundle` to call it. Full replacement of the `build_bundle` body and add the new function above it. The complete file becomes:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ks_gen.config import HostConfig
from ks_gen.exceptions_report import render_exceptions_md
from ks_gen.registry import load_rules
from ks_gen.skeleton import PostBlock, render_skeleton
from ks_gen.tailoring import build_tailoring_xml
from ks_gen.topo import topo_sort


@dataclass(frozen=True)
class Bundle:
    ks_cfg: str
    tailoring_xml: str
    host_yaml: str
    exceptions_md: str


def render_tailoring(cfg: HostConfig) -> str:
    """Render the tailoring.xml for `cfg` without rendering ks.cfg / exceptions.md.

    Used by `build_bundle` (the full bundle path) and by `verify` (for
    tailoring drift detection). The embedded `<xccdf:version time="...">`
    timestamp comes from `build_tailoring_xml`'s `datetime.now(UTC)` call —
    callers comparing two renders must strip it first.
    """
    rules = topo_sort(load_rules())
    applicable = [r for r in rules if r.applies(cfg)]
    tailoring_ops = []
    for r in applicable:
        tailoring_ops.extend(r.emit_tailoring(cfg))
    profile_id = f"xccdf_org.ssgproject.content_profile_{cfg.meta.profile}"
    return build_tailoring_xml(tailoring_ops, profile_id=profile_id)


def build_bundle(cfg: HostConfig) -> Bundle:
    rules = topo_sort(load_rules())
    applicable = [r for r in rules if r.applies(cfg)]

    post_blocks: list[PostBlock] = []
    tailoring_ops = []
    for r in applicable:
        body = r.emit_post(cfg).rstrip()
        if body:
            post_blocks.append(PostBlock(rule_id=r.id, body=body))
        tailoring_ops.extend(r.emit_tailoring(cfg))

    profile_id = f"xccdf_org.ssgproject.content_profile_{cfg.meta.profile}"
    tailoring_xml = build_tailoring_xml(tailoring_ops, profile_id=profile_id)
    ks_cfg = render_skeleton(cfg, post_blocks=list(post_blocks))
    host_yaml = yaml.safe_dump(
        cfg.model_dump(mode="json"), sort_keys=False, default_flow_style=False
    )
    exceptions_md = render_exceptions_md(cfg, applicable)
    return Bundle(
        ks_cfg=ks_cfg,
        tailoring_xml=tailoring_xml,
        host_yaml=host_yaml,
        exceptions_md=exceptions_md,
    )


def write_bundle(bundle: Bundle, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ks.cfg").write_text(bundle.ks_cfg, encoding="utf-8", newline="\n")
    (out_dir / "tailoring.xml").write_text(bundle.tailoring_xml, encoding="utf-8", newline="\n")
    (out_dir / "host.yaml").write_text(bundle.host_yaml, encoding="utf-8", newline="\n")
    (out_dir / "exceptions.md").write_text(bundle.exceptions_md, encoding="utf-8", newline="\n")
```

The duplication between `render_tailoring` and `build_bundle` (rules load + applicable filter + ops collection) is intentional: extracting a second shared helper for the rules+applicable list would add a tuple-return signature for a single inner-loop savings. The duplicated three lines are clearer; both paths are pinned by the round-trip test above.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_writer.py::test_render_tailoring_matches_build_bundle_tailoring_xml -v
```

Expected: PASS.

- [ ] **Step 5: Confirm existing writer/golden tests still pass**

```bash
pytest tests/test_writer.py tests/golden -q
```

Expected: all green; no snapshot diffs (build_bundle output byte-identical).

- [ ] **Step 6: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 459 passed.

- [ ] **Step 7: Commit**

```bash
git add src/ks_gen/writer.py tests/test_writer.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "refactor(writer): extract render_tailoring helper for verify reuse"
```

---

### Task 4: `verify/tailoring_drift.py` — data model

**Files:**
- Create: `src/ks_gen/verify/tailoring_drift.py` (data classes only at this step)
- Test: `tests/test_verify_tailoring_drift.py` (one import-smoke test)

This task lands the dataclasses so subsequent tasks have stable shapes. No parse/compare logic yet — each gets its own task.

- [ ] **Step 1: Write the failing test**

Create `tests/test_verify_tailoring_drift.py`:

```python
from __future__ import annotations

from ks_gen.rules._types import TailoringOp
from ks_gen.verify.tailoring_drift import (
    OpChange,
    ParsedTailoring,
    TailoringDriftReport,
)


def test_parsed_tailoring_shape() -> None:
    op = TailoringOp(rule_id="r1", action="disable")
    pt = ParsedTailoring(profile_id="p", ops=[op])
    assert pt.profile_id == "p"
    assert pt.ops == [op]


def test_op_change_shape() -> None:
    change = OpChange(
        rule_id="r1",
        action="set_value",
        expected_value="5",
        deployed_value="24",
    )
    assert change.rule_id == "r1"
    assert change.expected_value == "5"
    assert change.deployed_value == "24"


def test_tailoring_drift_report_shape() -> None:
    report = TailoringDriftReport(
        profile_id_expected="p1",
        profile_id_deployed="p2",
        added=[],
        removed=[],
        changed=[],
    )
    assert report.profile_id_expected == "p1"
    assert report.profile_id_deployed == "p2"
    assert report.added == []
    assert report.removed == []
    assert report.changed == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_verify_tailoring_drift.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'ks_gen.verify.tailoring_drift'`.

- [ ] **Step 3: Create the module with the data classes**

Create `src/ks_gen/verify/tailoring_drift.py`:

```python
"""Tailoring drift detection — compare expected (re-rendered from host.yaml)
against deployed (`/root/tailoring.xml` pulled from the host).

Pure parse/compare/render functions. Re-uses `TailoringOp` from
`ks_gen.rules._types` as the comparison unit; both sides round-trip through
the same dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass

from ks_gen.rules._types import TailoringOp


@dataclass(frozen=True)
class ParsedTailoring:
    """A tailoring.xml decoded into its profile_id + ordered op list."""

    profile_id: str
    ops: list[TailoringOp]


@dataclass(frozen=True)
class OpChange:
    """A set-value op whose value differs between expected and deployed.

    `action` is always `"set_value"`. select/disable transitions can't be
    `changed` because action is part of the op identity — a select-to-disable
    flip surfaces as one `removed` + one `added`.
    """

    rule_id: str
    action: str
    expected_value: str
    deployed_value: str


@dataclass(frozen=True)
class TailoringDriftReport:
    """Drift between expected and deployed tailorings.

    Empty `added`/`removed`/`changed` lists *with matching profile_ids*
    means the check ran and found no drift. `verify.reconcile.VerifyReport`
    exposes `has_tailoring_drift` for the convenience predicate.
    """

    profile_id_expected: str
    profile_id_deployed: str
    added: list[TailoringOp]
    removed: list[TailoringOp]
    changed: list[OpChange]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_verify_tailoring_drift.py -v
```

Expected: PASS, 3 tests.

- [ ] **Step 5: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 462 passed.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/verify/tailoring_drift.py tests/test_verify_tailoring_drift.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(verify): tailoring_drift module scaffold (ParsedTailoring, OpChange, TailoringDriftReport)"
```

---

### Task 5: `parse_tailoring_xml` — TDD

**Files:**
- Modify: `src/ks_gen/verify/tailoring_drift.py` (add function)
- Modify: `tests/test_verify_tailoring_drift.py` (add tests)

The parser uses stdlib `xml.etree.ElementTree` with local-name matching, mirroring `verify/arf.py:_localname`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_verify_tailoring_drift.py`:

```python
import pytest

from ks_gen.tailoring import build_tailoring_xml
from ks_gen.verify.errors import TailoringParseError
from ks_gen.verify.tailoring_drift import parse_tailoring_xml


def test_parse_round_trips_build_tailoring_xml() -> None:
    ops = [
        TailoringOp(rule_id="rule_a", action="disable"),
        TailoringOp(rule_id="rule_b", action="select"),
        TailoringOp(rule_id="rule_c", action="set_value", value="24"),
    ]
    xml = build_tailoring_xml(ops, profile_id="xccdf_org.ssgproject.content_profile_stig")
    parsed = parse_tailoring_xml(xml)

    assert parsed.profile_id == "xccdf_org.ssgproject.content_profile_stig"
    assert sorted(parsed.ops, key=lambda o: o.rule_id) == sorted(ops, key=lambda o: o.rule_id)


def test_parse_handles_empty_set_value() -> None:
    ops = [TailoringOp(rule_id="rule_a", action="set_value", value="")]
    xml = build_tailoring_xml(ops, profile_id="p")
    parsed = parse_tailoring_xml(xml)
    assert parsed.ops == [TailoringOp(rule_id="rule_a", action="set_value", value="")]


def test_parse_raises_on_garbage_xml() -> None:
    with pytest.raises(TailoringParseError, match="well-formed"):
        parse_tailoring_xml("<not-xml")


def test_parse_raises_on_xml_with_no_profile() -> None:
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<xccdf:Tailoring xmlns:xccdf="http://checklists.nist.gov/xccdf/1.2"/>'
    )
    with pytest.raises(TailoringParseError, match="Profile"):
        parse_tailoring_xml(xml)


def test_parse_ignores_unknown_op_elements() -> None:
    """Forward-compat: unknown child elements inside <Profile> are dropped, not raised."""
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<xccdf:Tailoring xmlns:xccdf="http://checklists.nist.gov/xccdf/1.2">'
        '<xccdf:Profile id="x">'
        '<xccdf:select idref="r1" selected="true"/>'
        '<xccdf:future-element idref="r2"/>'
        '</xccdf:Profile>'
        '</xccdf:Tailoring>'
    )
    parsed = parse_tailoring_xml(xml)
    assert parsed.ops == [TailoringOp(rule_id="r1", action="select")]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_verify_tailoring_drift.py -v
```

Expected: 5 tests FAIL with `ImportError: cannot import name 'parse_tailoring_xml'`.

- [ ] **Step 3: Implement `parse_tailoring_xml`**

Append to `src/ks_gen/verify/tailoring_drift.py`:

```python
import xml.etree.ElementTree as ET

from ks_gen.verify.errors import TailoringParseError


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_tailoring_xml(text: str) -> ParsedTailoring:
    """Parse a tailoring.xml into profile_id + ordered TailoringOp list.

    Uses stdlib xml.etree.ElementTree with local-name matching (same pattern
    as `verify/arf.py`). Recognized op elements:

    - `<xccdf:select idref="..." selected="true"/>`  → action="select"
    - `<xccdf:select idref="..." selected="false"/>` → action="disable"
    - `<xccdf:set-value idref="...">VALUE</xccdf:set-value>` → action="set_value"

    Unknown child elements inside `<Profile>` are dropped, not raised — keeps
    the parser forward-compatible against new XCCDF op kinds.

    Raises:
        TailoringParseError: malformed XML or no `<Profile>` element.
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise TailoringParseError(f"tailoring XML is not well-formed: {e}") from e

    profile = None
    for elem in root.iter():
        if _localname(elem.tag) == "Profile":
            profile = elem
            break
    if profile is None:
        raise TailoringParseError("tailoring XML has no <Profile> element")

    profile_id = profile.get("id") or ""
    ops: list[TailoringOp] = []
    for child in profile:
        local = _localname(child.tag)
        if local == "select":
            rule_id = child.get("idref") or ""
            if not rule_id:
                continue
            selected = (child.get("selected") or "").lower()
            if selected == "true":
                ops.append(TailoringOp(rule_id=rule_id, action="select"))
            elif selected == "false":
                ops.append(TailoringOp(rule_id=rule_id, action="disable"))
        elif local == "set-value":
            rule_id = child.get("idref") or ""
            if not rule_id:
                continue
            value = child.text or ""
            ops.append(TailoringOp(rule_id=rule_id, action="set_value", value=value))

    return ParsedTailoring(profile_id=profile_id, ops=ops)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_verify_tailoring_drift.py -v
```

Expected: PASS, all 8 tests.

- [ ] **Step 5: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 467 passed.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/verify/tailoring_drift.py tests/test_verify_tailoring_drift.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(verify): parse_tailoring_xml — round-trips build_tailoring_xml output"
```

---

### Task 6: `compare_tailorings` — TDD

**Files:**
- Modify: `src/ks_gen/verify/tailoring_drift.py` (add function)
- Modify: `tests/test_verify_tailoring_drift.py` (add tests)

Keys ops by `(action, rule_id)`. Same key + different value → `OpChange` (only meaningful for `set_value`). Key on expected only → `added`. Key on deployed only → `removed`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_verify_tailoring_drift.py`:

```python
from ks_gen.verify.tailoring_drift import OpChange, compare_tailorings


def _parsed(profile: str, ops: list[TailoringOp]) -> ParsedTailoring:
    return ParsedTailoring(profile_id=profile, ops=ops)


def test_compare_clean_no_drift() -> None:
    ops = [TailoringOp("r1", "disable"), TailoringOp("r2", "select")]
    report = compare_tailorings(_parsed("p", ops), _parsed("p", ops))
    assert report.added == []
    assert report.removed == []
    assert report.changed == []
    assert report.profile_id_expected == report.profile_id_deployed == "p"


def test_compare_added_only() -> None:
    expected = _parsed("p", [TailoringOp("r1", "disable"), TailoringOp("r2", "disable")])
    deployed = _parsed("p", [TailoringOp("r1", "disable")])
    report = compare_tailorings(expected, deployed)
    assert report.added == [TailoringOp("r2", "disable")]
    assert report.removed == []
    assert report.changed == []


def test_compare_removed_only() -> None:
    expected = _parsed("p", [TailoringOp("r1", "disable")])
    deployed = _parsed("p", [TailoringOp("r1", "disable"), TailoringOp("r2", "disable")])
    report = compare_tailorings(expected, deployed)
    assert report.added == []
    assert report.removed == [TailoringOp("r2", "disable")]
    assert report.changed == []


def test_compare_changed_set_value() -> None:
    expected = _parsed("p", [TailoringOp("r1", "set_value", "24")])
    deployed = _parsed("p", [TailoringOp("r1", "set_value", "5")])
    report = compare_tailorings(expected, deployed)
    assert report.added == []
    assert report.removed == []
    assert report.changed == [
        OpChange(rule_id="r1", action="set_value", expected_value="24", deployed_value="5")
    ]


def test_compare_select_to_disable_is_two_changes_not_one() -> None:
    """Action is part of the op identity, so a flip surfaces as remove+add."""
    expected = _parsed("p", [TailoringOp("r1", "select")])
    deployed = _parsed("p", [TailoringOp("r1", "disable")])
    report = compare_tailorings(expected, deployed)
    assert report.added == [TailoringOp("r1", "select")]
    assert report.removed == [TailoringOp("r1", "disable")]
    assert report.changed == []


def test_compare_profile_id_mismatch_with_no_op_drift() -> None:
    ops = [TailoringOp("r1", "disable")]
    report = compare_tailorings(_parsed("p1", ops), _parsed("p2", ops))
    assert report.profile_id_expected == "p1"
    assert report.profile_id_deployed == "p2"
    assert report.added == []
    assert report.removed == []
    assert report.changed == []


def test_compare_all_four_categories_simultaneously() -> None:
    expected = _parsed(
        "p1",
        [
            TailoringOp("r_added", "disable"),
            TailoringOp("r_changed", "set_value", "24"),
            TailoringOp("r_same", "select"),
        ],
    )
    deployed = _parsed(
        "p2",
        [
            TailoringOp("r_removed", "disable"),
            TailoringOp("r_changed", "set_value", "5"),
            TailoringOp("r_same", "select"),
        ],
    )
    report = compare_tailorings(expected, deployed)
    assert report.added == [TailoringOp("r_added", "disable")]
    assert report.removed == [TailoringOp("r_removed", "disable")]
    assert report.changed == [
        OpChange(rule_id="r_changed", action="set_value", expected_value="24", deployed_value="5")
    ]
    assert report.profile_id_expected == "p1"
    assert report.profile_id_deployed == "p2"


def test_compare_results_sorted_by_rule_id() -> None:
    expected = _parsed(
        "p",
        [TailoringOp("rule_z", "disable"), TailoringOp("rule_a", "disable")],
    )
    deployed = _parsed("p", [])
    report = compare_tailorings(expected, deployed)
    assert [op.rule_id for op in report.added] == ["rule_a", "rule_z"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_verify_tailoring_drift.py -v
```

Expected: 8 new tests FAIL with `ImportError: cannot import name 'compare_tailorings'`.

- [ ] **Step 3: Implement `compare_tailorings`**

Append to `src/ks_gen/verify/tailoring_drift.py`:

```python
def compare_tailorings(
    expected: ParsedTailoring,
    deployed: ParsedTailoring,
) -> TailoringDriftReport:
    """Pure diff between two parsed tailorings.

    Ops are keyed by `(action, rule_id)`. Same key on both sides with a
    different value → `OpChange` (only set_value carries a meaningful value).
    Key in expected only → `added`. Key in deployed only → `removed`.

    Returned lists are sorted by rule_id for stable rendering.
    """
    expected_map = {(op.action, op.rule_id): op for op in expected.ops}
    deployed_map = {(op.action, op.rule_id): op for op in deployed.ops}

    added: list[TailoringOp] = []
    removed: list[TailoringOp] = []
    changed: list[OpChange] = []

    for key, op in expected_map.items():
        if key not in deployed_map:
            added.append(op)
        else:
            other = deployed_map[key]
            if op.action == "set_value" and (op.value or "") != (other.value or ""):
                changed.append(
                    OpChange(
                        rule_id=op.rule_id,
                        action="set_value",
                        expected_value=op.value or "",
                        deployed_value=other.value or "",
                    )
                )

    for key, op in deployed_map.items():
        if key not in expected_map:
            removed.append(op)

    added.sort(key=lambda o: o.rule_id)
    removed.sort(key=lambda o: o.rule_id)
    changed.sort(key=lambda c: c.rule_id)

    return TailoringDriftReport(
        profile_id_expected=expected.profile_id,
        profile_id_deployed=deployed.profile_id,
        added=added,
        removed=removed,
        changed=changed,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_verify_tailoring_drift.py -v
```

Expected: PASS, 16 tests total.

- [ ] **Step 5: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 475 passed.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/verify/tailoring_drift.py tests/test_verify_tailoring_drift.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(verify): compare_tailorings — pure (added/removed/changed) diff"
```

---

### Task 7: `render_drift_section` — TDD

**Files:**
- Modify: `src/ks_gen/verify/tailoring_drift.py` (add function)
- Modify: `tests/test_verify_tailoring_drift.py` (add tests)

Returns plain-text human-readable section. Empty string when there's no drift to render.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_verify_tailoring_drift.py`:

```python
from ks_gen.verify.tailoring_drift import render_drift_section


def test_render_empty_drift_returns_empty_string() -> None:
    report = TailoringDriftReport(
        profile_id_expected="p",
        profile_id_deployed="p",
        added=[],
        removed=[],
        changed=[],
    )
    assert render_drift_section(report) == ""


def test_render_added_only() -> None:
    report = TailoringDriftReport(
        profile_id_expected="p",
        profile_id_deployed="p",
        added=[TailoringOp("rule_x", "disable")],
        removed=[],
        changed=[],
    )
    out = render_drift_section(report)
    assert "Tailoring drift detected" in out
    assert "+ disable rule_x" in out


def test_render_removed_only_uses_minus_glyph() -> None:
    report = TailoringDriftReport(
        profile_id_expected="p",
        profile_id_deployed="p",
        added=[],
        removed=[TailoringOp("rule_y", "select")],
        changed=[],
    )
    out = render_drift_section(report)
    assert "- select rule_y" in out


def test_render_changed_uses_tilde_with_arrow() -> None:
    report = TailoringDriftReport(
        profile_id_expected="p",
        profile_id_deployed="p",
        added=[],
        removed=[],
        changed=[
            OpChange(rule_id="rule_z", action="set_value", expected_value="24", deployed_value="5")
        ],
    )
    out = render_drift_section(report)
    assert "~ rule_z: 5 → 24" in out


def test_render_profile_mismatch_adds_profile_changed_line() -> None:
    report = TailoringDriftReport(
        profile_id_expected="profile_a",
        profile_id_deployed="profile_b",
        added=[],
        removed=[],
        changed=[],
    )
    out = render_drift_section(report)
    assert "(profile changed: profile_b → profile_a)" in out


def test_render_profile_mismatch_alone_is_not_empty() -> None:
    """profile_id-only drift still produces a non-empty section."""
    report = TailoringDriftReport(
        profile_id_expected="profile_a",
        profile_id_deployed="profile_b",
        added=[],
        removed=[],
        changed=[],
    )
    assert render_drift_section(report) != ""


def test_render_all_four_categories_present() -> None:
    report = TailoringDriftReport(
        profile_id_expected="p1",
        profile_id_deployed="p2",
        added=[TailoringOp("r_a", "disable")],
        removed=[TailoringOp("r_r", "disable")],
        changed=[
            OpChange(rule_id="r_c", action="set_value", expected_value="24", deployed_value="5")
        ],
    )
    out = render_drift_section(report)
    assert "+ disable r_a" in out
    assert "- disable r_r" in out
    assert "~ r_c: 5 → 24" in out
    assert "(profile changed: p2 → p1)" in out
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_verify_tailoring_drift.py -v
```

Expected: 7 new tests FAIL with `ImportError: cannot import name 'render_drift_section'`.

- [ ] **Step 3: Implement `render_drift_section`**

Append to `src/ks_gen/verify/tailoring_drift.py`:

```python
def _has_any_drift(report: TailoringDriftReport) -> bool:
    return bool(report.added or report.removed or report.changed) or (
        report.profile_id_expected != report.profile_id_deployed
    )


def render_drift_section(report: TailoringDriftReport) -> str:
    """Human-readable drift section for the verify text report.

    Returns empty string when there is no drift to render — caller doesn't
    have to gate on `has_tailoring_drift`. Glyph legend: `+` added (expected
    only), `-` removed (deployed only), `~` changed (set_value delta). The
    `(profile changed: ...)` line appears only when profile_ids differ.
    """
    if not _has_any_drift(report):
        return ""

    lines: list[str] = [
        "Tailoring drift detected — workstation host.yaml differs from /root/tailoring.xml.",
        "Re-run `ks-gen gen <host.yaml>` and redeploy to align.",
        "",
    ]
    for op in report.added:
        lines.append(f"  + {op.action} {op.rule_id}")
    for op in report.removed:
        lines.append(f"  - {op.action} {op.rule_id}")
    for change in report.changed:
        lines.append(
            f"  ~ {change.rule_id}: {change.deployed_value} → {change.expected_value}"
        )
    if report.profile_id_expected != report.profile_id_deployed:
        lines.append(
            f"  (profile changed: {report.profile_id_deployed} → "
            f"{report.profile_id_expected})"
        )

    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_verify_tailoring_drift.py -v
```

Expected: PASS, 23 tests total.

- [ ] **Step 5: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 482 passed.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/verify/tailoring_drift.py tests/test_verify_tailoring_drift.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(verify): render_drift_section — text drift section for verify report"
```

---

### Task 8: Add `tailoring_drift` field + `has_tailoring_drift` property to `VerifyReport`

**Files:**
- Modify: `src/ks_gen/verify/reconcile.py:43-53` (extend `VerifyReport`)
- Modify: `tests/test_verify_reconcile.py` (add tests)

Default `None` keeps every existing caller backward-compatible.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_verify_reconcile.py`:

```python
def test_verify_report_tailoring_drift_defaults_to_none() -> None:
    from ks_gen.verify.reconcile import VerifyReport

    report = VerifyReport(
        host="h",
        user="u",
        timestamp_utc="2026-06-09T00:00:00Z",
        rows=(),
        install_baseline_available=True,
    )
    assert report.tailoring_drift is None
    assert report.has_tailoring_drift is False


def test_verify_report_has_tailoring_drift_false_when_empty_drift_attached() -> None:
    from ks_gen.verify.reconcile import VerifyReport
    from ks_gen.verify.tailoring_drift import TailoringDriftReport

    drift = TailoringDriftReport(
        profile_id_expected="p",
        profile_id_deployed="p",
        added=[],
        removed=[],
        changed=[],
    )
    report = VerifyReport(
        host="h",
        user="u",
        timestamp_utc="2026-06-09T00:00:00Z",
        rows=(),
        install_baseline_available=True,
        tailoring_drift=drift,
    )
    assert report.tailoring_drift is drift
    assert report.has_tailoring_drift is False


def test_verify_report_has_tailoring_drift_true_when_changes_present() -> None:
    from ks_gen.rules._types import TailoringOp
    from ks_gen.verify.reconcile import VerifyReport
    from ks_gen.verify.tailoring_drift import TailoringDriftReport

    drift = TailoringDriftReport(
        profile_id_expected="p",
        profile_id_deployed="p",
        added=[TailoringOp("r1", "disable")],
        removed=[],
        changed=[],
    )
    report = VerifyReport(
        host="h",
        user="u",
        timestamp_utc="2026-06-09T00:00:00Z",
        rows=(),
        install_baseline_available=True,
        tailoring_drift=drift,
    )
    assert report.has_tailoring_drift is True


def test_verify_report_has_tailoring_drift_true_on_profile_id_mismatch_alone() -> None:
    from ks_gen.verify.reconcile import VerifyReport
    from ks_gen.verify.tailoring_drift import TailoringDriftReport

    drift = TailoringDriftReport(
        profile_id_expected="p1",
        profile_id_deployed="p2",
        added=[],
        removed=[],
        changed=[],
    )
    report = VerifyReport(
        host="h",
        user="u",
        timestamp_utc="2026-06-09T00:00:00Z",
        rows=(),
        install_baseline_available=True,
        tailoring_drift=drift,
    )
    assert report.has_tailoring_drift is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_verify_reconcile.py -v -k tailoring_drift
```

Expected: 4 tests FAIL — `tailoring_drift` is not a field on `VerifyReport`.

- [ ] **Step 3: Extend `VerifyReport`**

Edit `src/ks_gen/verify/reconcile.py`. Add the import and the field+property. The new `VerifyReport` block is:

```python
from ks_gen.verify.tailoring_drift import TailoringDriftReport


@dataclass(frozen=True)
class VerifyReport:
    host: str
    user: str
    timestamp_utc: str
    rows: tuple[VerifyRow, ...]
    install_baseline_available: bool
    tailoring_drift: TailoringDriftReport | None = None

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

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_verify_reconcile.py -v -k tailoring_drift
```

Expected: 4 tests PASS.

- [ ] **Step 5: Confirm existing reconcile / report tests still pass**

```bash
pytest tests/test_verify_reconcile.py tests/test_verify_report.py tests/test_verify_run.py -q
```

Expected: all green; the default-None field doesn't break existing constructors.

- [ ] **Step 6: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 486 passed.

- [ ] **Step 7: Commit**

```bash
git add src/ks_gen/verify/reconcile.py tests/test_verify_reconcile.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(verify): VerifyReport gains tailoring_drift field + has_tailoring_drift"
```

---

### Task 9: `collect_deployed_tailoring` in `verify/remote.py`

**Files:**
- Modify: `src/ks_gen/verify/remote.py` (append function)
- Modify: `tests/test_verify_remote.py` (add tests)

Sibling to `collect_arfs`. Doesn't share state with it. Failures raise existing error classes.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_verify_remote.py`:

```python
from ks_gen.verify.remote import collect_deployed_tailoring


def test_collect_deployed_tailoring_pulls_and_returns_text(tmp_path: Path) -> None:
    pulled: dict[str, object] = {}

    def fake_ssh(host: str, user: str, cmd: str, **kw: object) -> SshResult:
        if cmd == "sudo -n true":
            return SshResult("", "", 0)
        if cmd == "sudo -n test -r /root/tailoring.xml":
            return SshResult("", "", 0)
        raise AssertionError(f"unexpected ssh cmd: {cmd}")

    def fake_scp(host: str, user: str, remote: str, local: Path, **kw: object) -> None:
        pulled["remote"] = remote
        local.write_text("<xccdf:Tailoring/>", encoding="utf-8")

    with (
        patch("ks_gen.verify.remote.ssh_exec", side_effect=fake_ssh),
        patch("ks_gen.verify.remote.scp_pull", side_effect=fake_scp),
    ):
        text = collect_deployed_tailoring(
            host="h", user="u", workdir=tmp_path, ssh_extra_opts=[]
        )

    assert pulled["remote"] == "/root/tailoring.xml"
    assert text == "<xccdf:Tailoring/>"


def test_collect_deployed_tailoring_raises_when_file_missing(tmp_path: Path) -> None:
    def fake_ssh(host: str, user: str, cmd: str, **kw: object) -> SshResult:
        if cmd == "sudo -n true":
            return SshResult("", "", 0)
        if cmd == "sudo -n test -r /root/tailoring.xml":
            return SshResult("", "", 1)
        raise AssertionError(f"unexpected ssh cmd: {cmd}")

    with (
        patch("ks_gen.verify.remote.ssh_exec", side_effect=fake_ssh),
        pytest.raises(OscapInvocationError, match="install-time tailoring"),
    ):
        collect_deployed_tailoring(host="h", user="u", workdir=tmp_path, ssh_extra_opts=[])


def test_collect_deployed_tailoring_raises_when_pulled_file_empty(tmp_path: Path) -> None:
    def fake_ssh(host: str, user: str, cmd: str, **kw: object) -> SshResult:
        if cmd == "sudo -n true":
            return SshResult("", "", 0)
        if cmd == "sudo -n test -r /root/tailoring.xml":
            return SshResult("", "", 0)
        raise AssertionError(f"unexpected ssh cmd: {cmd}")

    def fake_scp(host: str, user: str, remote: str, local: Path, **kw: object) -> None:
        local.write_text("", encoding="utf-8")

    with (
        patch("ks_gen.verify.remote.ssh_exec", side_effect=fake_ssh),
        patch("ks_gen.verify.remote.scp_pull", side_effect=fake_scp),
        pytest.raises(ArfMissingError, match="empty"),
    ):
        collect_deployed_tailoring(host="h", user="u", workdir=tmp_path, ssh_extra_opts=[])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_verify_remote.py -v -k collect_deployed_tailoring
```

Expected: 3 FAIL with `ImportError: cannot import name 'collect_deployed_tailoring'`.

- [ ] **Step 3: Implement `collect_deployed_tailoring`**

Append to `src/ks_gen/verify/remote.py`:

```python
def collect_deployed_tailoring(
    *,
    host: str,
    user: str,
    workdir: Path,
    ssh_extra_opts: list[str],
) -> str:
    """scp-pull `/root/tailoring.xml` for drift comparison.

    Sibling to `collect_arfs`. Does not share state with the ARF pull —
    `--check-tailoring` and `--no-drift` are independent axes.

    Returns the file's text contents.

    Raises:
        SudoPromptError: passwordless sudo unavailable.
        OscapInvocationError: `/root/tailoring.xml` not readable on host.
        ArfMissingError: scp succeeded but the pulled file is 0 bytes.
        SshConnectError: ssh/scp transport failure.
        ToolMissingError: ssh/scp not on PATH.
    """
    probe_sudo(host, user, ssh_extra_opts=ssh_extra_opts)

    check = ssh_exec(
        host, user, f"sudo -n test -r {REMOTE_TAILORING}", extra_opts=ssh_extra_opts
    )
    if check.exit_code != 0:
        raise OscapInvocationError(
            f"install-time tailoring not present at {REMOTE_TAILORING} "
            f"— host may not have been provisioned by ks-gen"
        )

    local = workdir / "deployed-tailoring.xml"
    scp_pull(host, user, REMOTE_TAILORING, local, extra_opts=ssh_extra_opts)
    if not local.exists() or local.stat().st_size == 0:
        raise ArfMissingError(f"pulled tailoring is empty or missing: {local}")
    return local.read_text(encoding="utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_verify_remote.py -v -k collect_deployed_tailoring
```

Expected: 3 PASS.

- [ ] **Step 5: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 489 passed.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/verify/remote.py tests/test_verify_remote.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(verify): collect_deployed_tailoring — scp-pull /root/tailoring.xml"
```

---

### Task 10: Thread `check_tailoring` through `run_verify`

**Files:**
- Modify: `src/ks_gen/verify/__init__.py` (extend `run_verify`)
- Modify: `tests/test_verify_run.py` (add tests)

When `check_tailoring=True`, pull deployed tailoring (fail fast), re-render expected via `render_tailoring`, parse both, compare, attach to report.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_verify_run.py`:

```python
def test_run_verify_check_tailoring_false_leaves_field_none(tmp_path: Path) -> None:
    from ks_gen.verify import run_verify
    from ks_gen.verify.remote import CollectedArfs

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
            check_tailoring=False,
            ssh_extra_opts=[],
            timeout=600,
        )

    assert report.tailoring_drift is None


def test_run_verify_check_tailoring_true_attaches_drift_report(tmp_path: Path) -> None:
    from ks_gen.tailoring import build_tailoring_xml
    from ks_gen.verify import run_verify
    from ks_gen.verify.remote import CollectedArfs

    current = (FIXTURES / "arf-clean.xml").read_text(encoding="utf-8")
    # Hand-craft a "deployed" tailoring with an extra disable op — drift.
    deployed_xml = build_tailoring_xml(
        [
            __import__("ks_gen.rules._types", fromlist=["TailoringOp"]).TailoringOp(
                rule_id="xccdf_org.ssgproject.content_rule_synthetic_drift",
                action="disable",
            )
        ],
        profile_id="xccdf_org.ssgproject.content_profile_stig",
    )

    with (
        patch(
            "ks_gen.verify.collect_arfs",
            return_value=CollectedArfs(current_text=current, install_text=None),
        ),
        patch(
            "ks_gen.verify.collect_deployed_tailoring",
            return_value=deployed_xml,
        ),
    ):
        report = run_verify(
            cfg=_cfg(),
            host="h",
            user="ops",
            workdir=tmp_path,
            no_drift=True,
            check_tailoring=True,
            ssh_extra_opts=[],
            timeout=600,
        )

    assert report.tailoring_drift is not None
    # The synthetic_drift rule is in deployed but not expected → removed.
    assert any(
        op.rule_id == "xccdf_org.ssgproject.content_rule_synthetic_drift"
        for op in report.tailoring_drift.removed
    )
    assert report.has_tailoring_drift is True


def test_run_verify_check_tailoring_true_clean_when_matching(tmp_path: Path) -> None:
    from ks_gen.verify import run_verify
    from ks_gen.verify.remote import CollectedArfs
    from ks_gen.writer import render_tailoring

    cfg = _cfg()
    current = (FIXTURES / "arf-clean.xml").read_text(encoding="utf-8")
    deployed_xml = render_tailoring(cfg)

    with (
        patch(
            "ks_gen.verify.collect_arfs",
            return_value=CollectedArfs(current_text=current, install_text=None),
        ),
        patch(
            "ks_gen.verify.collect_deployed_tailoring",
            return_value=deployed_xml,
        ),
    ):
        report = run_verify(
            cfg=cfg,
            host="h",
            user="ops",
            workdir=tmp_path,
            no_drift=True,
            check_tailoring=True,
            ssh_extra_opts=[],
            timeout=600,
        )

    assert report.tailoring_drift is not None
    assert report.has_tailoring_drift is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_verify_run.py -v -k check_tailoring
```

Expected: 3 FAIL — `check_tailoring` is not a parameter of `run_verify`.

- [ ] **Step 3: Extend `run_verify`**

Edit `src/ks_gen/verify/__init__.py`. Full new content:

```python
"""Post-install host verification — re-run oscap, reconcile against host.yaml."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from ks_gen.config import HostConfig
from ks_gen.exceptions_report import expected_failure_rule_ids
from ks_gen.verify.arf import parse_arf
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

    Returns:
        A VerifyReport. Use `report.is_clean` for compliance and
        `report.has_tailoring_drift` for intent-vs-deployed drift.

    Raises:
        SudoPromptError, OscapInvocationError, ArfMissingError, ArfParseError,
        SshConnectError, ToolMissingError: same as v0.8.0.
        TailoringParseError: malformed deployed or re-rendered tailoring XML
            (only when `check_tailoring=True`). Message names the side.
    """
    extra_opts = ssh_extra_opts or []

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
        no_drift=no_drift,
        ssh_extra_opts=extra_opts,
        timeout=timeout,
    )
    current = parse_arf(arfs.current_text)
    install = parse_arf(arfs.install_text) if arfs.install_text is not None else None
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = build_report(
        current=current,
        install=install,
        expected_failures=expected,
        host=host,
        user=user,
        timestamp_utc=timestamp,
    )
    if tailoring_drift is not None:
        # VerifyReport is frozen — rebuild with the new field.
        report = replace(report, tailoring_drift=tailoring_drift)
    return report


__all__ = ["VerifyReport", "run_verify"]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_verify_run.py -v
```

Expected: all PASS (existing + 3 new).

- [ ] **Step 5: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 492 passed.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/verify/__init__.py tests/test_verify_run.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(verify): run_verify gains check_tailoring=True path"
```

---

### Task 11: `render_table` and `render_json` surface the drift section

**Files:**
- Modify: `src/ks_gen/verify/report.py` (append drift to both renderers)
- Modify: `tests/test_verify_report.py` (add tests + syrupy snapshots)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_verify_report.py`:

```python
def test_render_table_appends_drift_section_when_present(snapshot) -> None:
    from ks_gen.rules._types import TailoringOp
    from ks_gen.verify.reconcile import VerifyReport, VerifyRow
    from ks_gen.verify.report import render_table
    from ks_gen.verify.tailoring_drift import OpChange, TailoringDriftReport

    drift = TailoringDriftReport(
        profile_id_expected="profile_a",
        profile_id_deployed="profile_b",
        added=[TailoringOp("rule_x", "disable")],
        removed=[TailoringOp("rule_y", "select")],
        changed=[
            OpChange(rule_id="rule_z", action="set_value", expected_value="24", deployed_value="5")
        ],
    )
    report = VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(
            VerifyRow("rule_b", "fail", "pass", False, "regression"),
        ),
        install_baseline_available=True,
        tailoring_drift=drift,
    )
    out = render_table(report)
    assert out == snapshot


def test_render_table_no_drift_section_when_drift_none() -> None:
    from ks_gen.verify.reconcile import VerifyReport
    from ks_gen.verify.report import render_table

    report = VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(),
        install_baseline_available=True,
    )
    assert "Tailoring drift" not in render_table(report)


def test_render_json_includes_tailoring_drift_when_present(snapshot) -> None:
    from ks_gen.rules._types import TailoringOp
    from ks_gen.verify.reconcile import VerifyReport
    from ks_gen.verify.report import render_json
    from ks_gen.verify.tailoring_drift import OpChange, TailoringDriftReport

    drift = TailoringDriftReport(
        profile_id_expected="profile_a",
        profile_id_deployed="profile_b",
        added=[TailoringOp("rule_x", "disable")],
        removed=[TailoringOp("rule_y", "select")],
        changed=[
            OpChange(rule_id="rule_z", action="set_value", expected_value="24", deployed_value="5")
        ],
    )
    report = VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(),
        install_baseline_available=True,
        tailoring_drift=drift,
    )
    assert render_json(report) == snapshot


def test_render_json_no_tailoring_drift_key_when_field_is_none() -> None:
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
    assert "tailoring_drift" not in payload
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_verify_report.py -v -k tailoring_drift
```

Expected: 4 FAIL — snapshot/JSON keys missing, drift section not appended.

- [ ] **Step 3: Update both renderers**

Edit `src/ks_gen/verify/report.py`. Add `render_drift_section` import and append the drift logic. Full new file:

```python
from __future__ import annotations

import json
from collections import Counter

from ks_gen.verify.reconcile import VerifyReport
from ks_gen.verify.suggest import Suggestion, render_yaml
from ks_gen.verify.tailoring_drift import render_drift_section


def _summary(report: VerifyReport) -> dict[str, int]:
    counts: Counter[str] = Counter(r.category for r in report.rows)
    return {
        "clean": counts.get("clean", 0),
        "expected_fail": counts.get("expected_fail", 0),
        "new_fail": counts.get("new_fail", 0),
        "regression": counts.get("regression", 0),
        "incomplete": counts.get("incomplete", 0),
    }


def render_table(report: VerifyReport, *, suggestions: list[Suggestion] | None = None) -> str:
    """Plain-text report. Omits `clean` rows by default to keep output focused.

    When `suggestions` is a non-None list (including empty), appends a
    rendered suggestions block via `render_yaml`. None means "operator
    didn't ask for suggestions" and that section is omitted.

    When `report.tailoring_drift` is populated and non-empty, appends a
    drift section between the table and any suggestions block.
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
        header = f"  {'CATEGORY':<{cat_w}}  {'CURRENT':<{cur_w}}  {'INSTALL':<{inst_w}}  EXP  RULE"
        lines.append(header)
        for r in visible:
            inst = r.install if r.install is not None else "-"
            exp = "yes" if r.expected else "no "
            cat = f"{r.category:<{cat_w}}"
            cur = f"{r.current:<{cur_w}}"
            instc = f"{inst:<{inst_w}}"
            rule = f"{r.rule_id:<{rule_w}}"
            lines.append(f"  {cat}  {cur}  {instc}  {exp}  {rule}")
        base = "\n".join(lines) + "\n"

    if report.tailoring_drift is not None:
        drift_section = render_drift_section(report.tailoring_drift)
        if drift_section:
            base = base + "\n" + drift_section

    if suggestions is None:
        return base
    suggestion_block = render_yaml(suggestions, report)
    if not suggestion_block:
        return base
    return base + "\n" + suggestion_block


def render_json(report: VerifyReport, *, suggestions: list[Suggestion] | None = None) -> str:
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
            {"category": s.category, "decl": s.decl.model_dump()} for s in suggestions
        ]
    drift = report.tailoring_drift
    if drift is not None:
        payload["tailoring_drift"] = {
            "profile_id_expected": drift.profile_id_expected,
            "profile_id_deployed": drift.profile_id_deployed,
            "added": [
                {"action": op.action, "rule_id": op.rule_id, "value": op.value}
                for op in drift.added
            ],
            "removed": [
                {"action": op.action, "rule_id": op.rule_id, "value": op.value}
                for op in drift.removed
            ],
            "changed": [
                {
                    "rule_id": c.rule_id,
                    "action": c.action,
                    "expected_value": c.expected_value,
                    "deployed_value": c.deployed_value,
                }
                for c in drift.changed
            ],
        }
    return json.dumps(payload, indent=2)
```

- [ ] **Step 4: Regenerate the new snapshots**

```bash
pytest tests/test_verify_report.py -k tailoring_drift --snapshot-update
```

- [ ] **Step 5: Re-run tests to verify they pass**

```bash
pytest tests/test_verify_report.py -v
```

Expected: PASS — existing snapshots untouched, two new snapshots added.

- [ ] **Step 6: Inspect the new snapshots**

```bash
git diff tests/__snapshots__/test_verify_report.ambr
```

Expected: two new snapshot entries appended; no existing snapshot modified. Confirm the drift section formatting matches the design and that the JSON includes `tailoring_drift`.

- [ ] **Step 7: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 496 passed.

- [ ] **Step 8: Commit**

```bash
git add src/ks_gen/verify/report.py tests/test_verify_report.py tests/__snapshots__/test_verify_report.ambr
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(verify): render_table/render_json surface tailoring drift section"
```

---

### Task 12: CLI `--check-tailoring` flag + exit-code priority

**Files:**
- Modify: `src/ks_gen/cli.py:174-310` (verify command)
- Modify: `tests/test_cli/test_verify.py` (add tests)

Priority order (most-severe wins): transport/tool errors → config errors → `VERIFY_FAIL` (compliance fail) → `TAILORING_DRIFT` (drift only) → `OK`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli/test_verify.py`:

```python
def _clean_with_drift() -> VerifyReport:
    """Clean compliance, but tailoring drift present."""
    from ks_gen.rules._types import TailoringOp
    from ks_gen.verify.tailoring_drift import TailoringDriftReport

    drift = TailoringDriftReport(
        profile_id_expected="p",
        profile_id_deployed="p",
        added=[TailoringOp("synthetic_rule", "disable")],
        removed=[],
        changed=[],
    )
    return VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(VerifyRow("rule_a", "pass", "pass", False, "clean"),),
        install_baseline_available=True,
        tailoring_drift=drift,
    )


def _failing_with_drift() -> VerifyReport:
    """Compliance fail AND drift — compliance wins."""
    from ks_gen.rules._types import TailoringOp
    from ks_gen.verify.tailoring_drift import TailoringDriftReport

    drift = TailoringDriftReport(
        profile_id_expected="p",
        profile_id_deployed="p",
        added=[TailoringOp("synthetic_rule", "disable")],
        removed=[],
        changed=[],
    )
    return VerifyReport(
        host="h1",
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=(VerifyRow("rule_b", "fail", "pass", False, "regression"),),
        install_baseline_available=True,
        tailoring_drift=drift,
    )


def test_verify_check_tailoring_flag_threads_through(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
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
            app, ["verify", "--host", "h1", "--config", str(cfg), "--check-tailoring"]
        )
    assert result.exit_code == 0, result.output
    assert captured["check_tailoring"] is True


def test_verify_check_tailoring_default_false_when_flag_absent(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    captured: dict[str, object] = {}

    def fake_run_verify(**kwargs: object) -> VerifyReport:
        captured.update(kwargs)
        return _clean_report()

    with (
        patch("ks_gen.cli.run_verify", side_effect=fake_run_verify),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(app, ["verify", "--host", "h1", "--config", str(cfg)])
    assert result.exit_code == 0, result.output
    assert captured["check_tailoring"] is False


def test_verify_exits_8_on_drift_only(tmp_path: Path) -> None:
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with (
        patch("ks_gen.cli.run_verify", return_value=_clean_with_drift()),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(
            app, ["verify", "--host", "h1", "--config", str(cfg), "--check-tailoring"]
        )
    assert result.exit_code == 8, result.output


def test_verify_compliance_fail_wins_over_drift(tmp_path: Path) -> None:
    """When both compliance fail and drift, exit 6 (VERIFY_FAIL) — not 8."""
    cfg = _write_cfg(tmp_path)
    runner = CliRunner()
    with (
        patch("ks_gen.cli.run_verify", return_value=_failing_with_drift()),
        patch("ks_gen.cli.check_tools"),
    ):
        result = runner.invoke(
            app, ["verify", "--host", "h1", "--config", str(cfg), "--check-tailoring"]
        )
    assert result.exit_code == 6, result.output
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_cli/test_verify.py -v -k tailoring
```

Expected: 4 FAIL — `--check-tailoring` flag unknown, exit codes wrong.

- [ ] **Step 3: Add the flag + thread + bump exit-code priority**

Edit `src/ks_gen/cli.py`. Two changes inside `verify_cmd`:

(a) Add a new `typer.Option` parameter `check_tailoring`. Insert it in the parameter list immediately after `no_drift` (around `cli.py:204`). The new parameter declaration:

```python
    check_tailoring: bool = typer.Option(
        False,
        "--check-tailoring",
        help=(
            "Re-render the expected tailoring locally and diff against the host's "
            "/root/tailoring.xml. Reports drift as a separate section; exit 8 if "
            "drift is detected and compliance is otherwise clean."
        ),
    ),
```

(b) Pass it through to `run_verify` and adjust the `_do` exit logic. The `run_verify` call site (around `cli.py:259-267`) becomes:

```python
            report = run_verify(
                cfg=cfg,
                host=host,
                user=resolved_user,
                workdir=workdir,
                no_drift=no_drift,
                check_tailoring=check_tailoring,
                ssh_extra_opts=extra_opts,
                timeout=timeout,
            )
```

And the final exit block (around `cli.py:299-300`) becomes:

```python
        if not report.is_clean:
            raise typer.Exit(code=int(ExitCode.VERIFY_FAIL))
        if report.has_tailoring_drift:
            raise typer.Exit(code=int(ExitCode.TAILORING_DRIFT))
```

The order matters: compliance fail must short-circuit before the drift check so `VERIFY_FAIL` wins. The default `typer.Exit(0)` is implicit when neither raises.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_cli/test_verify.py -v
```

Expected: PASS (existing + 4 new).

- [ ] **Step 5: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 500 passed.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/cli.py tests/test_cli/test_verify.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(cli): verify --check-tailoring flag + TAILORING_DRIFT exit code priority"
```

---

### Task 13: MANUAL.md §8.5 + README sentence

**Files:**
- Modify: `MANUAL.md` (add §8.5 subsection — choose insertion point peer to `--suggest-exceptions`)
- Modify: `README.md` (one sentence)

- [ ] **Step 1: Locate the existing verify subsection in MANUAL.md**

```bash
grep -n "verify" MANUAL.md | head -20
grep -n "suggest-exceptions" MANUAL.md | head -5
```

Identify the heading for the `--suggest-exceptions` subsection (added in v0.8.0 commit `a58b077`). The new `--check-tailoring` subsection goes immediately after it, peer-level.

- [ ] **Step 2: Add the new MANUAL.md subsection**

Insert after the `--suggest-exceptions` subsection (whatever heading level it uses — match it):

```markdown
### Detecting tailoring drift

`ks-gen verify --check-tailoring` re-renders the tailoring locally from
the workstation `host.yaml` and diffs it against `/root/tailoring.xml`
on the deployed host. Use this when you've edited `host.yaml` after
install and want to confirm the change hasn't been deployed yet.

Drift is reported as a per-op diff:

```
Tailoring drift detected — workstation host.yaml differs from /root/tailoring.xml.
Re-run `ks-gen gen <host.yaml>` and redeploy to align.

  + disable xccdf_org.ssgproject.content_rule_grub2_audit_argument
  - disable xccdf_org.ssgproject.content_rule_package_telnet_removed
  ~ xccdf_org.ssgproject.content_value_var_password_pam_unix_remember: 5 → 24
```

Glyphs: `+` op present in expected but not deployed, `-` present in
deployed but not expected, `~` set-value differs (shown as
`deployed → expected`).

**Exit codes.** When `--check-tailoring` is set and drift is detected
but compliance is otherwise clean, `verify` exits `8`
(`TAILORING_DRIFT`). Compliance failures (exit `6`) take precedence —
a host with both compliance fail and drift exits `6`. A host with no
drift and clean compliance exits `0`.

**Drift does not mean non-compliant.** The host is still being
measured against the tailoring deployed at install time. The drift
report is about workstation/host divergence — your intent vs the
host's reality. The fix path is `ks-gen gen <host.yaml>` followed by
redeploying the bundle (re-burn ISO, ship updated `tailoring.xml`, etc.
— whatever delivery method you used originally).

**JSON output.** `verify --format json --check-tailoring` adds a
top-level `tailoring_drift` key. The key is omitted (not present) when
the flag isn't set, so consumers can use `key in payload` to detect
whether the check ran.
```

- [ ] **Step 3: Add the README sentence**

In `README.md`, find the `verify` blurb and append one sentence at the end of that paragraph. Locate it:

```bash
grep -n "verify" README.md | head -10
```

Add (matching the surrounding tone — terse):

```markdown
Pass `--check-tailoring` to also diff the deployed `/root/tailoring.xml` against your current `host.yaml` (exit 8 if drift is detected and compliance is otherwise clean).
```

- [ ] **Step 4: Run the local CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 500 passed (docs-only change shouldn't shift the count).

- [ ] **Step 5: Commit**

```bash
git add MANUAL.md README.md
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "docs: verify --check-tailoring — MANUAL §8.5 + README sentence"
```

---

### Task 14: Final integration check + push

**Files:**
- (none — verification + branch push)

- [ ] **Step 1: Re-run the full CI parity chain from a clean slate**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, 500 passed.

- [ ] **Step 2: Confirm commit history**

```bash
git log --oneline ef9c723..HEAD
```

Expected: 13 implementation commits (Tasks 1-13), all signed (`%G?` shows `G` or `U`).

- [ ] **Step 3: Confirm signatures**

```bash
git log --format="%h %G? %s" ef9c723..HEAD
```

Expected: every line starts with the commit hash followed by `G` (good signature) or `U` (good signature, unknown trust). No `N` (no signature).

- [ ] **Step 4: Push the branch**

```bash
git push -u origin impl/v0.9.0-verify-tailoring-drift
```

Expected: branch pushed; if GitHub rejects with `GH007: Your push would publish a private email address`, stop and tell the user — don't fall back to the noreply form silently.

- [ ] **Step 5: Open the PR**

```bash
gh pr create --title "feat(verify): --check-tailoring drift detection (#12)" --body "$(cat <<'EOF'
## Summary

Closes #12. Opt-in `ks-gen verify --check-tailoring` scp-pulls
`/root/tailoring.xml`, re-renders the expected tailoring locally from
the workstation `host.yaml`, and reports a per-op diff (added,
removed, changed `<select>` / `<set-value>` ops, plus profile-id
mismatch as a header-level drift line).

New exit code `TAILORING_DRIFT = 8`, distinct from `VERIFY_FAIL = 6`
so automation can gate on stale tailoring independently from
non-compliance. Compliance failures take precedence: a host with both
exits `6`.

Comparison is semantic (parsed `TailoringOp` round-trip), not byte
hash — `build_tailoring_xml` embeds `datetime.now(UTC)` in the XCCDF
version header so a byte hash would always disagree.

## Test plan

- [ ] Local CI parity green: `ruff check && ruff format --check && mypy && pytest -q`
- [ ] `verify --check-tailoring` against a host whose tailoring matches → exit 0
- [ ] `verify --check-tailoring` against a host with a stale tailoring → exit 8 + per-op diff in output
- [ ] `verify --check-tailoring` against a compliance-failing + drifted host → exit 6 (compliance wins)
- [ ] `verify --format json --check-tailoring` round-trips through `jq` with the `tailoring_drift` key populated
- [ ] `verify` (no flag) — JSON has no `tailoring_drift` key (backward-compatible)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR opened; URL returned. Capture for the release-please loop.

---

## Self-review

After all tasks complete, verify against the spec:

- [ ] **Spec §Goals coverage:**
  - `--check-tailoring` flag → Task 12 ✓
  - `TAILORING_DRIFT = 8` exit code → Task 1 ✓
  - Semantic comparison via TailoringOp → Tasks 4-6 ✓
  - JSON `tailoring_drift` key → Task 11 ✓
  - Single new error class → Task 2 (`TailoringParseError`) ✓
- [ ] **Spec §Architecture coverage:**
  - `verify/tailoring_drift.py` with parse/compare/render → Tasks 4-7 ✓
  - `render_tailoring(cfg)` helper extracted → Task 3 ✓
  - `collect_deployed_tailoring` in remote.py → Task 9 ✓
  - `VerifyReport.tailoring_drift` field + property → Task 8 ✓
  - `run_verify(check_tailoring=...)` integration → Task 10 ✓
- [ ] **Spec §Edge cases — sanity check:**
  - Missing `/root/tailoring.xml` → `OscapInvocationError` → Task 9 test ✓
  - Malformed deployed XML → `TailoringParseError` with side-naming message → Task 10 wrapper ✓
  - Profile-id mismatch only → Task 6 + Task 7 + Task 8 tests ✓
  - Unknown op in deployed → Task 5 forward-compat test ✓
  - Empty set_value → Task 5 test ✓
  - Empty drift attached → Task 8 + Task 11 tests ✓
  - `check_tailoring=True` + `no_drift=True` → independent axes, both pass through `run_verify` ✓
- [ ] **Spec §Documentation:**
  - MANUAL §8.5 → Task 13 ✓
  - README sentence → Task 13 ✓
- [ ] **Spec §Acceptance:**
  - All five acceptance conditions covered by the test plan in Task 14's PR body ✓

No placeholders. No "TBD". Types referenced (`ParsedTailoring`, `OpChange`,
`TailoringDriftReport`, `TailoringOp`, `TailoringParseError`,
`ExitCode.TAILORING_DRIFT`) are all defined in earlier tasks. Function
names match across tasks (`parse_tailoring_xml`, `compare_tailorings`,
`render_drift_section`, `render_tailoring`, `collect_deployed_tailoring`).
