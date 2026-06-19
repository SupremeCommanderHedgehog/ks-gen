# Phase 3.3 — `time_servers` port to ubuntu2404 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the `time_servers` rule to ubuntu2404 so the generated autoinstall configures chrony with civilian NTP servers from `cfg.time.servers`.

**Architecture:** One new rule module + one new test file mirror the alma9 pattern. The shared `_meta/time_servers.py` is unchanged (already distro-agnostic). The rule plugs into the existing ubuntu2404 bundle pipeline: `emit_post` contributes a `# rule:time_servers` block to `late-commands`, and `emit_packages` returns `["chrony"]` which flows into `autoinstall.packages:` via plumbing landed in PR #99. This rule is the first ubuntu2404 rule to actually exercise that plumbing — banner_text and ssh_config_apply both return `[]`.

**Tech Stack:** Python 3.11+, pydantic v2 `StrictModel`, jinja2, syrupy snapshots, pytest, ruff, mypy. Same toolchain as prior ubuntu2404 ports.

**Spec:** `docs/superpowers/specs/2026-06-19-ubuntu-stig-autoinstall-phase-3-3-time-servers-design.md`

**Branch:** `feat/phase-3-3-time-servers` (already created off main at `9a1b094`; spec already committed at `e8bd493`).

---

## Reference patterns

The implementer should mirror these established files. They're authoritative for code style, comment voice, and test shape:

- **alma9 sibling:** `src/ks_gen/rules/alma9/time_servers.py` — the rule we're porting.
- **Closest ubuntu2404 sibling:** `src/ks_gen/rules/ubuntu2404/ssh_config_apply.py` — uses the top-level `_emit(cfg)` helper for f-string readability + `_Rule` dataclass + `RULE: Rule = cast(Rule, _Rule())` module-level binding, all with `Deferred:` comments on tailoring/exception.
- **Test sibling:** `tests/rules/test_ubuntu2404_ssh_config_apply.py` — module-level `from ... import RULE` at top of file, no inline imports inside test functions.
- **Writer test sibling:** `tests/test_writer.py::test_build_bundle_ubuntu2404_packages_block_includes_ufw_when_ssh_keep_open_applies` (lines 374-396) — pattern for end-to-end "rule package threads into autoinstall.packages" assertion via `yaml.safe_load` of `bundle.user_data`.

The `ubuntu_cfg_factory` fixture is defined in `tests/conftest.py`. It returns a callable; default invocation `ubuntu_cfg_factory()` yields a HostConfig with `distro="ubuntu2404"`, `hostname="u2404-host"`, admin user `"ops"` with one ed25519 key.

---

## Task 1: Failing test fixture for the rule module

This task creates the test file with one failing test that proves the rule module doesn't yet exist. Subsequent tasks build out the rule and the rest of the tests.

**Files:**
- Create: `tests/rules/test_ubuntu2404_time_servers.py`

- [ ] **Step 1: Write the failing test**

Create `tests/rules/test_ubuntu2404_time_servers.py` with this content:

```python
from ks_gen.rules.ubuntu2404.time_servers import RULE


def test_post_writes_chrony_conf_at_ubuntu_path(ubuntu_cfg_factory):
    # Ubuntu's chrony package owns /etc/chrony/ as a directory; the
    # config file lives at /etc/chrony/chrony.conf (not /etc/chrony.conf
    # as on RHEL). Strict path assertion catches drift.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/chrony/chrony.conf" in out
    # Bare /etc/chrony.conf (no subdirectory) is the alma9 path — must
    # not appear in the ubuntu output.
    assert "/etc/chrony.conf\n" not in out
    assert "/etc/chrony.conf " not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/rules/test_ubuntu2404_time_servers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ks_gen.rules.ubuntu2404.time_servers'`

- [ ] **Step 3: Create the rule module with minimal scaffolding**

Create `src/ks_gen/rules/ubuntu2404/time_servers.py`:

