# Phases 3.9 + 3.10 + 3.11 — bundled port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port three rules to ubuntu2404 in one PR: `usbguard` (phase 3.9), `package_purge` (phase 3.10), `dod_root_ca` (phase 3.11). usbguard and dod_root_ca are scaffolding-only (empty `emit_post`, deferred tailoring/exception); package_purge runs an `apt-get -y purge` late-command mirroring alma9's `dnf -y remove`.

**Architecture:** Three rule modules + three test files. Each rule mirrors its alma9 sibling exactly, with `emit_tailoring` + `exception_entry` deferred per the phase 3.x audit-story pattern. The ubuntu_minimal golden snapshot regenerates once at the end with three new entries in the Applied-rules listing (count 10 → 13) and one new `# rule:package_purge` late-commands band.

**Tech Stack:** Python 3.11+, pydantic v2, jinja2, syrupy snapshots, pytest, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-06-20-ubuntu-stig-autoinstall-phases-3-9-3-11-bundled-design.md`

**Branch:** `phase-3.9-3.11-bundled-ports` (already created off main at `8a1f2a4`; spec already committed at `acdfaa2`).

---

## Reference patterns

- **alma9 siblings (semantic source):**
  - `src/ks_gen/rules/alma9/usbguard.py` — empty `emit_post`, applies=True, the meaningful work (tailoring select-vs-disable + exception) is in methods we defer.
  - `src/ks_gen/rules/alma9/package_purge.py` — single-line late-command `dnf -y remove {pkgs} || true`, applies when `enable AND bool(excluded)`.
  - `src/ks_gen/rules/alma9/dod_root_ca.py` — empty `emit_post`, applies = `not install`, the meaningful work (tailoring disable + exception) is in methods we defer.
- **Closest ubuntu2404 sibling (single-line late-command):** `src/ks_gen/rules/ubuntu2404/auditd_actions.py` — single composed body in a `_emit` helper. `package_purge` uses a similar inline composition.
- **Closest ubuntu2404 sibling (scaffolding-only):** None yet. usbguard and dod_root_ca are the first two ubuntu2404 rules with empty `emit_post` — but the writer's `if body:` guard at `src/ks_gen/writer.py:124` already handles this case (precedent: `admin_user_and_keys` in phase 3.0 contributes nothing to `late-commands` and instead drives `autoinstall.identity` / `users:`).
- **Test sibling:** `tests/rules/test_ubuntu2404_faillock_safety.py` — module-level `from ... import RULE` at top, local `from ks_gen.config import ...` inside per-test override functions.

Schemas (no edits):

```python
# src/ks_gen/config.py:586-588
class UsbguardCfg(StrictModel):
    enable: bool = False

# src/ks_gen/config.py:606-607
class PackagePurgeCfg(StrictModel):
    enable: bool = True

# src/ks_gen/config.py:610-611
class DodRootCaCfg(StrictModel):
    install: bool = False

# src/ks_gen/config.py:510-537 (Packages.excluded default — 5 RHEL-flavored entries)
class Packages(StrictModel):
    ...
    excluded: list[str] = Field(default_factory=lambda: [
        "telnet-server", "rsh-server", "tftp-server", "vsftpd", "ypserv",
    ])
