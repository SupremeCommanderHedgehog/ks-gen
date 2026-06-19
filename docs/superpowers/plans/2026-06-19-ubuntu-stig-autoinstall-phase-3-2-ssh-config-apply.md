# Ubuntu STIG Autoinstall Phase 3.2 — `ssh_config_apply` Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port `ssh_config_apply` to `ubuntu2404` — drop sshd config knobs (Port, PermitRootLogin, PasswordAuthentication, ClientAliveInterval/Max, MaxAuthTries, UsePAM) into `/etc/ssh/sshd_config.d/00-ks-gen.conf` plus a conditional `Banner /etc/ssh/sshd-banner` line that completes phase 3.1's banner_text wiring; deferring tailoring + exception per the phase 3.0/3.1 lock pattern.

**Architecture:** New rule module at `src/ks_gen/rules/ubuntu2404/ssh_config_apply.py`, auto-discovered by `registry.load_rules("ubuntu2404")` (no `__init__.py` changes). Reuses `src/ks_gen/rules/_meta/ssh_config_apply.py` unchanged (depends on `admin_user_and_keys` and `ssh_keep_open`, so topo_sort places this rule LAST among ubuntu rules). Bash structure identical to alma9 modulo the conditional Banner line. `emit_tailoring` / `emit_packages` / `exception_entry` return `[]` / `[]` / `None`.

**Tech Stack:** Python 3.11+, pydantic 2, syrupy snapshots. No new dependencies.

**Branch:** Plan assumes `feat/phase-3-2-ssh-config-apply` is checked out from `main` at commit `e2abc56` (post-spec-commit).

**Acceptance bar:**
- New rule + new unit test file pass.
- `tests/golden/__snapshots__/test_ubuntu_minimal.ambr` regen shows: one new late-command entry appended to the END of `late-commands` (ssh_config_apply body), plus the exceptions.md Applied-rules count bump `3 → 4` and new bullet. No other deltas.
- alma9 goldens byte-identical.
- Local CI parity chain green: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`.

---

## File Structure

**Create (2 files):**

- `src/ks_gen/rules/ubuntu2404/ssh_config_apply.py` — the new rule module. Single `_emit` function building the bash body, a `_Rule` dataclass exporting module-level `RULE: Rule`. Mirrors `src/ks_gen/rules/alma9/ssh_config_apply.py` with two divergences: (1) conditional `Banner /etc/ssh/sshd-banner` line in the heredoc when `"motd" in cfg.banner.apply_to`, (2) `emit_tailoring` / `emit_packages` / `exception_entry` return empty / empty / `None` (deferred).
- `tests/rules/test_ubuntu2404_ssh_config_apply.py` — unit tests mirroring `tests/rules/test_ssh_config_apply.py` plus four ubuntu-specific tests (Banner emitted when motd in apply_to; Banner omitted when motd not in apply_to; three deferral contracts; meta-sharing).

**Modify (1 file):**

- `tests/golden/__snapshots__/test_ubuntu_minimal.ambr` — syrupy-regenerated. Expected diff: one new YAML literal-block entry under `late-commands:` (alphabetically/topologically LAST — after the ssh_keep_open `ufw allow 22/tcp` entry), plus a new bullet in the `exceptions.md` Applied-rules list and the count bump.

**Out of scope (no edits):**

- `src/ks_gen/rules/_meta/ssh_config_apply.py` — already distro-agnostic, reuse as-is.
- `src/ks_gen/rules/ubuntu2404/__init__.py` — registry uses `pkgutil.iter_modules`; new module is auto-discovered.
- `src/ks_gen/skeleton.py` / `src/ks_gen/templates/user-data.j2` — late-command plumbing already handles multi-line bash bodies.
- `src/ks_gen/writer.py` — `_build_ubuntu2404_bundle` already collects non-empty `emit_post` bodies into `PostBlock`s.
- `src/ks_gen/config.py` — `cfg.ssh` already exposes all seven directives; `cfg.banner.apply_to` already includes `motd` in defaults.

---

### Task 1: Write the failing unit-test file

**Files:**
- Create: `tests/rules/test_ubuntu2404_ssh_config_apply.py`

**Goal:** Lock the rule's contract — drop-in path + mode, all seven sshd directives, `sshd -t` validation, no service restart, conditional Banner gating, deferral contracts — before any rule code exists.

- [ ] **Step 1: Create the test file**

Create `tests/rules/test_ubuntu2404_ssh_config_apply.py` with this EXACT content (top-of-file RULE import matches the sibling convention established in phase 3.1):

```python
from ks_gen.rules.ubuntu2404.ssh_config_apply import RULE


