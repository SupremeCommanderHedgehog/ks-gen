# Phase 3.8 — `kernel_module_blacklist` port to ubuntu2404 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the `kernel_module_blacklist` rule to ubuntu2404 so the generated autoinstall writes `/etc/modprobe.d/ks-gen-blacklist.conf` with `install <module> /bin/true` lines for each operator-configured kernel module.

**Architecture:** One new rule module + one new test file. `emit_post` writes a single modprobe drop-in via heredoc (mirrors the alma9 implementation almost verbatim — `/etc/modprobe.d/` is shared between Debian-family and RHEL-family). `emit_packages` returns `[]` because `kmod` is Essential on Ubuntu. `applies()` gates on `cfg.overrides.kernel_module_blacklist.enable` (matches alma9). `emit_tailoring` + `exception_entry` deferred to audit-story PR per phase 3.x pattern.

**Tech Stack:** Python 3.11+, pydantic v2, jinja2, syrupy snapshots, pytest, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-06-20-ubuntu-stig-autoinstall-phase-3-8-kernel-module-blacklist-design.md`

**Branch:** `phase-3.8-kernel-module-blacklist` (already created off main at `d362e47`; spec already committed at `1a2d7a8`).

---

## Reference patterns

- **alma9 sibling:** `src/ks_gen/rules/alma9/kernel_module_blacklist.py` — semantic source for the install-trick body, the heredoc, and the `chmod 644`. The ubuntu port is essentially the same file with a docstring change and `applies()` semantics preserved.
- **Closest ubuntu2404 sibling (write-only heredoc):** `src/ks_gen/rules/ubuntu2404/time_servers.py` (phase 3.3) — also writes one config file via `cat > X <<'__KS_GEN_EOF__'`, same shell shape that survives `shlex.quote` wrapping in `skeleton._format_late_commands`.
- **Test sibling:** `tests/rules/test_ubuntu2404_faillock_safety.py` — module-level `from ... import RULE` at top, local `from ks_gen.config import ...` inside per-test override functions.

The `KernelModuleBlacklistCfg` schema lives at `src/ks_gen/config.py:590-603`:

```python
class KernelModuleBlacklistCfg(StrictModel):
    enable: bool = True
    modules: list[str] = Field(
        default_factory=lambda: [
            "usb-storage",
            "cramfs",
            "freevxfs",
            "jffs2",
            "hfs",
            "hfsplus",
            "squashfs",
            "udf",
        ]
    )
```

Has a parent `enable: True` flag — the rule's `applies` returns `cfg.overrides.kernel_module_blacklist.enable`. Operator opts out by setting `enable: false` in `host.yaml`.

Override pattern in tests:

```python
from ks_gen.config import KernelModuleBlacklistCfg, Overrides

cfg = ubuntu_cfg_factory().model_copy(
    update={"overrides": Overrides(
        kernel_module_blacklist=KernelModuleBlacklistCfg(enable=False),
    )}
)
```

---

## Task 1: Rule skeleton + first failing test

Create the rule file with the full `_emit` helper in one TDD shot. The body is small and the alma9 reference is near-verbatim, so incrementally building it out adds no review value. Add one failing path test (on `/etc/modprobe.d/ks-gen-blacklist.conf`) to drive the wiring.

**Files:**
- Create: `src/ks_gen/rules/ubuntu2404/kernel_module_blacklist.py`
- Create: `tests/rules/test_ubuntu2404_kernel_module_blacklist.py`

- [ ] **Step 1: Write the failing test**

Create `tests/rules/test_ubuntu2404_kernel_module_blacklist.py` with this exact content:

```python
from ks_gen.rules.ubuntu2404.kernel_module_blacklist import RULE


def test_post_writes_modprobe_blacklist_conf_path(ubuntu_cfg_factory):
    # /etc/modprobe.d/ is the canonical drop-in directory on both
    # Debian-family and RHEL-family systems — modprobe reads every
    # *.conf file there at module-load time. The "ks-gen-" prefix
    # avoids collision with Debian-shipped blacklist-*.conf files.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/modprobe.d/ks-gen-blacklist.conf" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/rules/test_ubuntu2404_kernel_module_blacklist.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ks_gen.rules.ubuntu2404.kernel_module_blacklist'`

- [ ] **Step 3: Create the rule module**

Create `src/ks_gen/rules/ubuntu2404/kernel_module_blacklist.py` with this exact content:

```python
"""ubuntu2404 kernel_module_blacklist rule.

Writes /etc/modprobe.d/ks-gen-blacklist.conf with modprobe
install-trick entries (install <module> /bin/true) for each
operator-configured kernel module. Prevents the kernel from loading
disallowed/unused modules at boot or on hot-plug.

`modprobe` ships in the `kmod` package (Essential: yes on Ubuntu
Server), so no apt deps are required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import kernel_module_blacklist as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


def _emit(cfg: HostConfig) -> str:
    modules = cfg.overrides.kernel_module_blacklist.modules
    body = "\n".join(f"install {m} /bin/true" for m in modules)
    return f"""\
# Disable specific kernel modules via modprobe install-trick
cat > /etc/modprobe.d/ks-gen-blacklist.conf <<'__KS_GEN_EOF__'
{body}
__KS_GEN_EOF__
chmod 644 /etc/modprobe.d/ks-gen-blacklist.conf
"""


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return cfg.overrides.kernel_module_blacklist.enable

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        # Deferred: ssg-ubuntu2404-ds.xml kernel-module-disablement rule
        # IDs land in the audit-story PR.
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        # `modprobe` ships in `kmod` (Essential: yes on Ubuntu).
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        # Deferred: paired with emit_tailoring above; see audit-story PR.
        return None


RULE: Rule = cast(Rule, _Rule())
```

No edit to `src/ks_gen/rules/ubuntu2404/__init__.py` — registry uses `pkgutil.iter_modules` auto-discovery.

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/rules/test_ubuntu2404_kernel_module_blacklist.py -v`
Expected: PASS — `test_post_writes_modprobe_blacklist_conf_path` is green.

- [ ] **Step 5: Commit**

```bash
git add tests/rules/test_ubuntu2404_kernel_module_blacklist.py src/ks_gen/rules/ubuntu2404/kernel_module_blacklist.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(rules/ubuntu2404): add kernel_module_blacklist rule skeleton (#81 phase 3.8)

Mirrors the alma9 rule almost verbatim — /etc/modprobe.d/ is shared
between Debian-family and RHEL-family, and the modprobe install-trick
(install <module> /bin/true) is universal. Writes
/etc/modprobe.d/ks-gen-blacklist.conf with one install line per
operator-configured module.

emit_packages returns [] because kmod is essential on Ubuntu
(modprobe always available). applies() gates on
cfg.overrides.kernel_module_blacklist.enable (matches alma9).

emit_tailoring + exception_entry deferred to audit-story PR per
phase 3.x pattern.

First test pins the /etc/modprobe.d/ks-gen-blacklist.conf path."
```

NO `Co-Authored-By` trailer in the commit message.

If pre-commit hook regenerates the golden snapshot (the registry auto-discovery picks up the new rule), STAGE THOSE CHANGES and amend so the commit is whole. Same pattern as phase 3.4/3.5/3.6/3.7.

---

## Task 2: `applies` semantics + remaining path/shape tests

Two `applies` tests (default-True + disabled-False) plus `chmod` and `install-trick shape` defensive pins.

**Files:**
- Modify: `tests/rules/test_ubuntu2404_kernel_module_blacklist.py`

- [ ] **Step 1: Append four tests**

```python


def test_applies_when_enabled(ubuntu_cfg_factory):
    # Default cfg.overrides.kernel_module_blacklist.enable is True.
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_applies_short_circuits_when_disabled(ubuntu_cfg_factory):
    # When the operator sets enable=False, the rule is excluded from
    # late-commands entirely (the registry's applies() filter drops it).
    from ks_gen.config import KernelModuleBlacklistCfg, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(
            kernel_module_blacklist=KernelModuleBlacklistCfg(enable=False),
        )}
    )
    assert RULE.applies(cfg) is False


def test_post_chmods_blacklist_conf_644(ubuntu_cfg_factory):
    # Mirrors alma9 — modprobe reads the file world-readable. The
    # explicit chmod is defensive (Debian's umask 022 would already
    # produce 644) but keeps the rule's surface identical across distros.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "chmod 644 /etc/modprobe.d/ks-gen-blacklist.conf" in out


def test_post_uses_install_trick_with_bin_true(ubuntu_cfg_factory):
    # The install-trick (install <m> /bin/true) is strictly stronger
    # than "blacklist <m>" — modprobe itself refuses to load the
    # module instead of relying on udev to honor a blacklist hint.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "install " in out
    assert " /bin/true" in out
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/rules/test_ubuntu2404_kernel_module_blacklist.py -v`
Expected: 5 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_kernel_module_blacklist.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert kernel_module_blacklist applies + chmod + install-trick shape"
```

---

## Task 3: Default-module coverage

One test asserting all eight defaults (`usb-storage`, `cramfs`, `freevxfs`, `jffs2`, `hfs`, `hfsplus`, `squashfs`, `udf`) appear as `install <m> /bin/true` lines.

**Files:**
- Modify: `tests/rules/test_ubuntu2404_kernel_module_blacklist.py`