```

---

## Task 1: usbguard rule skeleton + 6 tests

usbguard's `emit_post` is empty (mirrors alma9), so this is one TDD shot: create rule + 6 tests at once. Snapshot effect is "+1 line in Applied-rules listing"; no late-commands band.

**Files:**
- Create: `src/ks_gen/rules/ubuntu2404/usbguard.py`
- Create: `tests/rules/test_ubuntu2404_usbguard.py`

- [ ] **Step 1: Create the rule module**

Create `src/ks_gen/rules/ubuntu2404/usbguard.py` with this exact content:

```python
"""ubuntu2404 usbguard rule.

Scaffolding-only port: applies unconditionally so the rule lands in
the Applied-rules count + listing. emit_post is empty (mirrors
alma9 — the meaningful work is in emit_tailoring + exception_entry,
both deferred to the audit-story PR per the phase 3.x pattern).

When the audit-story PR wires up the deferred methods, this rule
will gain ssg-ubuntu2404-ds.xml tailoring ops (select if
overrides.usbguard.enable, disable otherwise) and a paired
exception_entry. At that point, a coordinated edit will likely
also add the `usbguard` package install + service enable in
emit_post — currently neither alma9 nor ubuntu2404 implements that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import usbguard as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        # Deferred: ssg-ubuntu2404-ds.xml usbguard rule IDs land in
        # the audit-story PR.
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return ""

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        # Deferred with emit_tailoring: when usbguard.enable is wired,
        # this will return ["usbguard"].
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        # Deferred: paired with emit_tailoring above; see audit-story PR.
        return None


RULE: Rule = cast(Rule, _Rule())
```

- [ ] **Step 2: Create the test file**

Create `tests/rules/test_ubuntu2404_usbguard.py` with this exact content:

```python
from ks_gen.rules.ubuntu2404.usbguard import RULE


def test_applies_always_returns_true(ubuntu_cfg_factory):
    # Mirrors alma9 unconditional applies. The meaningful
    # enable/disable distinction lives in deferred methods.
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_emit_post_returns_empty(ubuntu_cfg_factory):
    # Empty body — writer's `if body:` guard skips this rule for
    # late-commands. The rule still increments Applied-rules count.
    assert RULE.emit_post(ubuntu_cfg_factory()) == ""


def test_emit_packages_returns_empty(ubuntu_cfg_factory):
    # Deferred: usbguard package install lands when the audit-story
    # PR wires up the enable=True branch.
    assert RULE.emit_packages(ubuntu_cfg_factory()) == []


def test_emit_tailoring_returns_empty_deferred(ubuntu_cfg_factory):
    # Deferred: ssg-ubuntu2404-ds.xml usbguard rule IDs land in
    # the audit-story PR.
    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []


def test_exception_entry_returns_none_deferred(ubuntu_cfg_factory):
    # Deferred: paired with emit_tailoring above.
    assert RULE.exception_entry(ubuntu_cfg_factory()) is None


def test_id_and_summary_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules._meta import usbguard as meta

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY
    # Mirrors meta's empty DEPENDS_ON.
    assert RULE.depends_on == []
```

- [ ] **Step 3: Run the tests**

Run: `pytest tests/rules/test_ubuntu2404_usbguard.py -v`
Expected: 6 tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/ks_gen/rules/ubuntu2404/usbguard.py tests/rules/test_ubuntu2404_usbguard.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(rules/ubuntu2404): add usbguard rule skeleton (#81 phase 3.9)

Scaffolding-only port mirroring alma9 — applies=True, empty
emit_post, emit_packages empty. The meaningful work (tailoring
select-vs-disable on overrides.usbguard.enable + paired
exception_entry, plus the usbguard package install + service
enable that neither distro implements yet) is deferred to the
audit-story PR per the phase 3.x pattern.

The writer's \`if body:\` guard at writer.py:124 skips empty
emit_post bodies — the rule appears in the Applied-rules count
+ listing in exceptions.md but contributes no late-commands band.

6 tests pin: applies always True, emit_post empty, emit_packages
empty, tailoring + exception_entry deferred, protocol contract
(id/summary from shared meta, depends_on empty)."
```

---

## Task 2: package_purge rule skeleton + 10 tests

The only rule of the three with a meaningful late-command. `applies` gates on both `enable` AND `bool(excluded)` (matches alma9).

**Files:**
- Create: `src/ks_gen/rules/ubuntu2404/package_purge.py`
- Create: `tests/rules/test_ubuntu2404_package_purge.py`

- [ ] **Step 1: Create the rule module**

Create `src/ks_gen/rules/ubuntu2404/package_purge.py` with this exact content:

```python
"""ubuntu2404 package_purge rule.

Runs an apt-get -y purge late-command for each package in
cfg.packages.excluded. Mirrors the alma9 dnf -y remove rule. The
trailing `|| true` squashes "unable to locate package" (exit 100)
and "already removed" (exit 1) so stale excluded entries don't
fail the install — important because the default excluded list is
RHEL-flavored (telnet-server, rsh-server, etc.) and most entries
don't exist in the Ubuntu archive.

