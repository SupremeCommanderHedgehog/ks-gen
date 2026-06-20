# Phase 3.7 — `auditd_actions` port to ubuntu2404 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the `auditd_actions` rule to ubuntu2404 so the generated autoinstall installs the `auditd` package and defensively re-asserts `disk_full_action`, `disk_error_action`, and `max_log_file_action` in `/etc/audit/auditd.conf` to operator's `cfg.overrides.auditd` values.

**Architecture:** One new rule module + one new test file. `emit_post` returns a single defensive sed + grep-fallback block (mirrors phase 3.5 faillock_safety). `emit_packages` returns `["auditd"]` because Ubuntu Server doesn't ship it by default (unlike RHEL). `emit_tailoring` + `exception_entry` deferred to audit-story PR per phase 3.x pattern. `applies` always True (no parent enable on AuditdActionsCfg).

**Tech Stack:** Python 3.11+, pydantic v2, jinja2, syrupy snapshots, pytest, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-06-20-ubuntu-stig-autoinstall-phase-3-7-auditd-actions-design.md`

**Branch:** `phase-3.7-auditd-actions` (already created off main at `388b46a`; spec already committed at `d27d9c1`).

---

## Reference patterns

- **alma9 sibling:** `src/ks_gen/rules/alma9/auditd_actions.py` — semantic source for the sed-replace structure and the three field substitutions; the alma9 rule uses non-defensive sed (`^disk_full_action.*`) but the Ubuntu port uses the defensive variant (`^[# ]*disk_full_action.*` + grep-fallback) per the spec.
- **Closest ubuntu2404 sibling:** `src/ks_gen/rules/ubuntu2404/faillock_safety.py` (phase 3.5) — same defensive sed + grep-fallback shape over a single config file.
- **Test sibling:** `tests/rules/test_ubuntu2404_faillock_safety.py` — module-level `from ... import RULE` at top, local `from ks_gen.config import ...` inside per-test override functions.

The `AuditdActionsCfg` schema lives at `src/ks_gen/config.py:560-577`:

```python
# src/ks_gen/config.py:560-577
class AuditdSystemAction(StrEnum):
    SUSPEND = "SUSPEND"
    SYSLOG = "SYSLOG"
    HALT = "HALT"
    SINGLE = "SINGLE"

class AuditdMaxFileAction(StrEnum):
    ROTATE = "ROTATE"
    KEEP_LOGS = "keep_logs"      # note lowercase — auditd.conf token
    SYSLOG = "SYSLOG"
    IGNORE = "IGNORE"

class AuditdActionsCfg(StrictModel):
    disk_full_action: AuditdSystemAction = AuditdSystemAction.SUSPEND
    disk_error_action: AuditdSystemAction = AuditdSystemAction.SUSPEND
    max_log_file_action: AuditdMaxFileAction = AuditdMaxFileAction.ROTATE
```

No parent `enable` flag — the rule's `applies` always returns True. Operator opts out by reverting all three field defaults (which is a no-op against stock auditd.conf).

Override pattern in tests:

```python
from ks_gen.config import (
    AuditdActionsCfg, AuditdSystemAction, AuditdMaxFileAction, Overrides,
)

cfg = ubuntu_cfg_factory().model_copy(
    update={"overrides": Overrides(
        auditd=AuditdActionsCfg(disk_full_action=AuditdSystemAction.HALT),
    )}
)
```

---

## Task 1: Rule skeleton + first failing test

Create the rule file with the full `_emit` helper in one TDD shot. The body is small enough that incrementally building it out wouldn't add review value. Add one failing path test (on `/etc/audit/auditd.conf`) to drive the wiring.

**Files:**
- Create: `src/ks_gen/rules/ubuntu2404/auditd_actions.py`
- Create: `tests/rules/test_ubuntu2404_auditd_actions.py`

- [ ] **Step 1: Write the failing test**

Create `tests/rules/test_ubuntu2404_auditd_actions.py` with this exact content:

```python
from ks_gen.rules.ubuntu2404.auditd_actions import RULE


def test_post_targets_etc_audit_auditd_conf(ubuntu_cfg_factory):
    # /etc/audit/auditd.conf is the canonical auditd config path on
    # both Ubuntu and RHEL — same upstream auditd package layout.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/audit/auditd.conf" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/rules/test_ubuntu2404_auditd_actions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ks_gen.rules.ubuntu2404.auditd_actions'`

- [ ] **Step 3: Create the rule module**

Create `src/ks_gen/rules/ubuntu2404/auditd_actions.py` with this exact content:

```python
"""ubuntu2404 auditd_actions rule.

Installs the auditd package and defensively re-asserts
disk_full_action, disk_error_action, and max_log_file_action in
/etc/audit/auditd.conf to the operator's cfg.overrides.auditd
values. Ubuntu Server does not ship auditd by default (unlike
RHEL), so emit_packages pulls it in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import auditd_actions as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


def _emit(cfg: HostConfig) -> str:
    a = cfg.overrides.auditd
    conf = "/etc/audit/auditd.conf"
    df = a.disk_full_action.value
    de = a.disk_error_action.value
    mf = a.max_log_file_action.value
    return (
        "# Re-assert auditd actions (defensive sed + append-if-missing)\n"
        f"sed -i -E 's|^[# ]*disk_full_action.*|disk_full_action = {df}|' {conf}\n"
        f"grep -q '^disk_full_action' {conf} || echo 'disk_full_action = {df}' >> {conf}\n"
        f"sed -i -E 's|^[# ]*disk_error_action.*|disk_error_action = {de}|' {conf}\n"
        f"grep -q '^disk_error_action' {conf} || echo 'disk_error_action = {de}' >> {conf}\n"
        f"sed -i -E 's|^[# ]*max_log_file_action.*|max_log_file_action = {mf}|' {conf}\n"
        f"grep -q '^max_log_file_action' {conf} || echo 'max_log_file_action = {mf}' >> {conf}\n"
    )


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        # Deferred: ssg-ubuntu2404-ds.xml var_auditd_* variable IDs
        # land in the audit-story PR.
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        # Ubuntu Server doesn't ship auditd by default (unlike RHEL).
        return ["auditd"]

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        # Deferred: paired with emit_tailoring above; see audit-story PR.
        return None


RULE: Rule = cast(Rule, _Rule())
```

No edit to `src/ks_gen/rules/ubuntu2404/__init__.py` — registry uses `pkgutil.iter_modules` auto-discovery.

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/rules/test_ubuntu2404_auditd_actions.py -v`
Expected: PASS — `test_post_targets_etc_audit_auditd_conf` is green.

- [ ] **Step 5: Commit**

```bash
git add tests/rules/test_ubuntu2404_auditd_actions.py src/ks_gen/rules/ubuntu2404/auditd_actions.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(rules/ubuntu2404): add auditd_actions rule skeleton (#81 phase 3.7)

Defensive sed + grep-fallback for disk_full_action, disk_error_action,
and max_log_file_action in /etc/audit/auditd.conf. emit_packages
returns [auditd] because Ubuntu Server does not ship auditd by
default (unlike RHEL).

emit_tailoring + exception_entry deferred to audit-story PR per
phase 3.x pattern.

First test pins the /etc/audit/auditd.conf path."
```

NO `Co-Authored-By` trailer in the commit message.

If pre-commit hook regenerates the golden snapshot (the registry auto-discovery picks up the new rule), STAGE THOSE CHANGES and amend so the commit is whole. Same pattern as phase 3.4/3.5/3.6.

---

## Task 2: Default-value tests

Three tests asserting the cfg defaults (SUSPEND / SUSPEND / ROTATE) land in the rendered output, plus one for `applies`-always-True.

**Files:**
- Modify: `tests/rules/test_ubuntu2404_auditd_actions.py`

- [ ] **Step 1: Append four tests**

```python


def test_applies_always_returns_true(ubuntu_cfg_factory):
    # No parent enable flag on AuditdActionsCfg — matches alma9.
    # Opting out means reverting field defaults (no-op against stock auditd.conf).
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_post_reasserts_disk_full_action_default_suspend(ubuntu_cfg_factory):
    # Default disk_full_action is SUSPEND (remote-safe; HALT would
    # kill a cloud server on a log-volume spike).
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "disk_full_action = SUSPEND" in out


def test_post_reasserts_disk_error_action_default_suspend(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "disk_error_action = SUSPEND" in out


def test_post_reasserts_max_log_file_action_default_rotate(ubuntu_cfg_factory):
    # Default max_log_file_action is ROTATE (keeps recent logs,
    # avoids unbounded growth).
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "max_log_file_action = ROTATE" in out
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/rules/test_ubuntu2404_auditd_actions.py -v`
Expected: 5 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_auditd_actions.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert auditd_actions defaults + applies always true"
```

---

## Task 3: Cfg-override responsiveness tests

Three tests asserting that operator overrides flow into the rendered output. Includes the lowercase `keep_logs` edge case.

**Files:**
- Modify: `tests/rules/test_ubuntu2404_auditd_actions.py`

- [ ] **Step 1: Append three override tests**

```python


def test_post_reflects_disk_full_action_override(ubuntu_cfg_factory):
    from ks_gen.config import AuditdActionsCfg, AuditdSystemAction, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(
            auditd=AuditdActionsCfg(disk_full_action=AuditdSystemAction.HALT),
        )}
    )
    out = RULE.emit_post(cfg)
    assert "disk_full_action = HALT" in out
    # The default value must NOT appear in the disk_full assignment.
    assert "disk_full_action = SUSPEND" not in out


def test_post_reflects_disk_error_action_override(ubuntu_cfg_factory):
    from ks_gen.config import AuditdActionsCfg, AuditdSystemAction, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(
            auditd=AuditdActionsCfg(disk_error_action=AuditdSystemAction.SYSLOG),
        )}
    )
    out = RULE.emit_post(cfg)
    assert "disk_error_action = SYSLOG" in out
    assert "disk_error_action = SUSPEND" not in out


def test_post_reflects_max_log_file_action_keep_logs_lowercase(ubuntu_cfg_factory):
    # AuditdMaxFileAction.KEEP_LOGS has string value "keep_logs"
    # (lowercase) — auditd.conf's documented token. The enum's
    # string value lands verbatim in the sed-replace.
    from ks_gen.config import AuditdActionsCfg, AuditdMaxFileAction, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(
            auditd=AuditdActionsCfg(max_log_file_action=AuditdMaxFileAction.KEEP_LOGS),
        )}
    )
    out = RULE.emit_post(cfg)
    assert "max_log_file_action = keep_logs" in out
    assert "max_log_file_action = ROTATE" not in out
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/rules/test_ubuntu2404_auditd_actions.py -v`
Expected: 8 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_auditd_actions.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert auditd_actions cfg overrides flow through"
```

---

## Task 4: Defensive pattern shape tests

Two tests asserting the defensive sed prefix and the grep-fallback structure are present for ALL three directives. These pin the pattern so a future cleanup that drops the defensive branches gets caught.

**Files:**
- Modify: `tests/rules/test_ubuntu2404_auditd_actions.py`

- [ ] **Step 1: Append two pattern tests**

```python


def test_post_uses_defensive_sed_prefix_for_all_three_directives(ubuntu_cfg_factory):
    # The ^[# ]* prefix handles three states defensively: line
    # uncommented, line commented (e.g., "# disk_full_action = ..."),
    # and line entirely absent (the grep-fallback covers this last
    # case — see the next test).
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "^[# ]*disk_full_action" in out
    assert "^[# ]*disk_error_action" in out
    assert "^[# ]*max_log_file_action" in out


def test_post_appends_with_grep_fallback_for_all_three_directives(ubuntu_cfg_factory):
    # When the line is entirely absent (e.g., Debian downstream
    # rebuild dropped a default), the grep || echo fallback appends
    # the line so the directive is always set.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "grep -q '^disk_full_action' /etc/audit/auditd.conf || echo 'disk_full_action = SUSPEND'" in out
    assert "grep -q '^disk_error_action' /etc/audit/auditd.conf || echo 'disk_error_action = SUSPEND'" in out
    assert "grep -q '^max_log_file_action' /etc/audit/auditd.conf || echo 'max_log_file_action = ROTATE'" in out
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/rules/test_ubuntu2404_auditd_actions.py -v`
Expected: 10 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_auditd_actions.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert auditd_actions defensive sed + grep-fallback shape"
```

---

## Task 5: Packages + Protocol contract tests

Four tests guarding the remaining contract surfaces: `emit_packages` returns `["auditd"]`, `emit_tailoring` deferred, `exception_entry` deferred, and meta-derived attributes (`id`, `summary`, `depends_on`).

**Files:**
- Modify: `tests/rules/test_ubuntu2404_auditd_actions.py`

- [ ] **Step 1: Append four contract tests**

```python


def test_emit_packages_returns_auditd(ubuntu_cfg_factory):
    # Ubuntu Server's seed doesn't include auditd. Without this pull,
    # /etc/audit/auditd.conf doesn't exist and the sed-replace fails.
    assert RULE.emit_packages(ubuntu_cfg_factory()) == ["auditd"]


def test_emit_tailoring_returns_empty_deferred(ubuntu_cfg_factory):
    # Deferred: ssg-ubuntu2404-ds.xml var_auditd_* variable IDs land
    # in the audit-story PR.
    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []


def test_exception_entry_returns_none_deferred(ubuntu_cfg_factory):
    # Deferred: runtime-computed English (mirroring alma9's
    # HALT/HALT/keep_logs strict check) lands in the audit-story PR.
    assert RULE.exception_entry(ubuntu_cfg_factory()) is None


def test_id_and_summary_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules._meta import auditd_actions as meta

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY
    # Mirrors meta's empty DEPENDS_ON.
    assert RULE.depends_on == []
```

- [ ] **Step 2: Run all tests in the file**

Run: `pytest tests/rules/test_ubuntu2404_auditd_actions.py -v`
Expected: 14 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_auditd_actions.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert protocol contract for auditd_actions"
```

---

## Task 6: Snapshot regen

**Files:**
- Modify: `tests/golden/__snapshots__/test_ubuntu_minimal.ambr`

- [ ] **Step 1: Run the golden test to confirm it fails**

Run: `pytest tests/golden/ -v -k ubuntu_minimal`
Expected: FAIL — syrupy reports the snapshot diff for the new
auditd_actions band.

(Note: the snapshot may already be modified in the working tree if
the Task 1 commit's pre-commit hook ran `pytest` and triggered
syrupy's regen. In that case Step 1 still works — just verify the
diff against expectations in Step 3.)

- [ ] **Step 2: Regenerate the snapshot if not already updated**

If the snapshot test failed in Step 1:
Run: `pytest tests/golden/ --snapshot-update -k ubuntu_minimal`

If `git status` already shows the snapshot file as modified (or it
was bundled into Task 1's commit), skip the update command.

- [ ] **Step 3: Inspect the diff**

Run: `git diff tests/golden/__snapshots__/test_ubuntu_minimal.ambr`

Expected diff (and ONLY these changes):

1. `- Applied rules: 8` → `+ Applied rules: 9` in the Summary section.
2. `+ - `auditd_actions` — auditd disk_full/disk_error/max_log_file
   actions (SUSPEND/ROTATE default).` inserted at its sorted position
   in the Applied-rules list. (Writer's existing sort key determines
   exact location; observe and accept the regen's single-line
   insertion.)
3. A new `# rule:auditd_actions ──────────...` band inside
   `late-commands` containing the 6 sed+grep lines.
4. `+ - auditd` added to the `autoinstall.packages:` list at its
   sorted position.

If any alma9 snapshot diffs, STOP — investigate before proceeding.

**Merge-order assumption.** The 8 → 9 count assumes this branch
sits on main at `388b46a` (post-v0.20.0, phases
3.0/3.1/3.2/3.3/3.4/3.5/3.6 merged = 8 ubuntu rules). If unrelated
work landed first that added another rule, regenerate and confirm
"+1 your rule, nothing else."

- [ ] **Step 4: Commit the snapshot (if not already in Task 1's commit)**

```bash
git add tests/golden/__snapshots__/test_ubuntu_minimal.ambr
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(golden): regen ubuntu_minimal snapshot for auditd_actions rule"
```

If the snapshot was already bundled into Task 1's commit, this step
is a no-op — skip it.

---

## Task 7: CI parity + push + PR

- [ ] **Step 1: ruff check**

Run: `ruff check src tests`
Expected: `All checks passed!`

- [ ] **Step 2: ruff format --check**

Run: `ruff format --check src tests`
Expected: `N files already formatted`

If reformat needed:

```bash
ruff format src tests
ruff format --check src tests
git add -u
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "style: ruff format src tests"
```

- [ ] **Step 3: mypy**

Run: `mypy`
Expected: `Success: no issues found in N source files`

- [ ] **Step 4: pytest**

Run: `pytest -q`
Expected: ~855 tests pass (841 from end of phase 3.6 + 14 new
auditd_actions tests). Exact baseline may differ if other work has
landed since v0.20.0 — what matters is "+14 tests, all green."

- [ ] **Step 5: Verify signed-clean**

Run: `git log --show-signature -8 --oneline`
Expected: every commit on this branch since `d27d9c1` (spec) is
signed with key `BE707B220C995478`.

- [ ] **Step 6: Push**

Run: `git push -u origin phase-3.7-auditd-actions`
Expected: push succeeds; GitHub returns the PR URL.

If push fails with `GH007`, STOP and surface to user.

- [ ] **Step 7: Open the PR**

```bash
gh pr create --title "feat(rules/ubuntu2404): auditd_actions port (#81 phase 3.7)" --body "$(cat <<'EOF'
## Summary

- Ports the `auditd_actions` rule to ubuntu2404 (issue #81 phase 3.7).
- Single-block port: defensive sed + grep-fallback for `disk_full_action`, `disk_error_action`, and `max_log_file_action` in `/etc/audit/auditd.conf`. Same `^[# ]*` prefix + `grep -q || echo` append-if-missing pattern phase 3.5 faillock_safety uses.
- `emit_packages` returns `["auditd"]` because Ubuntu Server doesn't ship auditd by default (unlike RHEL). Without this pull, `/etc/audit/auditd.conf` doesn't exist and the late-command fails.
- `applies` returns True unconditionally — no parent enable flag on `AuditdActionsCfg` (matches alma9).
- `emit_tailoring` + `exception_entry` deferred to the audit-story PR (consistent with phases 3.1–3.6).
- Edge case pinned: `AuditdMaxFileAction.KEEP_LOGS` has string value `"keep_logs"` (lowercase, per upstream auditd convention) and lands verbatim in the sed-replace.

Spec: `docs/superpowers/specs/2026-06-20-ubuntu-stig-autoinstall-phase-3-7-auditd-actions-design.md`
Plan: `docs/superpowers/plans/2026-06-20-ubuntu-stig-autoinstall-phase-3-7-auditd-actions.md`

## Test plan

- [x] 14 new unit tests in `tests/rules/test_ubuntu2404_auditd_actions.py` cover: `/etc/audit/auditd.conf` path, `applies` always True, all three field defaults (SUSPEND/SUSPEND/ROTATE), cfg-override flow for each field (including the `keep_logs` lowercase edge), defensive `^[# ]*` sed prefix for all three directives, grep-fallback `||` append-if-missing for all three directives, `emit_packages == ["auditd"]`, and the Rule Protocol contract (`id`, `summary`, `depends_on`, deferred `emit_tailoring` / `exception_entry`).
- [x] `tests/golden/__snapshots__/test_ubuntu_minimal.ambr` regenerated — diff adds the `# rule:auditd_actions` band (6 sed+grep lines), bumps Applied-rules header 8 → 9, and inserts `auditd` into `autoinstall.packages:`. No alma9 snapshot changes.
- [x] Full CI chain run locally: `ruff check && ruff format --check && mypy && pytest -q` — all four green.
- [x] Each commit on this branch is GPG-signed with `BE707B220C995478`.
EOF
)"
```

- [ ] **Step 8: Wait for GitHub CI**

Run: `gh pr checks <pr-number>`
Expected: 6/6 checks pass (CodeQL, analyze, ruff, test 3.11/3.12/3.13).

Or poll:
```bash
until gh pr checks <pr-number> --json bucket --jq 'all(.[]; .bucket != "pending")' | grep -q true; do sleep 30; done
gh pr checks <pr-number>
```

If any check fails, STOP and report.