- [ ] **Step 1: Append one test**

```python


def test_post_includes_all_eight_default_modules(ubuntu_cfg_factory):
    # Default list comes from KernelModuleBlacklistCfg.modules — eight
    # filesystem/removable-media modules required disabled by the STIG
    # profile. Each must appear as a full install-trick line.
    out = RULE.emit_post(ubuntu_cfg_factory())
    for module in (
        "usb-storage",
        "cramfs",
        "freevxfs",
        "jffs2",
        "hfs",
        "hfsplus",
        "squashfs",
        "udf",
    ):
        assert f"install {module} /bin/true" in out
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/rules/test_ubuntu2404_kernel_module_blacklist.py -v`
Expected: 6 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_kernel_module_blacklist.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert kernel_module_blacklist covers all eight default modules"
```

---

## Task 4: Cfg-override responsiveness tests

Two tests: operator-supplied list fully replaces defaults; empty-list override produces a heredoc with no install lines.

**Files:**
- Modify: `tests/rules/test_ubuntu2404_kernel_module_blacklist.py`

- [ ] **Step 1: Append two override tests**

```python


def test_post_reflects_modules_override_replaces_default_list(ubuntu_cfg_factory):
    # Override is a full replacement, NOT a merge — operator gets
    # exactly the modules they specified, no implicit defaults.
    from ks_gen.config import KernelModuleBlacklistCfg, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(
            kernel_module_blacklist=KernelModuleBlacklistCfg(modules=["dccp", "rds"]),
        )}
    )
    out = RULE.emit_post(cfg)
    assert "install dccp /bin/true" in out
    assert "install rds /bin/true" in out
    # Default modules MUST NOT leak in.
    assert "install usb-storage /bin/true" not in out
    assert "install cramfs /bin/true" not in out


def test_post_reflects_empty_modules_override(ubuntu_cfg_factory):
    # Operator can configure modules=[] to keep the rule applied
    # (file exists, audit checks pass) but disable any specific
    # module. The heredoc still runs; just no install lines.
    from ks_gen.config import KernelModuleBlacklistCfg, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(
            kernel_module_blacklist=KernelModuleBlacklistCfg(modules=[]),
        )}
    )
    out = RULE.emit_post(cfg)
    # File still created + chmod'd.
    assert "/etc/modprobe.d/ks-gen-blacklist.conf" in out
    assert "chmod 644 /etc/modprobe.d/ks-gen-blacklist.conf" in out
    # But no install-trick line lands.
    assert "install " not in out
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/rules/test_ubuntu2404_kernel_module_blacklist.py -v`
Expected: 8 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_kernel_module_blacklist.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert kernel_module_blacklist cfg overrides flow through"
```

---

## Task 5: Packages + Protocol contract tests

Five tests guarding the remaining contract surfaces: `emit_packages` returns `[]`, `emit_tailoring` deferred, `exception_entry` deferred, `depends_on` is empty, and meta-derived attributes (`id`, `summary`).

**Files:**
- Modify: `tests/rules/test_ubuntu2404_kernel_module_blacklist.py`

- [ ] **Step 1: Append five contract tests**

```python


def test_emit_packages_returns_empty(ubuntu_cfg_factory):
    # `modprobe` ships in `kmod` (Essential: yes on Ubuntu Server) —
    # always present, no apt deps required.
    assert RULE.emit_packages(ubuntu_cfg_factory()) == []


def test_emit_tailoring_returns_empty_deferred(ubuntu_cfg_factory):
    # Deferred: ssg-ubuntu2404-ds.xml kernel_module_<m>_disabled
    # rule IDs land in the audit-story PR.
    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []


def test_exception_entry_returns_none_deferred(ubuntu_cfg_factory):
    # Deferred: paired with emit_tailoring above. May remain None
    # permanently if there's no operator-facing exception story.
    assert RULE.exception_entry(ubuntu_cfg_factory()) is None


def test_depends_on_is_empty(ubuntu_cfg_factory):
    # Mirrors meta's empty DEPENDS_ON.
    assert RULE.depends_on == []


def test_id_and_summary_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules._meta import kernel_module_blacklist as meta

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY
```

- [ ] **Step 2: Run all tests in the file**