emit_tailoring + exception_entry deferred to audit-story PR per
phase 3.x pattern (alma9 returns [] / None for both).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import package_purge as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


def _emit(cfg: HostConfig) -> str:
    pkgs = " ".join(cfg.packages.excluded)
    return (
        "# Remove disallowed packages (no-op if not installed)\n"
        f"DEBIAN_FRONTEND=noninteractive apt-get -y purge {pkgs} || true\n"
    )


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return cfg.overrides.package_purge.enable and bool(cfg.packages.excluded)

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return None


RULE: Rule = cast(Rule, _Rule())
```

- [ ] **Step 2: Create the test file**

Create `tests/rules/test_ubuntu2404_package_purge.py` with this exact content:

```python
from ks_gen.rules.ubuntu2404.package_purge import RULE


def test_applies_when_enabled_and_has_excluded(ubuntu_cfg_factory):
    # Default cfg: enable=True, excluded=5 RHEL-flavored entries.
    # Both conditions satisfied → applies.
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_applies_short_circuits_when_disabled(ubuntu_cfg_factory):
    from ks_gen.config import Overrides, PackagePurgeCfg

    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "overrides": Overrides(
                package_purge=PackagePurgeCfg(enable=False),
            )
        }
    )
    assert RULE.applies(cfg) is False


def test_applies_short_circuits_when_excluded_empty(ubuntu_cfg_factory):
    # No work to do — even with enable=True, an empty excluded list
    # means the rule shouldn't run (would render a no-op apt command).
    from ks_gen.config import Packages

    cfg = ubuntu_cfg_factory().model_copy(
        update={"packages": Packages(excluded=[])}
    )
    assert RULE.applies(cfg) is False


def test_post_uses_apt_get_purge(ubuntu_cfg_factory):
    # apt-get (not apt — `apt` is interactive and not script-safe).
    # -y is the non-interactive yes flag.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "apt-get -y purge" in out


def test_post_uses_debian_frontend_noninteractive(ubuntu_cfg_factory):
    # No TTY in late-commands. Without this, a conffile-removal
    # prompt would hang the install.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "DEBIAN_FRONTEND=noninteractive" in out


def test_post_squashes_failures_with_or_true(ubuntu_cfg_factory):
    # Mirrors alma9. Squashes:
    #   exit 100 "Unable to locate package" (RHEL-flavored default
    #     excluded list against Ubuntu archive)
    #   exit 1   "package already removed" (re-run idempotency)
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "|| true" in out


def test_post_lists_all_default_excluded_packages(ubuntu_cfg_factory):
    # The 5 RHEL-flavored entries in Packages.excluded default — all
    # of them must reach the apt-get -y purge command. Cross-distro
    # name mapping is intentionally NOT done here; operators configure
    # Ubuntu-flavored names in host.yaml for real purges.
    out = RULE.emit_post(ubuntu_cfg_factory())
    for pkg in ("telnet-server", "rsh-server", "tftp-server", "vsftpd", "ypserv"):
        assert pkg in out


def test_post_reflects_excluded_override(ubuntu_cfg_factory):
    # Override is a full replacement, NOT a merge — operator gets
    # exactly the excluded list they specified.
    from ks_gen.config import Packages

    cfg = ubuntu_cfg_factory().model_copy(
        update={"packages": Packages(excluded=["apache2", "nginx"])}
    )
    out = RULE.emit_post(cfg)
    assert "apache2" in out
    assert "nginx" in out
    # Defaults MUST NOT leak in.
    assert "telnet-server" not in out
    assert "vsftpd" not in out


def test_emit_packages_returns_empty(ubuntu_cfg_factory):
    # apt-get ships with apt (Priority: required) — no apt deps needed
    # for the rule itself.
    assert RULE.emit_packages(ubuntu_cfg_factory()) == []


def test_protocol_contract(ubuntu_cfg_factory):
    from ks_gen.rules._meta import package_purge as meta

    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []
    assert RULE.exception_entry(ubuntu_cfg_factory()) is None
    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY
    assert RULE.depends_on == []
