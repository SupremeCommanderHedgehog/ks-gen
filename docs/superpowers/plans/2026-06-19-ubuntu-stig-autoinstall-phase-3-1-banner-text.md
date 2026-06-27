# Ubuntu STIG Autoinstall Phase 3.1 — `banner_text` Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port `banner_text` to `ubuntu2404` — emit the civilian banner as a late-command, identical operator surface to alma9, deferring tailoring + exception per the phase 3.0 lock pattern.

**Architecture:** New rule module at `src/ks_gen/rules/ubuntu2404/banner_text.py` discovered automatically by `registry.load_rules("ubuntu2404")` (no `__init__.py` changes — module discovery via `pkgutil.iter_modules`). Reuses `src/ks_gen/rules/_meta/banner_text.py` unchanged. Heredoc-driven `emit_post` writes `/etc/issue`, `/etc/issue.net`, `/etc/ssh/sshd-banner` from `cfg.banner.text` per `cfg.banner.apply_to` (motd → sshd-banner; gdm skipped). `emit_tailoring`, `emit_packages`, `exception_entry` return `[]` / `[]` / `None` deferred until the audit-story PR. The existing `_format_late_commands` in `skeleton.py` already handles multi-line bash bodies — no skeleton changes.

**Tech Stack:** Python 3.11+, pydantic 2, syrupy snapshots. No new dependencies.

**Branch:** Plan assumes `feat/phase-3-1-banner-text` is checked out from `main` at commit `140e6cf` (post-spec-commit).

**Acceptance bar:**
- New rule file + new unit-test file pass on their own.
- `tests/golden/__snapshots__/test_ubuntu_minimal.ambr` regen shows exactly one new late-command entry (banner_text, alphabetically before ssh_keep_open) — no other deltas.
- alma9 goldens byte-identical (zero behavior change for alma9 users).
- Local CI parity chain green: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`.

---

## File Structure

**Create (2 files):**

- `src/ks_gen/rules/ubuntu2404/banner_text.py` — the new rule module. Single `_Rule` dataclass exporting module-level `RULE: Rule` binding (matches the convention of every other rule module). Shape mirrors `src/ks_gen/rules/alma9/banner_text.py` with two divergences: the `_TARGET` dict maps `motd` to `/etc/ssh/sshd-banner` (not `/etc/motd`), and `emit_tailoring` / `emit_packages` / `exception_entry` return empty / empty / `None` (deferred).
- `tests/rules/test_ubuntu2404_banner_text.py` — unit tests mirroring `tests/rules/test_banner_text.py` (alma9) plus three deferral assertions (`emit_tailoring == []`, `exception_entry is None`, `emit_packages == []`) so the future audit-story PR has visible test fails to update.

**Modify (1 file):**

- `tests/golden/__snapshots__/test_ubuntu_minimal.ambr` — syrupy-regenerated; should grow exactly one new YAML literal block for the banner late-command (alphabetically positioned before the ssh_keep_open entry).

**Out of scope (no edits):**

- `src/ks_gen/rules/_meta/banner_text.py` — already distro-agnostic, reuse as-is.
- `src/ks_gen/rules/ubuntu2404/__init__.py` — registry uses `pkgutil.iter_modules`; new module is auto-discovered.
- `src/ks_gen/skeleton.py` / `src/ks_gen/templates/user-data.j2` — phase 3.0 already plumbed multi-line bash bodies through `_format_late_commands`.
- `src/ks_gen/writer.py` — `_build_ubuntu2404_bundle` already iterates `r.emit_post(cfg)` and collects non-empty bodies into `PostBlock`s.

---

### Task 1: Write the failing unit-test file

**Files:**
- Create: `tests/rules/test_ubuntu2404_banner_text.py`

**Goal:** Lock the rule's contract — three target paths, divergence from alma's `/etc/motd`, no DoD text, deferral of tailoring + exception + packages — before any rule code exists. Module import fails first, then per-method assertions fail.

- [ ] **Step 1: Create the test file**

Create `tests/rules/test_ubuntu2404_banner_text.py` with this content:

```python
def test_post_writes_issue_files(ubuntu_cfg_factory):
    from ks_gen.rules.ubuntu2404.banner_text import RULE

    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/issue" in out
    assert "/etc/issue.net" in out


