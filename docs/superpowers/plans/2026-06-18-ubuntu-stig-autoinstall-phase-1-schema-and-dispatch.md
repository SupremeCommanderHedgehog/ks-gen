# Ubuntu STIG Autoinstall — Phase 1: Schema discriminator + per-distro registry dispatch

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `distro:` discriminator to `HostConfig`, split the rule registry to load `ks_gen.rules.<distro>.*`, mechanically move the existing 15 rules under `ks_gen.rules.alma9/`, and extract their shared identity strings into `ks_gen.rules._meta/<rule_id>.py`. Outcome: alma9 users see zero behavior change (golden snapshots unchanged); the codebase is now staged to accept `rules/ubuntu2404/*` modules in Phase 3 with no further refactor.

**Architecture:** Three small atomic changes — (1) config field with default `alma9` and a coordinating post-validator on `meta.scap_content`, (2) atomic move of `rules/*.py` → `rules/alma9/*.py` with `registry.load_rules(distro)` becoming distro-aware and every call site passing `cfg.distro`, (3) per-rule metadata extraction into `rules/_meta/<rule_id>.py` modules so future Ubuntu siblings import the same `ID`/`SUMMARY`/exception text.

**Tech Stack:** Python 3.11+, pydantic 2, pytest, syrupy (golden snapshots). No new runtime deps.