```

- [ ] **Step 3: Run the tests**

Run: `pytest tests/rules/test_ubuntu2404_package_purge.py -v`
Expected: 10 tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/ks_gen/rules/ubuntu2404/package_purge.py tests/rules/test_ubuntu2404_package_purge.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(rules/ubuntu2404): add package_purge rule (#81 phase 3.10)

apt-get -y purge mirror of alma9 dnf -y remove. Runs against
cfg.packages.excluded; DEBIAN_FRONTEND=noninteractive prevents
conffile-removal prompts in the TTY-less late-commands env.
Trailing \`|| true\` squashes:
  - exit 100 \"unable to locate package\" (the default RHEL-flavored
    excluded list against Ubuntu's archive)
  - exit 1 \"package already removed\" (idempotent re-runs)

applies gates on enable AND bool(excluded), matching alma9.
emit_tailoring + exception_entry deferred per phase 3.x pattern."
```

---

## Task 3: dod_root_ca rule skeleton + 6 tests

Same shape as usbguard (scaffolding-only) but `applies` is `not install` instead of `True`. Mirrors alma9 — the rule "fires" when NOT installing the DoD CA bundle (civilian default), so the eventual audit-story PR has a Tailored XCCDF rule to disable.

**Files:**
- Create: `src/ks_gen/rules/ubuntu2404/dod_root_ca.py`
- Create: `tests/rules/test_ubuntu2404_dod_root_ca.py`

- [ ] **Step 1: Create the rule module**

Create `src/ks_gen/rules/ubuntu2404/dod_root_ca.py` with this exact content:

```python
"""ubuntu2404 dod_root_ca rule.

Scaffolding-only port mirroring alma9. applies = not install — the
rule "fires" when the operator is NOT installing the DoD CA bundle
(default, civilian use). emit_post is empty (alma9 never
implemented the install-the-bundle branch). The meaningful work
(emit_tailoring disable of the SSG install_DoD_intermediate_certificates
rule + exception_entry) is deferred to the audit-story PR per the
phase 3.x pattern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import dod_root_ca as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return not cfg.overrides.dod_root_ca.install

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        # Deferred: ssg-ubuntu2404-ds.xml DoD certificate rule ID
        # lands in the audit-story PR.
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return ""

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        # Deferred: paired with emit_tailoring above; see audit-story PR.
        return None


RULE: Rule = cast(Rule, _Rule())
```

- [ ] **Step 2: Create the test file**

Create `tests/rules/test_ubuntu2404_dod_root_ca.py` with this exact content:

```python
from ks_gen.rules.ubuntu2404.dod_root_ca import RULE


def test_applies_when_install_is_false(ubuntu_cfg_factory):
    # Default DodRootCaCfg.install is False → applies returns True
    # (the rule "fires" when NOT installing DoD CA, mirroring alma9).
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_applies_short_circuits_when_install_is_true(ubuntu_cfg_factory):
    # When the operator opts INTO installing the DoD bundle, the rule
    # no longer needs to mark the SSG check disabled — so applies=False.
    from ks_gen.config import DodRootCaCfg, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "overrides": Overrides(
                dod_root_ca=DodRootCaCfg(install=True),
            )
        }
    )
    assert RULE.applies(cfg) is False


def test_emit_post_returns_empty(ubuntu_cfg_factory):
    # Empty body — writer's `if body:` guard skips this rule for
    # late-commands. The rule still increments Applied-rules count.
    # (Mirrors alma9 — the install-the-bundle branch was never
    # implemented in either distro.)
    assert RULE.emit_post(ubuntu_cfg_factory()) == ""


def test_emit_packages_returns_empty(ubuntu_cfg_factory):
    assert RULE.emit_packages(ubuntu_cfg_factory()) == []


def test_tailoring_and_exception_deferred(ubuntu_cfg_factory):
    # Both deferred to audit-story PR per phase 3.x pattern.
    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []
    assert RULE.exception_entry(ubuntu_cfg_factory()) is None


def test_id_and_summary_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules._meta import dod_root_ca as meta

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY
    # Mirrors meta's empty DEPENDS_ON.
    assert RULE.depends_on == []
```