Run: `pytest tests/rules/test_ubuntu2404_kernel_module_blacklist.py -v`
Expected: 13 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_kernel_module_blacklist.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert protocol contract for kernel_module_blacklist"
```

---

## Task 6: Snapshot regen

**Files:**
- Modify: `tests/golden/__snapshots__/test_ubuntu_minimal.ambr`

- [ ] **Step 1: Run the golden test to confirm it fails**

Run: `pytest tests/golden/ -v -k ubuntu_minimal`
Expected: FAIL — syrupy reports the snapshot diff for the new
`kernel_module_blacklist` band.

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

1. `- Applied rules: 9` → `+ Applied rules: 10` in the Summary section.
2. `+ - \`kernel_module_blacklist\` — Write modprobe blacklist for
   unused/disallowed kernel modules.` inserted at its sorted
   position in the Applied-rules list (alphabetical, between
   `faillock_safety` and `ssh_*`).
3. A new `# rule:kernel_module_blacklist ──────────...` band
   inside `late-commands` containing the heredoc, eight
   `install <m> /bin/true` lines, the EOF marker, and the chmod
   line.
4. **No** addition to `autoinstall.packages:` (`emit_packages`
   returns `[]`).

If any alma9 snapshot diffs, STOP — investigate before proceeding.

**Merge-order assumption.** The 9 → 10 count assumes this branch
sits on main at `d362e47` (release 0.21.0, phases
3.0/3.1/3.2/3.3/3.4/3.5/3.6/3.7 merged = 9 ubuntu rules). If
unrelated work landed first that added another rule, regenerate and
confirm "+1 your rule, nothing else."

- [ ] **Step 4: Commit the snapshot (if not already in Task 1's commit)**

```bash
git add tests/golden/__snapshots__/test_ubuntu_minimal.ambr
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(golden): regen ubuntu_minimal snapshot for kernel_module_blacklist rule"
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
Expected: ~868 tests pass (855 from end of phase 3.7 + 13 new
kernel_module_blacklist tests). Exact baseline may differ if other
work has landed since v0.21.0 — what matters is "+13 tests, all
green."

- [ ] **Step 5: Verify signed-clean**

Run: `git log --show-signature -8 --oneline`
Expected: every commit on this branch since `1a2d7a8` (spec) is
signed with key `BE707B220C995478`.

- [ ] **Step 6: Push**

Run: `git push -u origin phase-3.8-kernel-module-blacklist`
Expected: push succeeds; GitHub returns the PR URL.

If push fails with `GH007`, STOP and surface to user.

- [ ] **Step 7: Open the PR**

```bash
gh pr create --title "feat(rules/ubuntu2404): kernel_module_blacklist port (#81 phase 3.8)" --body "$(cat <<'EOF'
## Summary

- Ports the `kernel_module_blacklist` rule to ubuntu2404 (issue #81 phase 3.8).
- Single-block port: writes `/etc/modprobe.d/ks-gen-blacklist.conf` with `install <module> /bin/true` lines for each operator-configured kernel module. Defaults are the same eight modules the alma9 rule blacklists (`usb-storage`, `cramfs`, `freevxfs`, `jffs2`, `hfs`, `hfsplus`, `squashfs`, `udf`).
- `emit_packages` returns `[]` because `kmod` (which ships `modprobe`) is `Essential: yes` on Ubuntu Server — always present, no apt deps needed.
- `applies()` returns `cfg.overrides.kernel_module_blacklist.enable` — operator can opt out via `host.yaml` (matches alma9).
- `emit_tailoring` + `exception_entry` deferred to the audit-story PR (consistent with phases 3.1–3.7).
- Path `/etc/modprobe.d/` is shared between Debian-family and RHEL-family systems, so this is the most mechanical port in the phase-3.x series — file, heredoc, install-trick body, and chmod all transfer verbatim from alma9. Only the docstring changed.

Spec: `docs/superpowers/specs/2026-06-20-ubuntu-stig-autoinstall-phase-3-8-kernel-module-blacklist-design.md`
Plan: `docs/superpowers/plans/2026-06-20-ubuntu-stig-autoinstall-phase-3-8-kernel-module-blacklist.md`

## Test plan

- [x] 13 new unit tests in `tests/rules/test_ubuntu2404_kernel_module_blacklist.py` cover: `/etc/modprobe.d/ks-gen-blacklist.conf` path, `applies` default-True / disabled-False, `chmod 644`, install-trick shape (`install ` and ` /bin/true`), all eight default modules present as full install lines, modules-override full replacement (custom list lands, defaults absent), empty-modules override (file + chmod still emitted, no install lines), `emit_packages == []`, and the Rule Protocol contract (`id`, `summary`, `depends_on`, deferred `emit_tailoring` / `exception_entry`).
- [x] `tests/golden/__snapshots__/test_ubuntu_minimal.ambr` regenerated — diff adds the `# rule:kernel_module_blacklist` band (heredoc + eight install lines + chmod), bumps Applied-rules header 9 → 10, and inserts the rule's summary line into the Applied-rules list. No alma9 snapshot changes. No autoinstall.packages: addition.
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