**Parent spec:** `docs/superpowers/specs/2026-06-18-ubuntu-stig-autoinstall-design.md` (PR #89). Phase 1 of 5; subsequent phases get their own plan files when sequenced (Phase 2: Bundle reshape + writer dispatch; Phase 3: ~14 Ubuntu rule ports, one plan per rule or batched logically; Phase 4: `verify/*` distro-awareness; Phase 5: install-regression harness Ubuntu variant).

**Tracking issue:** #81.

---

## File Structure

### Files modified
- `src/ks_gen/config.py` — add `distro: Literal["alma9", "ubuntu2404"]` field to `HostConfig`; add coordinating validator on `meta.scap_content`.
- `src/ks_gen/registry.py` — `load_rules(distro: str) -> list[Rule]` walks `ks_gen.rules.<distro>`.
- `src/ks_gen/writer.py` — `build_bundle`, `render_tailoring` pass `cfg.distro` to `load_rules`.
- `src/ks_gen/cli.py` — the `rules` subcommand accepts `--distro` (default `alma9`).
- `src/ks_gen/exceptions_report.py` — exception-catalog helper accepts `distro` parameter.
- `tests/test_registry.py` — tests updated to call `load_rules("alma9")` and add a `load_rules("ubuntu2404")` empty-result case.

### Files moved (mechanical, no content change in Task 2)
The 15 existing rule modules move from `src/ks_gen/rules/<rule>.py` to `src/ks_gen/rules/alma9/<rule>.py`. Order doesn't matter; do them in one commit:

```
admin_user_and_keys.py
auditd_actions.py
banner_text.py
container_host.py
crypto_policy.py
data_disks_preserve.py
dod_root_ca.py
faillock_safety.py
kernel_module_blacklist.py
package_purge.py
ssh_config_apply.py
ssh_keep_open.py
time_servers.py
unattended_updates.py
usbguard.py
```

`src/ks_gen/rules/_types.py` and `src/ks_gen/rules/__init__.py` stay at `src/ks_gen/rules/`. A new `src/ks_gen/rules/alma9/__init__.py` is created (empty).

### Files created
- `src/ks_gen/rules/alma9/__init__.py` (empty, marks subpackage)
- `src/ks_gen/rules/_meta/__init__.py` (empty, marks subpackage)
- `src/ks_gen/rules/_meta/<rule_id>.py` × 15 — shared rule identity strings (one per rule). Each contains `ID`, `SUMMARY`, `DEPENDS_ON`, plus optional `EXCEPTION_SUMMARY` + `EXCEPTION_REASON` for rules that return a non-`None` `exception_entry`.
- `tests/test_distro_field.py` — validates the new `HostConfig.distro` field and the `meta.scap_content` coordination.

### Files NOT created (deferred to Phase 2+)
- `src/ks_gen/rules/ubuntu2404/` — Phase 3.
- Any ubuntu rule implementations.
- Bundle reshape / `user-data` / `meta-data` emission (Phase 2).

---

## Task 1: Add `distro` field to `HostConfig` with `scap_content` coordination

**Files:**
- Modify: `src/ks_gen/config.py:669` (`HostConfig`) and `src/ks_gen/config.py:14` (`Meta`)
- Create: `tests/test_distro_field.py`

**Why first:** the registry change in Task 2 will require every call site to know `cfg.distro`. Adding the field first lets Task 2's tests reference the new attribute without depending on a half-applied refactor.

- [ ] **Step 1.1: Write the failing test file**

Create `tests/test_distro_field.py`:

```python
from __future__ import annotations

import pytest
from pydantic import ValidationError

from ks_gen.config import HostConfig


def _minimal_kwargs() -> dict:
    return {
        "system": {"hostname": "example"},
        "user": {
            "admin": {
                "name": "opsadmin",
                "authorized_keys": ["ssh-ed25519 AAAA test@host"],
                "sudo": "nopasswd_yes",
            }
        },
    }


def test_distro_defaults_to_alma9():
    cfg = HostConfig(**_minimal_kwargs())
    assert cfg.distro == "alma9"


def test_distro_accepts_ubuntu2404():
    cfg = HostConfig(distro="ubuntu2404", **_minimal_kwargs())
    assert cfg.distro == "ubuntu2404"


def test_distro_rejects_unknown_value():
    with pytest.raises(ValidationError) as ei:
        HostConfig(distro="centos7", **_minimal_kwargs())
    assert "distro" in str(ei.value)


def test_scap_content_default_matches_alma9():
    cfg = HostConfig(**_minimal_kwargs())
    assert cfg.meta.scap_content == "ssg-almalinux9-ds.xml"


def test_scap_content_default_matches_ubuntu2404():
    cfg = HostConfig(distro="ubuntu2404", **_minimal_kwargs())
    assert cfg.meta.scap_content == "ssg-ubuntu2404-ds.xml"


def test_scap_content_explicit_override_must_match_distro_alma9():
    with pytest.raises(ValidationError) as ei:
        HostConfig(
            distro="alma9",
            meta={"scap_content": "ssg-ubuntu2404-ds.xml"},
            **_minimal_kwargs(),
        )
    assert "scap_content" in str(ei.value)


def test_scap_content_explicit_override_must_match_distro_ubuntu2404():
    with pytest.raises(ValidationError) as ei:
        HostConfig(
            distro="ubuntu2404",
            meta={"scap_content": "ssg-almalinux9-ds.xml"},
            **_minimal_kwargs(),
        )
    assert "scap_content" in str(ei.value)
```

- [ ] **Step 1.2: Run the new tests to confirm they fail**

Run: `pytest tests/test_distro_field.py -v`
Expected: all seven tests fail (default test fails because `HostConfig` has no `distro` attribute; explicit-value test fails because `distro` kwarg is not accepted; etc.).

- [ ] **Step 1.3: Add the `distro` field on `HostConfig`**

In `src/ks_gen/config.py`, near the top of `class HostConfig(StrictModel):` (line ~669), insert as the first field:

```python
class HostConfig(StrictModel):
    distro: Literal["alma9", "ubuntu2404"] = "alma9"
    meta: Meta = Field(default_factory=Meta)
    # ...rest unchanged
```

`Literal` is already imported at the top of the file.

- [ ] **Step 1.4: Add a coordinating `model_validator` for `meta.scap_content`**

Inside `HostConfig`, alongside the existing `_crypto_fips_mutex` and `_admin_credential_mutex` validators, add:

```python
_DEFAULT_SCAP_CONTENT_BY_DISTRO: dict[str, str] = {
    "alma9": "ssg-almalinux9-ds.xml",
    "ubuntu2404": "ssg-ubuntu2404-ds.xml",
}


@model_validator(mode="after")
def _scap_content_matches_distro(self) -> HostConfig:
    expected = _DEFAULT_SCAP_CONTENT_BY_DISTRO[self.distro]
    # If the user accepted the alma9 default but distro is ubuntu2404, swap to the
    # ubuntu default rather than erroring. Only fail if they explicitly set a
    # mismatching value.
    alma_default = _DEFAULT_SCAP_CONTENT_BY_DISTRO["alma9"]
    if self.meta.scap_content == alma_default and self.distro != "alma9":
        # Replace the Meta with the distro-correct default; Meta is frozen, so rebuild.
        object.__setattr__(self, "meta", self.meta.model_copy(update={"scap_content": expected}))
        return self
    if self.meta.scap_content != expected:
        raise ValueError(
            f"meta.scap_content={self.meta.scap_content!r} does not match distro={self.distro!r}; "
            f"expected {expected!r}"
        )
    return self
```

Place the module-level dict `_DEFAULT_SCAP_CONTENT_BY_DISTRO` just above `class HostConfig` (it's a module-level constant the validator looks up).

> **Note on `object.__setattr__`:** `StrictModel` is `frozen=True`. Pydantic's recommended pattern for a model-validator that needs to mutate a sibling field is `object.__setattr__`. Verify the validator runs after `Meta` is constructed by keeping `mode="after"`.

- [ ] **Step 1.5: Run the tests again to confirm they pass**

Run: `pytest tests/test_distro_field.py -v`
Expected: all seven tests pass.

- [ ] **Step 1.6: Run the full test suite to confirm no regressions**

Run: `pytest -q`
Expected: all previously-passing tests still pass. If golden snapshot tests fail, investigate before continuing — Task 1 should not change any rendered output (default `distro=alma9` + default `scap_content` = `ssg-almalinux9-ds.xml`, same as today).

- [ ] **Step 1.7: Local CI parity check (per `CLAUDE.md`)**

Run: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
Expected: all four pass.
If `ruff format --check` fails: `ruff format src tests`, re-run `--check`, commit fixes as `style:`.

- [ ] **Step 1.8: Commit**

```bash
git -c user.email="github.v5f9w@bitbucket.onl" \
    -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(config): add distro discriminator to HostConfig

Adds distro: Literal[\"alma9\", \"ubuntu2404\"] = \"alma9\" to HostConfig
and a model_validator that coordinates meta.scap_content with the
chosen distro (auto-swaps default; rejects explicit mismatches).

No behavior change for existing alma9 users — the field defaults to
\"alma9\" and the default scap_content stays ssg-almalinux9-ds.xml.

Phase 1 of #81 (Ubuntu STIG autoinstall). Per spec PR #89."
```

---

## Task 2: Move existing rules to `rules/alma9/` and make registry distro-aware

**Files:**
- Modify: `src/ks_gen/registry.py`
- Modify: `src/ks_gen/writer.py` (lines 32, 42)
- Modify: `src/ks_gen/exceptions_report.py` (line 25)
- Modify: `src/ks_gen/cli.py` (line 73)
- Modify: `tests/test_registry.py`
- Create: `src/ks_gen/rules/alma9/__init__.py` (empty)
- Move: 15 files from `src/ks_gen/rules/*.py` to `src/ks_gen/rules/alma9/*.py` (full list in File Structure above)

**Why atomic:** the registry walks `ks_gen.rules.<distro>`. Moving files without updating registry breaks discovery; updating registry without moving files makes it find nothing. They commit together.

- [ ] **Step 2.1: Write the failing registry tests**

Replace the contents of `tests/test_registry.py` with:

```python
from ks_gen.registry import load_rules


def test_registry_discovers_alma9_modules():
    rules = load_rules("alma9")
    ids = {r.id for r in rules}
    assert "admin_user_and_keys" in ids
    assert "banner_text" in ids
    assert "ssh_keep_open" in ids


def test_registry_skips_underscore_modules_in_alma9():
    rules = load_rules("alma9")
    ids = {r.id for r in rules}
    assert "_types" not in ids
    assert not any(rid.startswith("_") for rid in ids)


def test_registry_returns_rule_instances_for_alma9():
    rules = load_rules("alma9")
    assert len(rules) >= 15
    for r in rules:
        assert hasattr(r, "id")
        assert hasattr(r, "applies")
        assert hasattr(r, "emit_post")


def test_registry_ubuntu2404_returns_empty_list():
    rules = load_rules("ubuntu2404")
    assert rules == []
```

- [ ] **Step 2.2: Run the new tests to confirm they fail**

Run: `pytest tests/test_registry.py -v`
Expected: all four tests fail — `load_rules()` currently takes no args, so `load_rules("alma9")` raises `TypeError`.

- [ ] **Step 2.3: Create the new subpackage marker file**

Create `src/ks_gen/rules/alma9/__init__.py` (empty).

- [ ] **Step 2.4: Move the 15 rule files into `rules/alma9/`**

Move every file in `src/ks_gen/rules/` except `__init__.py` and `_types.py` into `src/ks_gen/rules/alma9/`:

```powershell
# PowerShell
$src = "src/ks_gen/rules"
$dst = "src/ks_gen/rules/alma9"
Get-ChildItem $src -Filter "*.py" | Where-Object { $_.Name -notin @("__init__.py", "_types.py") } | ForEach-Object {
    Move-Item -Path $_.FullName -Destination (Join-Path $dst $_.Name)
}
```

Or equivalent `git mv` invocations preserving git history (preferred — git tracks moves better when each file is moved with `git mv`):

```bash
# bash (WSL or Git Bash)
cd src/ks_gen/rules
for f in *.py; do
    case "$f" in
        __init__.py|_types.py) ;;
        *) git mv "$f" "alma9/$f" ;;
    esac
done
```

Use `git mv` so each move shows up as a rename in `git status` and the spec's "no behavior change" claim is auditable in the diff.

- [ ] **Step 2.5: Update `src/ks_gen/registry.py` to take a `distro` argument**

Replace the entire file content with:

```python
from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable

from ks_gen.rules._types import Rule


def load_rules(distro: str) -> list[Rule]:
    """Discover rule modules under ks_gen.rules.<distro>.

    Each module is expected to export a module-level `RULE: Rule` binding.
    Modules whose name starts with `_` are skipped (reserved for shared
    helpers like `_types`, `_meta`).
    """
    pkg_name = f"ks_gen.rules.{distro}"
    try:
        pkg = importlib.import_module(pkg_name)
    except ModuleNotFoundError:
        return []

    discovered: list[Rule] = []
    for info in pkgutil.iter_modules(pkg.__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{pkg_name}.{info.name}")
        rule = getattr(module, "RULE", None)
        if rule is None:
            raise RuntimeError(
                f"{pkg_name}.{info.name} does not export a module-level RULE binding"
            )
        discovered.append(rule)
    return discovered


def rule_ids(rules: Iterable[Rule]) -> list[str]:
    return [r.id for r in rules]
```

- [ ] **Step 2.6: Update `src/ks_gen/writer.py` to pass `cfg.distro`**

Two call sites, both replaced the same way:

In `render_tailoring` (currently line 32):
```python
def render_tailoring(cfg: HostConfig) -> str:
    rules = topo_sort(load_rules(cfg.distro))
    # ...rest unchanged
```

In `build_bundle` (currently line 42):
```python
def build_bundle(cfg: HostConfig) -> Bundle:
    rules = topo_sort(load_rules(cfg.distro))
    # ...rest unchanged
```

- [ ] **Step 2.7: Update `src/ks_gen/exceptions_report.py` call site**

The function is `expected_failure_rule_ids(cfg: HostConfig)` at line 10. It already has `cfg` in scope. One-line change at line 25:

```python
# Before:
for r in topo_sort(load_rules()):
# After:
for r in topo_sort(load_rules(cfg.distro)):
```

No signature change needed. `render_exceptions_md` does not call `load_rules` (it receives an `Iterable[Rule]` already), so no change there.

- [ ] **Step 2.8: Update `src/ks_gen/cli.py` — `rules` subcommand**

In `cli.py` around line 73, the `rules` subcommand calls `load_rules()`. Add an `--distro` typer option:

```python
@app.command()
def rules(
    distro: str = typer.Option("alma9", "--distro", help="Distro to list rules for"),
):
    catalog = load_rules(distro)
    # ...rest unchanged
```

Verify the existing typer-option imports cover this; add `import typer` if not already present at that level.

- [ ] **Step 2.9: Run the registry tests to confirm they pass**

Run: `pytest tests/test_registry.py -v`
Expected: all four tests pass.

- [ ] **Step 2.10: Run the full test suite**

Run: `pytest -q`
Expected: all tests pass. Critical: golden snapshot tests under `tests/golden/` must be unchanged. If `tests/golden/__snapshots__/*.ambr` files show diffs, investigate before continuing — the move is mechanical and should not affect any rendered output.

If snapshot diffs appear: do not run `--snapshot-update`. Read the diff. The most likely cause is an import path that wasn't updated. Fix the import, re-run, snapshots should match again.

- [ ] **Step 2.11: Local CI parity check**

Run: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
Expected: all four pass.

- [ ] **Step 2.12: Commit**

```bash
git add -A   # mass-add captures the moves; verify with `git status` first
git status   # confirm exactly the expected files: 15 renames + 5 modifies + 2 creates
git -c user.email="github.v5f9w@bitbucket.onl" \
    -c user.signingkey=BE707B220C995478 \
    commit -S -m "refactor(rules): move existing rules under rules/alma9/; distro-aware registry

Moves all 15 existing rule modules from ks_gen.rules.* to
ks_gen.rules.alma9.* using git mv (preserves rename history).
registry.load_rules now takes a distro argument and walks
ks_gen.rules.<distro>; an unknown distro returns []. All callers
(writer.render_tailoring, writer.build_bundle, exceptions_report,
cli.rules) thread cfg.distro through.

No behavior change for alma9 users — golden snapshots unchanged.

Phase 1 of #81 (Ubuntu STIG autoinstall). Per spec PR #89."
```

> **If `git add -A` would include unexpected files**, stage selectively instead: `git add src/ks_gen/rules/ src/ks_gen/registry.py src/ks_gen/writer.py src/ks_gen/exceptions_report.py src/ks_gen/cli.py tests/test_registry.py`.

---

## Task 3: Extract per-rule metadata into `rules/_meta/<rule_id>.py`

**Files:**
- Create: `src/ks_gen/rules/_meta/__init__.py` (empty)
- Create: `src/ks_gen/rules/_meta/<rule_id>.py` × 15 (one per rule; see list below)
- Modify: every `src/ks_gen/rules/alma9/<rule>.py` to import its identity strings from `_meta`

**Why separate from Task 2:** Task 2 is a pure move; Task 3 is a content refactor. Keeping them as two commits makes the refactor reviewable — Task 2's diff is rename-only; Task 3's diff is content-only.

The 15 rules to process (alphabetical):

```
admin_user_and_keys
auditd_actions
banner_text
container_host
crypto_policy
data_disks_preserve
dod_root_ca
faillock_safety
kernel_module_blacklist
package_purge
ssh_config_apply
ssh_keep_open
time_servers
unattended_updates
usbguard
```

The work is identical per rule. Do them in two commits: one for the meta-module-creation half, one for the consumer-side refactor.

- [ ] **Step 3.1: Create the `_meta` subpackage marker**

Create `src/ks_gen/rules/_meta/__init__.py` (empty).

- [ ] **Step 3.2: Create per-rule `_meta` modules**

For each rule, read its current `src/ks_gen/rules/alma9/<rule>.py` and extract:
- `id` → `ID`
- `summary` → `SUMMARY`
- the default value of `depends_on` → `DEPENDS_ON`
- if `exception_entry` returns a non-`None` `ExceptionEntry`, its `summary` text → `EXCEPTION_SUMMARY` and its `reason` text → `EXCEPTION_REASON`.

Example — `src/ks_gen/rules/_meta/banner_text.py`:

```python
"""Shared identity for the banner_text rule.

Imported by every distro implementation (alma9, ubuntu2404, ...) so the
rule's auditor-facing English does not drift between distros. Only the
distro-specific bash, package names, and STIG rule IDs differ.
"""

from __future__ import annotations

ID = "banner_text"
SUMMARY = "Write civilian-equivalent login banner; suppress DoD-text oscap rules."
DEPENDS_ON: list[str] = []
EXCEPTION_SUMMARY = "Substitutes private-system banner for DISA-mandated DoD text."
EXCEPTION_REASON = (
    "Server is not a U.S. Government Information System; literal DoD banner "
    "would make false legal claims. Civilian text satisfies the rule intent "
    "(warn unauthorized users; consent to monitoring)."
)
```

Example — `src/ks_gen/rules/_meta/ssh_keep_open.py` (rule has no exception_entry):

```python
"""Shared identity for the ssh_keep_open rule."""

from __future__ import annotations

ID = "ssh_keep_open"
SUMMARY = "Ensure ssh.port reachable before sshd starts."
DEPENDS_ON: list[str] = []
```

Rules that return `None` from `exception_entry` omit `EXCEPTION_SUMMARY` and `EXCEPTION_REASON`. Rules with non-trivial `DEPENDS_ON` carry the list literal verbatim.

> **Tip:** to confirm which rules have non-trivial `exception_entry`, run:
> ```bash
> grep -l "return ExceptionEntry" src/ks_gen/rules/alma9/*.py
> ```
> That list determines which `_meta` modules get `EXCEPTION_*` constants.

Create all 15 `_meta/<rule_id>.py` files. Each is < 25 lines.

- [ ] **Step 3.3: Run the test suite to confirm `_meta` is invisible to the existing code**

Run: `pytest -q`
Expected: all tests still pass. The `_meta` modules are created but no consumer imports them yet, so behavior is unchanged. Golden snapshots unchanged.

- [ ] **Step 3.4: CI parity check**

Run: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
Expected: all four pass.

- [ ] **Step 3.5: Commit the `_meta` modules**

```bash
git add src/ks_gen/rules/_meta/
git -c user.email="github.v5f9w@bitbucket.onl" \
    -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(rules): introduce rules/_meta/ shared identity modules

Adds one rules/_meta/<rule_id>.py per existing alma9 rule, holding
ID, SUMMARY, DEPENDS_ON, and (where applicable) EXCEPTION_SUMMARY +
EXCEPTION_REASON. Consumers (alma9/<rule>.py) still hold their own
copies; Task 3 commit B refactors them to import from _meta.

Phase 1 of #81 (Ubuntu STIG autoinstall). Per spec PR #89."
```

- [ ] **Step 3.6: Refactor each `rules/alma9/<rule>.py` to import from `_meta`**

For each of the 15 rules, edit its file to replace literal strings with `_meta` imports.

Example diff — `src/ks_gen/rules/alma9/banner_text.py`:

```python
# Before:
@dataclass(frozen=True)
class _Rule:
    id: str = "banner_text"
    summary: str = "Write civilian-equivalent login banner; suppress DoD-text oscap rules."
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=lambda: list(_TAILORED))
    # ...
    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return ExceptionEntry(
            rule_id="banner_text",
            summary="Substitutes private-system banner for DISA-mandated DoD text.",
            stig_rules_disabled=list(_TAILORED),
            reason=(
                "Server is not a U.S. Government Information System; literal DoD banner "
                "would make false legal claims. Civilian text satisfies the rule intent "
                "(warn unauthorized users; consent to monitoring)."
            ),
        )
```

```python
# After:
from ks_gen.rules._meta import banner_text as meta

@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=lambda: list(_TAILORED))
    # ...
    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return ExceptionEntry(
            rule_id=meta.ID,
            summary=meta.EXCEPTION_SUMMARY,
            stig_rules_disabled=list(_TAILORED),
            reason=meta.EXCEPTION_REASON,
        )
```

Apply the same pattern to every rule:
- `id: str = meta.ID`
- `summary: str = meta.SUMMARY`
- `depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))`
- For rules with `exception_entry`: `rule_id=meta.ID`, `summary=meta.EXCEPTION_SUMMARY`, `reason=meta.EXCEPTION_REASON`.

Leave `stig_rules_affected` (distro-specific XCCDF rule IDs) and the rule's `_TAILORED` constants alone — those are not shared across distros.

- [ ] **Step 3.7: Run the full test suite — golden snapshots must be unchanged**

Run: `pytest -q`
Expected: all tests pass. **Critical**: `tests/golden/__snapshots__/*.ambr` must remain byte-identical. If any snapshot diffs, the meta extraction has drifted from the original strings somewhere — read the diff, fix the offending `_meta` constant, do **not** run `--snapshot-update`.

- [ ] **Step 3.8: CI parity check**

Run: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
Expected: all four pass.

- [ ] **Step 3.9: Commit the consumer-side refactor**

```bash
git add src/ks_gen/rules/alma9/
git -c user.email="github.v5f9w@bitbucket.onl" \
    -c user.signingkey=BE707B220C995478 \
    commit -S -m "refactor(rules): import shared identity from _meta in alma9 rules

Each rules/alma9/<rule>.py now imports its ID, SUMMARY, DEPENDS_ON, and
exception text from rules/_meta/<rule>.py. Distro-specific concerns
(stig_rules_affected, _TAILORED rule IDs, emit_post bodies) stay in
the per-distro file.

Golden snapshots unchanged — extraction is string-equivalent.

Phase 1 of #81 (Ubuntu STIG autoinstall). Per spec PR #89."
```

---

## Task 4: Verify acceptance criteria and open Phase 1 PR

**Files:**
- (No source changes — verification only.)

- [ ] **Step 4.1: Confirm acceptance criteria**

The Phase 1 acceptance bar:
- [ ] `HostConfig.distro` field exists, defaults to `"alma9"`, accepts `"ubuntu2404"`, rejects anything else.
- [ ] `meta.scap_content` is auto-corrected from the alma9 default to the ubuntu2404 default when only `distro` is changed; mismatched explicit values are rejected.
- [ ] `registry.load_rules("alma9")` returns the 15 existing rules; `load_rules("ubuntu2404")` returns `[]`.
- [ ] `tests/golden/__snapshots__/*.ambr` are byte-identical to `main`.
- [ ] All four CI parity commands pass locally.

Run the explicit comparison for golden snapshots:

```bash
git diff main -- tests/golden/__snapshots__/
```
Expected: empty diff (no changes).

- [ ] **Step 4.2: Final CI parity check**

Run: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
Expected: all four pass.

- [ ] **Step 4.3: Create branch (if not already on one) and push**

If working directly on `main`, move the work to a feature branch first:

```bash
git switch -c feat/distro-discriminator-and-registry-dispatch
git push -u origin feat/distro-discriminator-and-registry-dispatch
```

If already on a feature branch, just push.

- [ ] **Step 4.4: Open the PR**

```bash
gh pr create --base main --title "feat(config,rules): distro discriminator + per-distro registry (#81 phase 1)" --body "$(cat <<'EOF'
## Summary

Phase 1 of #81 (Ubuntu STIG autoinstall, per spec PR #89). Adds the
distro: discriminator to HostConfig, splits the rule registry to load
rules/<distro>/*, mechanically moves the 15 existing rules to
rules/alma9/, and extracts their shared identity strings into
rules/_meta/.

**Zero behavior change for existing alma9 users.** Golden snapshots
unchanged. The codebase is now staged to accept rules/ubuntu2404/* in
Phase 3 with no further refactor.

## What changed

- `HostConfig` gains `distro: Literal["alma9", "ubuntu2404"] = "alma9"`
- `Meta.scap_content` validator coordinates with `distro` (auto-swap for
  default values; reject explicit mismatches)
- `registry.load_rules(distro)` walks `ks_gen.rules.<distro>`
- All 15 existing rule modules moved to `ks_gen.rules.alma9.*` via `git mv`
- New `ks_gen.rules._meta.<rule_id>` modules hold shared identity strings
- Each `rules/alma9/<rule>.py` imports `ID`, `SUMMARY`, `DEPENDS_ON`,
  `EXCEPTION_SUMMARY`, `EXCEPTION_REASON` from its `_meta` sibling
- Call sites updated: `writer.build_bundle`, `writer.render_tailoring`,
  `exceptions_report`, `cli.rules` (new `--distro` flag, default `alma9`)

## Test plan

- [x] `pytest tests/test_distro_field.py -v` — all seven new tests pass
- [x] `pytest tests/test_registry.py -v` — all four updated/new tests pass
- [x] `pytest -q` — full suite green
- [x] `git diff main -- tests/golden/__snapshots__/` is empty
- [x] `ruff check src tests && ruff format --check src tests && mypy && pytest -q` passes
- [ ] CI all-green on PR

## Out of scope (later phases)

- Bundle reshape + ubuntu2404 emission — Phase 2
- Per-rule ubuntu2404 implementations — Phase 3
- verify/* distro-awareness — Phase 4
- Install-regression harness ubuntu variant — Phase 5

Spec: PR #89 (`docs/superpowers/specs/2026-06-18-ubuntu-stig-autoinstall-design.md`)
Plan: `docs/superpowers/plans/2026-06-18-ubuntu-stig-autoinstall-phase-1-schema-and-dispatch.md`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 4.5: Confirm Phase 1 is done**

After CI is green and the PR is merged, Phase 1 is complete. Phase 2 plan is the natural next artifact.

---

## Acceptance criteria (Phase 1)

The PR is mergeable when **all** of these hold:

1. `HostConfig.distro` field exists with default `"alma9"` and `Literal["alma9", "ubuntu2404"]` type.
2. `meta.scap_content` is auto-defaulted to the distro-correct value when not explicitly set; explicit cross-distro mismatches raise `ValidationError`.
3. `registry.load_rules("alma9")` returns exactly the 15 existing rules; `load_rules("ubuntu2404")` returns `[]` without error.
4. `tests/golden/__snapshots__/` is byte-identical to `main`.
5. CI parity chain (`ruff check`, `ruff format --check`, `mypy`, `pytest`) passes locally and on CI.
6. All commits in the branch are GPG-signed with the configured key.
7. No new `rules/ubuntu2404/` directory exists — that's Phase 3's responsibility.
8. The `ks-gen` CLI still works against existing alma9 fixtures (manual smoke check: `ks-gen gen --config tests/fixtures/<some-alma9-fixture>.yaml --out /tmp/smoke` produces a non-empty bundle).

---

## Scope decisions (what's intentionally NOT in Phase 1)

Spec §3.3 lists distro-incompatible field-rejection validators (e.g., `container_host.*` rejected when `distro=ubuntu2404`, `overrides.ssh_keep_open.ensure_selinux_port` rejected when `distro=ubuntu2404`, `unattended_updates.apt_periodic_*` rejected when `distro=alma9`). These are forward-correctness for the ubuntu2404 schema and would never fire today — no operator can set `distro: ubuntu2404` and reach a working bundle until Phase 2 lands. Defer to **Phase 2's plan** (alongside the Bundle reshape), where they become exercisable end-to-end.

If you decide to pull them forward into Phase 1, add them as a Task 5 — one validator per spec §3.3 row, each with a paired ValidationError test in `tests/test_distro_field.py`. The work is mechanical but adds ~8 small tests.

## Next phases (not in this plan)

When Phase 1 lands, write a separate plan for each of:

- **Phase 2:** Bundle reshape + writer dispatch + spec §3.3 cross-distro field-rejection validators. Adds `Bundle.distro`, `Bundle.user_data`/`meta_data` fields; `build_bundle` distro switch; emits an empty/placeholder ubuntu2404 bundle (no rules yet). Adds the post-validators that reject distro-incompatible field combos.
- **Phase 3:** Per-rule ubuntu2404 implementations. One plan per rule, in the order from spec §6's sketch table. Each plan covers the rule's unit tests, golden snapshot generation, and PR. Skip `container_host` (tracked in #88).
- **Phase 4:** `verify/*` distro-awareness. `baseline.py` distro-aware datastream selection; `suggest.py` rewrite for ubuntu remediation hints.
- **Phase 5:** Install-regression harness ubuntu variant. Local-only, gitignored, mirror of `.scratch/install-regression/` (#57).