def test_post_writes_sshd_banner_not_motd(ubuntu_cfg_factory):
    # On ubuntu the motd is dynamic; the canonical SSH banner channel is
    # /etc/ssh/sshd-banner. Spec 2026-06-18 §6 locks this divergence from
    # alma9 (which writes /etc/motd).
    from ks_gen.rules.ubuntu2404.banner_text import RULE

    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/ssh/sshd-banner" in out
    assert "/etc/motd" not in out


def test_post_writes_default_civilian_banner_text(ubuntu_cfg_factory):
    from ks_gen.rules.ubuntu2404.banner_text import RULE

    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "private computer system" in out


def test_post_does_not_contain_dod_text(ubuntu_cfg_factory):
    from ks_gen.rules.ubuntu2404.banner_text import RULE

    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "U.S. Government" not in out
    assert "USG" not in out


def test_applies_always_true(ubuntu_cfg_factory):
    from ks_gen.rules.ubuntu2404.banner_text import RULE

    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_emit_tailoring_returns_empty_deferred(ubuntu_cfg_factory):
    # Deferred until ssg-ubuntu2404-ds.xml survey lands. Future audit-story
    # PR will populate this — when it does, this test gets updated.
    from ks_gen.rules.ubuntu2404.banner_text import RULE

    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []


def test_exception_entry_returns_none_deferred(ubuntu_cfg_factory):
    # Deferred until ssg-ubuntu2404-ds.xml survey lands.
    from ks_gen.rules.ubuntu2404.banner_text import RULE

    assert RULE.exception_entry(ubuntu_cfg_factory()) is None


def test_emit_packages_is_empty(ubuntu_cfg_factory):
    # Banner files are written with coreutils (cat, chmod) which subiquity
    # pre-installs. No apt deps.
    from ks_gen.rules.ubuntu2404.banner_text import RULE

    assert RULE.emit_packages(ubuntu_cfg_factory()) == []


def test_id_and_summary_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules._meta import banner_text as meta
    from ks_gen.rules.ubuntu2404.banner_text import RULE

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY


def test_gdm_target_is_skipped(ubuntu_cfg_factory):
    # cfg.banner.apply_to defaults include "gdm"; ubuntu Server has no GDM
    # so this target must be a no-op (no path appears in the output).
    from ks_gen.rules.ubuntu2404.banner_text import RULE

    out = RULE.emit_post(ubuntu_cfg_factory())
    # No gdm-related path appears.
    assert "gdm" not in out
    assert "/etc/dconf" not in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/rules/test_ubuntu2404_banner_text.py -v`
Expected: every test fails with `ModuleNotFoundError: No module named 'ks_gen.rules.ubuntu2404.banner_text'`.

- [ ] **Step 3: Commit the failing tests**

```powershell
git add tests/rules/test_ubuntu2404_banner_text.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): failing tests for banner_text port (#81 phase 3.1)"
```

---

### Task 2: Implement the rule module

**Files:**
- Create: `src/ks_gen/rules/ubuntu2404/banner_text.py`

**Goal:** Make Task 1's tests pass. Bash output structure follows alma's heredoc convention so `_format_late_commands`'s `shlex.quote` round-trip is identical to the alma path.

- [ ] **Step 1: Create the rule module**

Create `src/ks_gen/rules/ubuntu2404/banner_text.py` with this content:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import banner_text as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_TARGET = {
    "issue": "/etc/issue",
    "issue_net": "/etc/issue.net",
    "motd": "/etc/ssh/sshd-banner",
}


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        text = cfg.banner.text.rstrip("\n") + "\n"
        lines = ["# Civilian-equivalent login banner"]
        for target in cfg.banner.apply_to:
            if target == "gdm":
                continue
            path = _TARGET[target]
            lines.append(f"cat > {path} <<'__KS_GEN_EOF__'")
            lines.append(text.rstrip("\n"))
            lines.append("__KS_GEN_EOF__")
            lines.append(f"chmod 644 {path}")
        return "\n".join(lines) + "\n"

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return None


RULE: Rule = cast(Rule, _Rule())
```

- [ ] **Step 2: Run the unit tests to verify they pass**

Run: `pytest tests/rules/test_ubuntu2404_banner_text.py -v`
Expected: all 10 tests PASS.

- [ ] **Step 3: Commit the implementation**

```powershell
git add src/ks_gen/rules/ubuntu2404/banner_text.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(rules/ubuntu2404): banner_text port (#81 phase 3.1)"
```

---

### Task 3: Regenerate the ubuntu_minimal golden snapshot

**Files:**
- Modify: `tests/golden/__snapshots__/test_ubuntu_minimal.ambr`

**Goal:** The ubuntu bundle now picks up a second late-command (banner_text). Confirm syrupy diff is exactly that addition — nothing else.

- [ ] **Step 1: Run the snapshot test to see the predicted diff**

Run: `pytest tests/golden/test_ubuntu_minimal.py -q`
Expected: FAIL on the `user-data` snapshot; diff shows a new late-command entry containing `cat > /etc/issue <<'__KS_GEN_EOF__'`, alphabetically inserted before the existing `ssh_keep_open`/`ufw allow 22/tcp` entry. No other deltas (tailoring.xml, meta-data, host.yaml, exceptions.md unchanged because tailoring/exception are still empty for this rule).

- [ ] **Step 2: Regenerate the snapshot**

Run: `pytest tests/golden/test_ubuntu_minimal.py --snapshot-update -q`
Expected: PASS, "1 snapshot updated".

- [ ] **Step 3: Inspect the diff**

Run: `git diff tests/golden/__snapshots__/test_ubuntu_minimal.ambr`
Expected: the diff shows ONLY a new YAML literal-block entry under `late-commands:` containing the banner heredocs for `/etc/issue`, `/etc/issue.net`, `/etc/ssh/sshd-banner`. No changes to tailoring.xml, meta-data, exceptions.md, or host.yaml sections. If anything else changes, STOP and investigate.

- [ ] **Step 4: Commit the snapshot**

```powershell
git add tests/golden/__snapshots__/test_ubuntu_minimal.ambr
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(golden): regen ubuntu_minimal snapshot for banner_text (#81 phase 3.1)"
```

---

### Task 4: Run CI parity chain, push, open PR

**Files:** none (no edits)

**Goal:** Verify lint/format/mypy/full test suite locally before push; open PR linked to #81.

- [ ] **Step 1: Run the full CI parity chain**

Run: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
Expected: all four green. If `ruff format --check` flags formatting drift, run `ruff format src tests`, re-verify with `--check`, then stage and create a NEW signed commit with subject `style: ruff format` (per the user's global "never amend" rule).

- [ ] **Step 2: Push the branch**

```powershell
git push -u origin feat/phase-3-1-banner-text
```
Expected: branch created on remote, tracking set.

- [ ] **Step 3: Open the PR**

Run:

```powershell
gh pr create --title "feat(rules/ubuntu2404): banner_text port (#81 phase 3.1)" --body @'
## Summary

- Ports the `banner_text` rule to `ubuntu2404`. Writes the civilian banner to `/etc/issue`, `/etc/issue.net`, and `/etc/ssh/sshd-banner` (motd target divergence from alma9 per spec §6 of `2026-06-18-ubuntu-stig-autoinstall-design.md`). `gdm` target stays a no-op.
- Heredoc style + meta sharing identical to alma9, so the operator config surface (`cfg.banner.text`, `cfg.banner.apply_to`) is unchanged across distros.
- Tailoring + exception entry + emit_packages return empty / `None` / empty — deferred to the upcoming "ubuntu audit story" PR that surveys `ssg-ubuntu2404-ds.xml` once for several ported rules together. Mirrors phase 3.0's locked decision #5.

## Test plan

- [x] 10 new unit tests in `tests/rules/test_ubuntu2404_banner_text.py` cover path map (issue + issue_net + sshd-banner), motd-divergence assertion, no-DoD-text, gdm-skip, meta sharing, and three deferral contracts (`emit_tailoring == []`, `exception_entry is None`, `emit_packages == []`)
- [x] `test_ubuntu_minimal` snapshot regen — diff is exactly one new late-command entry (banner heredocs); tailoring.xml / exceptions.md / meta-data / host.yaml byte-identical
- [x] alma9 goldens byte-identical
- [x] Local CI parity: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`

Refs #81 phase 3.1. Spec: `docs/superpowers/specs/2026-06-19-ubuntu-stig-autoinstall-phase-3-1-banner-text-design.md`.
'@
```

Expected: PR URL printed; capture it for the user.