- [ ] **Step 3: Run the tests**

Run: `pytest tests/rules/test_ubuntu2404_dod_root_ca.py -v`
Expected: 6 tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/ks_gen/rules/ubuntu2404/dod_root_ca.py tests/rules/test_ubuntu2404_dod_root_ca.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(rules/ubuntu2404): add dod_root_ca rule skeleton (#81 phase 3.11)

Scaffolding-only port mirroring alma9. applies = not install —
the rule \"fires\" when NOT installing the DoD CA bundle (civilian
default). emit_post is empty (alma9 never implemented the
install-the-bundle branch). The meaningful work (emit_tailoring
disable of the SSG install_DoD_intermediate_certificates rule +
paired exception_entry) is deferred to the audit-story PR per
the phase 3.x pattern.

6 tests pin: applies on install=False (default) → True, applies
short-circuits when install=True → False, emit_post empty,
emit_packages empty, tailoring + exception_entry deferred,
protocol contract (id/summary from shared meta, depends_on empty)."
```

---

## Task 4: Snapshot regen

**Files:**
- Modify: `tests/golden/__snapshots__/test_ubuntu_minimal.ambr`

- [ ] **Step 1: Confirm the golden test fails**

Run: `pytest tests/golden/ -v -k ubuntu_minimal`
Expected: FAIL — syrupy reports the diff for three new rules.

- [ ] **Step 2: Regenerate the snapshot**

Run: `pytest tests/golden/ --snapshot-update -k ubuntu_minimal`

- [ ] **Step 3: Inspect the diff**

Run: `git diff tests/golden/__snapshots__/test_ubuntu_minimal.ambr`

Expected diff (and ONLY these changes):

1. `- Applied rules: 10` → `+ Applied rules: 13` in the Summary section.
2. Three new entries in the Applied-rules list at their
   alphabetical positions:
   - `dod_root_ca` — between `crypto_policy` and `faillock_safety`
     (the meta SUMMARY is `"Skip DoD root CA bundle installation."`).
   - `package_purge` — between `kernel_module_blacklist` and `ssh_keep_open`
     (the meta SUMMARY is
     `"Remove disallowed packages after install (catches transitive pulls)."`).
   - `usbguard` — after `unattended_updates` (last alphabetically)
     (the meta SUMMARY is `"Enable or disable USBGuard install + service per overrides."`).
3. ONE new `# rule:package_purge` band inside `late-commands`
   containing:
   ```
   # Remove disallowed packages (no-op if not installed)
   DEBIAN_FRONTEND=noninteractive apt-get -y purge telnet-server rsh-server tftp-server vsftpd ypserv || true
   ```
4. **No** `# rule:usbguard` or `# rule:dod_root_ca` bands.
5. **No** addition to `autoinstall.packages:`.

If any alma9 snapshot diffs, STOP — investigate before proceeding.

**Merge-order assumption.** The 10 → 13 count assumes this branch
sits on main at `8a1f2a4` (release 0.22.0, includes phases 3.0–3.8).
If unrelated work landed first that added another rule, regenerate
and confirm "+3 your rules, nothing else."

- [ ] **Step 4: Commit the snapshot**

```bash
git add tests/golden/__snapshots__/test_ubuntu_minimal.ambr
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(golden): regen ubuntu_minimal for phases 3.9-3.11 (usbguard + package_purge + dod_root_ca)"
```

---

## Task 5: CI parity + push + PR

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
Expected: ~890 tests pass (868 from end of phase 3.8 + 22 new tests
across the three rules: 6 usbguard + 10 package_purge + 6 dod_root_ca).
Exact baseline may differ; what matters is "+22 tests, all green."

- [ ] **Step 5: Verify signed-clean**

Run: `git log --show-signature -8 --oneline`
Expected: every commit on this branch since `acdfaa2` (spec) is
signed with key `BE707B220C995478`.

- [ ] **Step 6: Push**

Run: `git push -u origin phase-3.9-3.11-bundled-ports`
Expected: push succeeds; GitHub returns the PR URL.