```python
"""ubuntu2404 chrony NTP configuration.

Writes /etc/chrony/chrony.conf with operator-chosen servers from
cfg.time.servers. Adds the chrony package to autoinstall.packages so
it's present in the chroot before this late-command runs. Service
activation and systemd-timesyncd masking are owned by chrony's apt
postinst (Conflicts=systemd-timesyncd.service) — same config-only
stance as the alma9 rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import time_servers as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


def _emit(cfg: HostConfig) -> str:
    servers = "\n".join(f"server {s} iburst" for s in cfg.time.servers)
    thresh = cfg.time.chrony_makestep_threshold
    return f"""\
# Chrony configuration (servers from host.yaml; STIG-compliant base)
install -d -m 755 /etc/chrony
cat > /etc/chrony/chrony.conf <<'__KS_GEN_EOF__'
{servers}
driftfile /var/lib/chrony/chrony.drift
makestep {thresh} 3
rtcsync
logdir /var/log/chrony
__KS_GEN_EOF__
chmod 644 /etc/chrony/chrony.conf
"""


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        # Deferred: ssg-ubuntu2404-ds.xml time/NTP rule survey lands in the audit-story PR.
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return ["chrony"]

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        # Deferred: paired with emit_tailoring above; see audit-story PR.
        return None


RULE: Rule = cast(Rule, _Rule())
```