def test_depends_on_admin_and_keep_open(ubuntu_cfg_factory):
    assert "admin_user_and_keys" in RULE.depends_on
    assert "ssh_keep_open" in RULE.depends_on


def test_post_writes_drop_in_config(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/ssh/sshd_config.d/00-ks-gen.conf" in out
    assert "Port 22" in out
    assert "PermitRootLogin no" in out
    assert "PasswordAuthentication no" in out
    assert "ClientAliveInterval 600" in out
    assert "ClientAliveCountMax 1" in out
    assert "MaxAuthTries 4" in out
    assert "UsePAM yes" in out


def test_post_validates_with_sshd_t(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "sshd -t" in out


def test_post_does_not_restart_sshd_during_install(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "systemctl restart sshd" not in out
    assert "systemctl reload sshd" not in out
    assert "systemctl restart ssh" not in out
    assert "systemctl reload ssh" not in out


def test_post_drop_in_is_mode_600(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "chmod 600 /etc/ssh/sshd_config.d/00-ks-gen.conf" in out


def test_post_emits_banner_directive_when_motd_in_apply_to(ubuntu_cfg_factory):
    # Default ubuntu cfg.banner.apply_to includes "motd"; phase 3.1's
    # banner_text rule maps motd -> /etc/ssh/sshd-banner. ssh_config_apply
    # must point sshd's Banner directive at that file so the banner
    # actually surfaces on SSH login.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "Banner /etc/ssh/sshd-banner" in out


def test_post_omits_banner_directive_when_motd_excluded(ubuntu_cfg_factory):
    # If the operator drops "motd" from apply_to, banner_text won't write
    # /etc/ssh/sshd-banner — so we must not point sshd at a missing file.
    from ks_gen.config import Banner

    base = ubuntu_cfg_factory()
    cfg = base.model_copy(
        update={
            "banner": Banner(
                text=base.banner.text,
                apply_to=["issue", "issue_net", "gdm"],
            )
        }
    )
    out = RULE.emit_post(cfg)
    assert "Banner /etc/ssh/sshd-banner" not in out


def test_post_uses_configured_port(ubuntu_cfg_factory):
    from ks_gen.config import Ssh

    base = ubuntu_cfg_factory()
    cfg = base.model_copy(update={"ssh": Ssh(port=2222)})
    out = RULE.emit_post(cfg)
    assert "Port 2222" in out
    assert "Port 22\n" not in out


def test_applies_always_true(ubuntu_cfg_factory):
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_emit_tailoring_returns_empty_deferred(ubuntu_cfg_factory):
    # Deferred until ssg-ubuntu2404-ds.xml survey lands.
    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []


def test_exception_entry_returns_none_deferred(ubuntu_cfg_factory):
    # Deferred until ssg-ubuntu2404-ds.xml survey lands.
    assert RULE.exception_entry(ubuntu_cfg_factory()) is None


def test_emit_packages_is_empty(ubuntu_cfg_factory):
    # openssh-server is installed by default on Ubuntu Server; no apt deps.
    assert RULE.emit_packages(ubuntu_cfg_factory()) == []


def test_id_and_summary_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules._meta import ssh_config_apply as meta

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/rules/test_ubuntu2404_ssh_config_apply.py -v`
Expected: collection error or per-test failure — every test fails because `ks_gen.rules.ubuntu2404.ssh_config_apply` doesn't exist yet.

- [ ] **Step 3: Confirm the failure mode is the right kind**

Look at the pytest output. The failure should reference `ModuleNotFoundError: No module named 'ks_gen.rules.ubuntu2404.ssh_config_apply'`. NOT a syntax error in the test file, NOT a fixture missing error, NOT an import error inside `ks_gen`. If you see any of those, STOP and report BLOCKED.

- [ ] **Step 4: Commit the failing tests (SIGNED, NEVER amend)**

```powershell
git add tests/rules/test_ubuntu2404_ssh_config_apply.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): failing tests for ssh_config_apply port (#81 phase 3.2)"
```

- [ ] **Step 5: Verify the commit is signed**

Run: `git log -1 --show-signature`
Expected: line containing `Good signature from "Patrick Connallon (SupremeCommanderHedgehog) <github.v5f9w@bitbucket.onl>"`. If gpg reports any other status, STOP and report BLOCKED.

---

### Task 2: Implement the rule module

**Files:**
- Create: `src/ks_gen/rules/ubuntu2404/ssh_config_apply.py`

**Goal:** Make Task 1's tests pass. Bash output identical to alma9 modulo one new conditional line (`Banner /etc/ssh/sshd-banner`) gated on `"motd" in cfg.banner.apply_to`.

- [ ] **Step 1: Create the rule module**

Create `src/ks_gen/rules/ubuntu2404/ssh_config_apply.py` with this EXACT content:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import ssh_config_apply as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


def _emit(cfg: HostConfig) -> str:
    s = cfg.ssh
    pwd = "yes" if s.password_authentication else "no"
    pam = "yes" if s.use_pam else "no"
    # phase 3.1's banner_text writes /etc/ssh/sshd-banner only when "motd"
    # is in apply_to. Gate the Banner directive on the same condition so
    # sshd never points at a missing file.
    banner_line = (
        "Banner /etc/ssh/sshd-banner\n" if "motd" in cfg.banner.apply_to else ""
    )
    return f"""\
# Drop-in SSH server config (active on first boot)
install -d -m 755 /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/00-ks-gen.conf <<'__KS_GEN_EOF__'
Port {s.port}
PermitRootLogin {s.permit_root_login}
PasswordAuthentication {pwd}
ClientAliveInterval {s.client_alive_interval}
ClientAliveCountMax {s.client_alive_count_max}
MaxAuthTries {s.max_auth_tries}
UsePAM {pam}
{banner_line}__KS_GEN_EOF__
chmod 600 /etc/ssh/sshd_config.d/00-ks-gen.conf
sshd -t
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
        # Deferred: ssg-ubuntu2404-ds.xml sshd-rule survey lands in the audit-story PR.
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        # Deferred: paired with emit_tailoring above; see audit-story PR.
        return None


RULE: Rule = cast(Rule, _Rule())
```

- [ ] **Step 2: Run the targeted unit tests**

Run: `pytest tests/rules/test_ubuntu2404_ssh_config_apply.py -v`
Expected: all 13 tests PASS.

- [ ] **Step 3: Sanity-check that the golden snapshot is the ONLY downstream regression**

Run: `pytest -q --no-header 2>&1 | tail -20`
Expected: exactly ONE failure — `tests/golden/test_ubuntu_minimal.py::test_ubuntu_minimal` snapshot mismatch. Anything else failing is a real regression you introduced — STOP and report BLOCKED.

- [ ] **Step 4: Commit (SIGNED, NEVER amend)**

```powershell
git add src/ks_gen/rules/ubuntu2404/ssh_config_apply.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(rules/ubuntu2404): ssh_config_apply port (#81 phase 3.2)"
```

- [ ] **Step 5: Verify the commit is signed**

Run: `git log -1 --show-signature`
Expected: `Good signature from "Patrick Connallon (SupremeCommanderHedgehog) <github.v5f9w@bitbucket.onl>"`.

---

### Task 3: Regenerate the ubuntu_minimal golden snapshot

**Files:**
- Modify: `tests/golden/__snapshots__/test_ubuntu_minimal.ambr`

**Goal:** Pick up the new ssh_config_apply late-command + the exceptions.md Applied-rules row. Verify the diff is exactly those two things.

- [ ] **Step 1: Run the snapshot test to see the predicted diff**

Run: `pytest tests/golden/test_ubuntu_minimal.py -q`
Expected: FAIL. The diff should show:
1. user-data snapshot: a new YAML literal-block late-command entry at the END of `late-commands` (after the `ssh_keep_open` `ufw allow 22/tcp` entry) containing the sshd config heredoc with `Banner /etc/ssh/sshd-banner` present (because the minimal yaml's default `apply_to` includes `motd`).
2. exceptions.md snapshot: Applied rules count `3 → 4`, new bullet `- ssh_config_apply — Write sshd drop-in config for Port/PermitRootLogin/PasswordAuthentication.` inserted in alphabetical position.

No changes to `tailoring.xml`, `meta-data`, or `host.yaml`.

- [ ] **Step 2: Regenerate the snapshot**

Run: `pytest tests/golden/test_ubuntu_minimal.py --snapshot-update -q`
Expected: PASS, "2 snapshots updated" (one for user-data, one for exceptions.md).

- [ ] **Step 3: Inspect the diff (CRITICAL VERIFICATION)**

Run: `git diff tests/golden/__snapshots__/test_ubuntu_minimal.ambr`
Expected diff body must contain:
- A new late-command block beginning `curtin in-target --target=/target -- bash -c '# rule:ssh_config_apply` positioned AFTER the existing `ssh_keep_open` block (the file is a top-down concat — last entry is last).
- That block must contain literal text `Banner /etc/ssh/sshd-banner` (because minimal cfg's apply_to includes motd).
- Exceptions.md count `2 → 3` is wrong (would mean banner_text didn't land); count must read `3 → 4`.
- Exceptions.md new bullet line must read exactly `  - \`ssh_config_apply\` — Write sshd drop-in config for Port/PermitRootLogin/PasswordAuthentication.` (or close to it modulo whitespace — verify with the rendered snapshot, not by hand).

If ANY other section (tailoring.xml, meta-data, host.yaml) diffs, STOP and report BLOCKED.

- [ ] **Step 4: Commit (SIGNED, NEVER amend)**

```powershell
git add tests/golden/__snapshots__/test_ubuntu_minimal.ambr
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(golden): regen ubuntu_minimal snapshot for ssh_config_apply (#81 phase 3.2)"
```

- [ ] **Step 5: Run the full suite to confirm zero regressions**

Run: `pytest -q`
Expected: ALL green. If `tests/test_writer.py::test_build_bundle_ubuntu2404_late_commands_includes_ufw_entry` fails with a count assertion (e.g., `len(late) == 2`), STOP — phase 3.1 already de-brittled it to a semantic filter (filtering by `# rule:ssh_keep_open`), so a count failure here would indicate that fix was reverted, which warrants investigation.

---

### Task 4: Commit the plan doc, CI parity chain, push, open PR

**Files:** plan doc commit (untracked), no other edits

**Goal:** Land the plan doc, verify CI parity locally, push, open PR.

- [ ] **Step 1: Commit the plan doc**

The plan at `docs/superpowers/plans/2026-06-19-ubuntu-stig-autoinstall-phase-3-2-ssh-config-apply.md` is untracked. Stage and commit it:

```powershell
git add docs/superpowers/plans/2026-06-19-ubuntu-stig-autoinstall-phase-3-2-ssh-config-apply.md
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "docs(plans): phase 3.2 ssh_config_apply implementation plan (#81)"
```

- [ ] **Step 2: Run the full CI parity chain**

Run: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
Expected: all four green. If `ruff format --check` flags drift, run `ruff format src tests`, re-verify with `--check`, then stage and create a NEW signed commit with subject `style: ruff format` (per user's global "never amend" rule).

- [ ] **Step 3: Push the branch**

```powershell
git push -u origin feat/phase-3-2-ssh-config-apply
```
Expected: branch created on remote, tracking set.

- [ ] **Step 4: Open the PR**

```powershell
gh pr create --title "feat(rules/ubuntu2404): ssh_config_apply port (#81 phase 3.2)" --body @'
## Summary

- Ports the `ssh_config_apply` rule to `ubuntu2404`. Drops the same seven sshd directives `ks-gen` controls (`Port`, `PermitRootLogin`, `PasswordAuthentication`, `ClientAliveInterval`, `ClientAliveCountMax`, `MaxAuthTries`, `UsePAM`) into `/etc/ssh/sshd_config.d/00-ks-gen.conf` (mode 600) and runs `sshd -t` to validate before subiquity reboots.
- Adds a conditional `Banner /etc/ssh/sshd-banner` line — emitted only when `"motd" in cfg.banner.apply_to` — to complete the banner_text → sshd wiring left open by phase 3.1's spec.
- Tailoring + exception entry + emit_packages return empty / `None` / empty — deferred to the upcoming "ubuntu audit story" PR (same lock pattern as 3.0/3.1).

## Test plan

- [x] 13 new unit tests in `tests/rules/test_ubuntu2404_ssh_config_apply.py` cover drop-in path + mode, all seven sshd directives, configured non-default port, `sshd -t` validation, no service restart, Banner gating both states, meta-sharing, deferral contracts (×3), and `applies==True`
- [x] `test_ubuntu_minimal` snapshot regen — diff is the new ssh_config_apply late-command (positioned last via topo, after ssh_keep_open) plus the Applied-rules count bump in `exceptions.md`. No `tailoring.xml`, `meta-data`, or `host.yaml` changes.
- [x] alma9 goldens byte-identical
- [x] Local CI parity: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`

Refs #81 phase 3.2.

Spec: `docs/superpowers/specs/2026-06-19-ubuntu-stig-autoinstall-phase-3-2-ssh-config-apply-design.md`
Plan: `docs/superpowers/plans/2026-06-19-ubuntu-stig-autoinstall-phase-3-2-ssh-config-apply.md`
'@
```

Expected: PR URL printed.

- [ ] **Step 5: Report the PR URL back to the controller**