If push fails with `GH007`, STOP and surface to user.

- [ ] **Step 7: Open the PR**

```bash
gh pr create --title "feat(rules/ubuntu2404): usbguard + package_purge + dod_root_ca ports (#81 phases 3.9-3.11)" --body "$(cat <<'EOF'
## Summary

Bundled port of three ubuntu2404 rules (issue #81 phases 3.9, 3.10, 3.11):

- **Phase 3.9 — `usbguard`** (scaffolding-only): `applies = True`, empty `emit_post`, `emit_packages = []`. The meaningful work (`emit_tailoring` select-vs-disable on `overrides.usbguard.enable`, paired `exception_entry`, and the usbguard package install + service enable that neither distro implements yet) is deferred to the audit-story PR per the phase 3.x pattern. The rule appears in the Applied-rules count + listing in `exceptions.md` but contributes no `late-commands` band (writer's `if body:` guard at `writer.py:124`).
- **Phase 3.10 — `package_purge`**: `apt-get -y purge` mirror of alma9's `dnf -y remove`. `applies = enable AND bool(excluded)`. `DEBIAN_FRONTEND=noninteractive` prevents conffile-removal prompts in TTY-less late-commands; trailing `|| true` squashes both "unable to locate package" (exit 100, the RHEL-flavored default excluded list against Ubuntu archive) and "package already removed" (exit 1, re-run idempotency). The default `Packages.excluded` list is RHEL-flavored — cross-distro name mapping is a known schema-level follow-up (out of scope here).
- **Phase 3.11 — `dod_root_ca`** (scaffolding-only): `applies = not install` mirrors alma9 — the rule "fires" when NOT installing the DoD CA bundle (civilian default). Empty `emit_post` mirrors alma9 (the install-the-bundle branch was never implemented in either distro). `emit_tailoring` (disable the SSG `install_DoD_intermediate_certificates` rule) + paired `exception_entry` deferred to audit-story PR.

Bundled because all three are independent at the code level but each bumps the `Applied rules: N` count + Applied-rules listing in the ubuntu_minimal golden snapshot. One snapshot regen, one CI cycle.

Spec: `docs/superpowers/specs/2026-06-20-ubuntu-stig-autoinstall-phases-3-9-3-11-bundled-design.md`
Plan: `docs/superpowers/plans/2026-06-20-ubuntu-stig-autoinstall-phases-3-9-3-11-bundled.md`

## Test plan

- [x] **usbguard** — 6 new unit tests in `tests/rules/test_ubuntu2404_usbguard.py` cover: `applies` always True, `emit_post` empty, `emit_packages` empty, `emit_tailoring` deferred, `exception_entry` deferred, protocol contract (`id`/`summary` from shared meta, `depends_on` empty).
- [x] **package_purge** — 10 new unit tests in `tests/rules/test_ubuntu2404_package_purge.py` cover: `applies` default-True (enable + excluded), `applies` short-circuits on `enable=False`, `applies` short-circuits on `excluded=[]`, `apt-get -y purge` present, `DEBIAN_FRONTEND=noninteractive` present, `|| true` present, all 5 default excluded packages present, operator override flow-through (custom list lands, defaults absent), `emit_packages` empty, protocol contract.
- [x] **dod_root_ca** — 6 new unit tests in `tests/rules/test_ubuntu2404_dod_root_ca.py` cover: `applies` default-True (install=False default), `applies` short-circuits on `install=True`, `emit_post` empty, `emit_packages` empty, `emit_tailoring` + `exception_entry` deferred, protocol contract.
- [x] `tests/golden/__snapshots__/test_ubuntu_minimal.ambr` regenerated — diff bumps Applied-rules header 10 → 13, inserts three new lines into the Applied-rules listing at their alphabetical positions, and adds ONE new `# rule:package_purge` band to `late-commands` (no bands for usbguard or dod_root_ca — empty `emit_post`). No alma9 snapshot changes. No `autoinstall.packages:` addition.
- [x] Full CI chain run locally: `ruff check && ruff format --check && mypy && pytest -q` — all four green (~890 passed = 868 + 22 new).
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