No edit to `src/ks_gen/rules/ubuntu2404/__init__.py` is needed — the registry uses `pkgutil.iter_modules` to auto-discover rule modules. (Sanity check the file with `Grep` for `iter_modules` in `src/ks_gen/registry.py` if uncertain.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/rules/test_ubuntu2404_time_servers.py -v`
Expected: PASS — `test_post_writes_chrony_conf_at_ubuntu_path` is green.

- [ ] **Step 5: Commit (test + minimal rule together because the test cannot pass without the module)**

```bash
git add tests/rules/test_ubuntu2404_time_servers.py src/ks_gen/rules/ubuntu2404/time_servers.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(rules/ubuntu2404): add time_servers rule skeleton (#81 phase 3.3)

Writes /etc/chrony/chrony.conf at Ubuntu's path with servers from
cfg.time.servers; emit_packages returns ['chrony']. emit_tailoring +
exception_entry deferred to audit-story PR.

First test pins the chrony.conf path divergence from alma9."
```

---

## Task 2: Add per-server line tests

The minimal `_emit` already emits server lines correctly; this task just adds the assertions that protect against future drift.

**Files:**
- Modify: `tests/rules/test_ubuntu2404_time_servers.py`

- [ ] **Step 1: Append three server-content tests**

Append to `tests/rules/test_ubuntu2404_time_servers.py`:

```python
def test_post_writes_server_lines_for_default_pool(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "server pool.ntp.org iburst" in out


def test_post_handles_multiple_servers(ubuntu_cfg_factory):
    from ks_gen.config import Time

    cfg = ubuntu_cfg_factory().model_copy(
        update={"time": Time(servers=["a.example", "b.example"])}
    )
    out = RULE.emit_post(cfg)
    assert "server a.example iburst" in out
    assert "server b.example iburst" in out


def test_post_no_dod_servers_in_output(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "usno" not in out.lower()
    assert "navy.mil" not in out.lower()
```

- [ ] **Step 2: Run the three new tests to verify they pass**

Run: `pytest tests/rules/test_ubuntu2404_time_servers.py -v`
Expected: all 4 tests pass (the 1 from Task 1 + the 3 new).

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_time_servers.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert chrony server lines + no-DoD output"
```

---

## Task 3: Add config-shape tests (driftfile, makestep, mode, install dir)

These tests pin the body content that diverges from alma9 (driftfile name, install -d helper) plus the cfg-driven knobs (makestep threshold).

**Files:**
- Modify: `tests/rules/test_ubuntu2404_time_servers.py`

- [ ] **Step 1: Append four config-shape tests**

Append to `tests/rules/test_ubuntu2404_time_servers.py`:

```python
def test_post_emits_drift_logdir_rtcsync(ubuntu_cfg_factory):
    # Ubuntu's chrony package default driftfile is /var/lib/chrony/chrony.drift,
    # which is what its apparmor profile (usr.sbin.chronyd) allows. alma uses
    # /var/lib/chrony/drift (no extension) — diverges by design.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "driftfile /var/lib/chrony/chrony.drift" in out
    assert "logdir /var/log/chrony" in out
    assert "rtcsync" in out


def test_post_uses_configured_makestep_threshold(ubuntu_cfg_factory):
    from ks_gen.config import Time

    cfg = ubuntu_cfg_factory().model_copy(
        update={"time": Time(servers=["pool.ntp.org"], chrony_makestep_threshold=2.5)}
    )
    out = RULE.emit_post(cfg)
    assert "makestep 2.5 3" in out


def test_post_chmod_644(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "chmod 644 /etc/chrony/chrony.conf" in out


def test_post_uses_install_dir_for_chrony_dir(ubuntu_cfg_factory):
    # Idempotent safety belt: when the late-command re-runs (rare but
    # possible during install debugging), `install -d` no-ops if the
    # directory already exists. chrony's apt postinst creates it during
    # package install, so on a fresh run this is a no-op.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "install -d -m 755 /etc/chrony" in out
```

- [ ] **Step 2: Run the four new tests to verify they pass**

Run: `pytest tests/rules/test_ubuntu2404_time_servers.py -v`
Expected: all 8 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_time_servers.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert chrony config shape (driftfile/makestep/mode)"
```

---

## Task 4: Add protocol-level tests (applies / deferred tailoring + exception / emit_packages / meta wiring)

These mirror the protocol-level tests in `test_ubuntu2404_ssh_config_apply.py` exactly. They guard against the protocol contract drifting.

**Files:**
- Modify: `tests/rules/test_ubuntu2404_time_servers.py`

- [ ] **Step 1: Append six protocol tests**

Append to `tests/rules/test_ubuntu2404_time_servers.py`:

```python
def test_applies_always_true(ubuntu_cfg_factory):
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_emit_tailoring_returns_empty_deferred(ubuntu_cfg_factory):
    # Deferred until ssg-ubuntu2404-ds.xml NTP rule survey lands in the
    # audit-story PR.
    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []


def test_exception_entry_returns_none_deferred(ubuntu_cfg_factory):
    # Deferred until ssg-ubuntu2404-ds.xml NTP rule survey lands.
    assert RULE.exception_entry(ubuntu_cfg_factory()) is None


def test_emit_packages_returns_chrony(ubuntu_cfg_factory):
    # chrony is NOT in Ubuntu Server's minimal install. This rule is the
    # first ubuntu2404 rule to actually contribute a package to
    # autoinstall.packages via the rule_packages plumbing from PR #99.
    assert RULE.emit_packages(ubuntu_cfg_factory()) == ["chrony"]


def test_depends_on_is_empty(ubuntu_cfg_factory):
    # Mirrors meta's empty DEPENDS_ON.
    assert RULE.depends_on == []


def test_id_and_summary_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules._meta import time_servers as meta

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY
```

- [ ] **Step 2: Run all tests in the file**

Run: `pytest tests/rules/test_ubuntu2404_time_servers.py -v`
Expected: all 14 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_time_servers.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert protocol contract for time_servers"
```

---

## Task 5: End-to-end test — chrony threads into `autoinstall.packages`

This task adds one writer-level integration test proving the
`emit_packages → rule_packages → render_user_data → autoinstall.packages:`
pipeline works end-to-end with a real rule that contributes a package.
Pattern mirrors `test_build_bundle_ubuntu2404_packages_block_includes_ufw_when_ssh_keep_open_applies`
at `tests/test_writer.py:374-396`.

**Files:**
- Modify: `tests/test_writer.py`

- [ ] **Step 1: Read the surrounding context once**

Read lines 374-396 of `tests/test_writer.py` to confirm the existing
ufw-checking test's exact shape (imports, fixtures, yaml parsing). Place
the new test directly below it so the two related "package threads into
autoinstall.packages" tests live side by side.

- [ ] **Step 2: Append the new writer test**

Add this test function immediately after
`test_build_bundle_ubuntu2404_packages_block_includes_ufw_when_ssh_keep_open_applies`
in `tests/test_writer.py`:

```python
def test_build_bundle_ubuntu2404_packages_includes_chrony_when_time_servers_applies(tmp_path):
    # time_servers.applies(cfg) is always True, and its emit_packages
    # returns ["chrony"] because chrony isn't in Ubuntu Server's minimal
    # install. A ubuntu2404 bundle must surface "chrony" in
    # autoinstall.packages so the chroot has chrony before time_servers'
    # late-command writes /etc/chrony/chrony.conf.
    yaml_text = textwrap.dedent(
        """\
        distro: ubuntu2404
        system: {hostname: u24-chrony}
        user:
          admin:
            name: ops
            authorized_keys: ["ssh-ed25519 AAAA a@b"]
            sudo: nopasswd_yes
        """
    )
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(yaml_text, encoding="utf-8")
    cfg = load_host_config(cfg_path, sets=[])
    bundle = build_bundle(cfg)
    assert bundle.user_data is not None
    doc = yaml.safe_load(bundle.user_data)
    assert "chrony" in doc["autoinstall"]["packages"]
```

`textwrap`, `yaml`, `load_host_config`, and `build_bundle` are already
imported at the top of `tests/test_writer.py` (they're used by the ufw
test). No new imports needed.

- [ ] **Step 3: Run the new writer test**

Run: `pytest tests/test_writer.py::test_build_bundle_ubuntu2404_packages_includes_chrony_when_time_servers_applies -v`
Expected: PASS — the rule was wired through in Task 1; this test proves the wiring works end-to-end.

- [ ] **Step 4: Commit**

```bash
git add tests/test_writer.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(writer): assert chrony reaches autoinstall.packages for ubuntu2404"
```

---

## Task 6: Regenerate the ubuntu_minimal golden snapshot

The new rule's late-command body and the new `autoinstall.packages:`
block must be captured in the golden snapshot for `test_ubuntu_minimal`.

**Files:**
- Modify: `tests/golden/__snapshots__/test_ubuntu_minimal.ambr`

- [ ] **Step 1: Run the golden test to confirm it fails**

Run: `pytest tests/golden/ -v -k ubuntu_minimal`
Expected: FAIL — syrupy reports the snapshot diff for the new chrony block + the new `autoinstall.packages` section.

- [ ] **Step 2: Regenerate the snapshot**

Run: `pytest tests/golden/ --snapshot-update -k ubuntu_minimal`
Expected: pass; the `.ambr` file is updated.

- [ ] **Step 3: Inspect the diff before committing**

Run: `git diff tests/golden/__snapshots__/test_ubuntu_minimal.ambr`

Expected diff (and ONLY these changes):

1. A new `autoinstall.packages:` block under `autoinstall:` with `- "chrony"` as its first/only entry. (Empty rule_packages list is elided by `{% if rule_packages %}` in the user-data template — that's why the block didn't exist before.)
2. A new `# rule:time_servers ──────────...` band inside `late-commands` containing the exact body from `_emit` (cat heredoc writing `/etc/chrony/chrony.conf`, `chmod 644`, `install -d` mkdir).
3. The "Applied rules: N" header in the late-commands intro comment bumps from 4 to 5.

If any alma9 snapshot diffs, STOP — that's a bug, investigate before proceeding.

**Merge-order assumption.** The 4 → 5 count assumes this branch sits on top of main at `9a1b094` (phases 3.0/3.1/3.2 already merged = 4 rules). If main has moved and another ubuntu2404 rule landed first, the count is whatever +1 produces; verify the diff is "+1 your rule, nothing else."

- [ ] **Step 4: Commit the regenerated snapshot**

```bash
git add tests/golden/__snapshots__/test_ubuntu_minimal.ambr
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(golden): regen ubuntu_minimal snapshot for time_servers rule"
```

---

## Task 7: CI parity check + push

Per `CLAUDE.md`, run the full local CI chain in the exact order CI runs
it. `ruff format --check` is a separate gate from `ruff check` and has
bounced PRs on this workstream before (phases 3.1 and 3.2 both hit this).

**Files:**
- (no source changes — running tooling only)

- [ ] **Step 1: Run ruff check**

Run: `ruff check src tests`
Expected: `All checks passed!`

If failures: read the diagnostic, fix in source, re-run. Common cause:
unused import (`F401`).

- [ ] **Step 2: Run ruff format --check**

Run: `ruff format --check src tests`
Expected: `N files already formatted` (no diff).

If `Would reformat: ...` appears: run `ruff format src tests`, then
re-run `ruff format --check src tests` to confirm clean, then add the
formatted files. Phase 3.2 hit this with the heredoc indentation —
formatter is the source of truth.

If files were reformatted, commit them:

```bash
git add -u
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "style: ruff format src tests"
```

- [ ] **Step 3: Run mypy**

Run: `mypy`
Expected: `Success: no issues found in N source files`

If failures: read the type error, fix in source, re-run.

- [ ] **Step 4: Run pytest**

Run: `pytest -q`
Expected: all tests pass (including the 14 new rule tests, the 1 new
writer test, and the regenerated golden snapshot).

- [ ] **Step 5: Verify branch is signed-clean and ready to push**

Run: `git log --show-signature -5 --oneline`
Expected: each commit on `feat/phase-3-3-time-servers` shows
`Good signature from "Patrick Connallon (SupremeCommanderHedgehog) <github.v5f9w@bitbucket.onl>"` with key `BE707B220C995478`.

- [ ] **Step 6: Push the branch**

Run: `git push -u origin feat/phase-3-3-time-servers`
Expected: push succeeds; GitHub returns the URL for opening a PR.

If push fails with `GH007: Your push would publish a private email address`,
STOP and surface to the user — do NOT fall back to the `users.noreply.github.com`
form silently. See `~/.claude/CLAUDE.md` for the resolution.

- [ ] **Step 7: Open the PR**

Run:

```bash
gh pr create --title "feat(rules/ubuntu2404): time_servers port (#81 phase 3.3)" --body "$(cat <<'EOF'
## Summary

- Ports the `time_servers` rule to ubuntu2404 (issue #81 phase 3.3).
- Writes `/etc/chrony/chrony.conf` (Ubuntu's path) with servers from `cfg.time.servers` — civilian-default `pool.ntp.org`.
- First ubuntu2404 rule that actually exercises the `rule_packages → autoinstall.packages` plumbing landed in #99: `emit_packages` returns `["chrony"]` because chrony isn't in Ubuntu Server's minimal install.
- `systemd-timesyncd` masking is owned by chrony's apt postinst (`Conflicts=systemd-timesyncd.service`) — no explicit late-command, mirrors alma9's config-only stance.
- `emit_tailoring` + `exception_entry` deferred to the coordinated audit-story PR (same pattern as phases 3.1 / 3.2).

Spec: `docs/superpowers/specs/2026-06-19-ubuntu-stig-autoinstall-phase-3-3-time-servers-design.md`

## Test plan

- [x] 14 new unit tests in `tests/rules/test_ubuntu2404_time_servers.py` cover chrony.conf path, server lines, no-DoD assertion, driftfile/makestep/mode/install-dir shape, and protocol contract (applies / deferred tailoring + exception / emit_packages / depends_on / meta wiring).
- [x] 1 new writer integration test asserts chrony lands in `autoinstall.packages` end-to-end.
- [x] `tests/golden/__snapshots__/test_ubuntu_minimal.ambr` regenerated — diff is +`autoinstall.packages: [chrony]` block and +`# rule:time_servers` band in late-commands; Applied-rules header bumps 4 → 5.
- [x] Full CI chain run locally: `ruff check && ruff format --check && mypy && pytest -q` — all four green.
- [x] Each commit on this branch is GPG-signed with `BE707B220C995478`.
EOF
)"
```

- [ ] **Step 8: Wait for required status checks to pass**

Run: `gh pr checks <pr-number>`
Expected: 5/5 status checks pass (ruff, analyze (python), test 3.11/3.12/3.13, CodeQL).

If a check fails: read the failure, fix on the branch, push again.

(Merging happens after final code review per the subagent-driven workflow — see superpowers:finishing-a-development-branch for the squash-merge step.)
