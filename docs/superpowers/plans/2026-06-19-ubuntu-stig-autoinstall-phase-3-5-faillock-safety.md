# Phase 3.5 — `faillock_safety` port to ubuntu2404 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the `faillock_safety` rule to ubuntu2404 so the generated autoinstall both writes `/etc/security/faillock.conf` AND wires `pam_faillock` into the PAM stack via Ubuntu's `pam-auth-update` profile mechanism.

**Architecture:** One new rule module + one new test file. `emit_post` composes three blocks: faillock.conf sed-replace (same defensive pattern as alma9), pam-auth-update profile at `/usr/share/pam-configs/ks-gen-faillock`, and a `DEBIAN_FRONTEND=noninteractive pam-auth-update --enable ks-gen-faillock --package` call. emit_post-only + defer-tailoring/exception pattern matches phases 3.1–3.4.

**Tech Stack:** Python 3.11+, pydantic v2, jinja2, syrupy snapshots, pytest, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-06-19-ubuntu-stig-autoinstall-phase-3-5-faillock-safety-design.md`

**Branch:** `feat/phase-3-5-faillock-safety` (already created off main at `2ba0cc5`; spec already committed at `a6acc4f`).

---

## Reference patterns

- **alma9 sibling:** `src/ks_gen/rules/alma9/faillock_safety.py` — semantic source for the faillock.conf sed-replace pattern.
- **Closest ubuntu2404 sibling:** `src/ks_gen/rules/ubuntu2404/crypto_policy.py` (phase 3.4) — multi-block `_emit_X` decomposition + heredoc style.
- **Test sibling:** `tests/rules/test_ubuntu2404_crypto_policy.py` — module-level `from ... import RULE` at top, local `from ks_gen.config import ...` inside per-test override functions.

The `FaillockCfg` schema is in `src/ks_gen/config.py:553-557` (fields: `enable`, `deny=3`, `unlock_time=900`, `even_deny_root=False`). `Overrides` is in `src/ks_gen/config.py:650` with `faillock: FaillockCfg`. Override pattern in tests:

```python
from ks_gen.config import FaillockCfg, Overrides

cfg = ubuntu_cfg_factory().model_copy(
    update={"overrides": Overrides(faillock=FaillockCfg(enable=False))}
)
```

---

## Task 1: Rule skeleton + first failing test

Create the rule file with all three component emitters in one TDD shot. The `_emit_*` helpers are small enough that incrementally building them out wouldn't add review value. Add one failing path test to drive the wiring.

**Files:**
- Create: `src/ks_gen/rules/ubuntu2404/faillock_safety.py`
- Create: `tests/rules/test_ubuntu2404_faillock_safety.py`

- [ ] **Step 1: Write the failing test**

Create `tests/rules/test_ubuntu2404_faillock_safety.py`:

```python
from ks_gen.rules.ubuntu2404.faillock_safety import RULE


def test_post_writes_faillock_conf_path(ubuntu_cfg_factory):
    # Same /etc/security/faillock.conf path as alma9 — file ships in
    # libpam-modules (essential package) so this works in the chroot.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/security/faillock.conf" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/rules/test_ubuntu2404_faillock_safety.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ks_gen.rules.ubuntu2404.faillock_safety'`

- [ ] **Step 3: Create the rule module**

Create `src/ks_gen/rules/ubuntu2404/faillock_safety.py`:

```python
"""ubuntu2404 faillock soften-lockout rule.

Writes /etc/security/faillock.conf and wires pam_faillock into the
common-auth/common-account stack via pam-auth-update. Wiring is
required on Ubuntu because the libpam-modules package ships
pam_faillock.so but does not auto-enable it (unlike RHEL).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import faillock_safety as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


def _emit_faillock_conf(cfg: HostConfig) -> str:
    f = cfg.overrides.faillock
    even = "yes" if f.even_deny_root else "no"
    conf = "/etc/security/faillock.conf"
    return (
        "# faillock.conf — soften lockout for remote-safe operation\n"
        f"sed -i -E 's/^[# ]*unlock_time *=.*/unlock_time = {f.unlock_time}/' {conf}\n"
        f"grep -q '^unlock_time' {conf} || echo 'unlock_time = {f.unlock_time}' >> {conf}\n"
        f"sed -i -E 's/^[# ]*deny *=.*/deny = {f.deny}/' {conf}\n"
        f"grep -q '^deny' {conf} || echo 'deny = {f.deny}' >> {conf}\n"
        f"sed -i -E 's/^[# ]*even_deny_root.*/# even_deny_root removed by ks-gen: {even}/' {conf}\n"
    )


def _emit_pam_profile(cfg: HostConfig) -> str:
    return """\
# pam-auth-update profile (wires pam_faillock into common-auth/common-account)
install -d -m 755 /usr/share/pam-configs
cat > /usr/share/pam-configs/ks-gen-faillock <<'__KS_GEN_EOF__'
Name: pam_faillock (ks-gen)
Default: yes
Priority: 1024
Auth-Type: Primary
Auth-Initial:
        [default=die]                  pam_faillock.so authfail
Auth:
        [success=1 default=ignore]     pam_faillock.so preauth
Account-Type: Primary
Account:
        required                       pam_faillock.so
__KS_GEN_EOF__
chmod 644 /usr/share/pam-configs/ks-gen-faillock
"""


def _emit_pam_enable(cfg: HostConfig) -> str:
    return "DEBIAN_FRONTEND=noninteractive pam-auth-update --enable ks-gen-faillock --package\n"


def _emit(cfg: HostConfig) -> str:
    return "".join([_emit_faillock_conf(cfg), _emit_pam_profile(cfg), _emit_pam_enable(cfg)])


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return cfg.overrides.faillock.enable

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        # Deferred: ssg-ubuntu2404-ds.xml faillock rule survey lands in the audit-story PR.
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

No edit to `src/ks_gen/rules/ubuntu2404/__init__.py` — registry uses `pkgutil.iter_modules` auto-discovery.

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/rules/test_ubuntu2404_faillock_safety.py -v`
Expected: PASS — `test_post_writes_faillock_conf_path` is green.

- [ ] **Step 5: Commit**

```bash
git add tests/rules/test_ubuntu2404_faillock_safety.py src/ks_gen/rules/ubuntu2404/faillock_safety.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(rules/ubuntu2404): add faillock_safety rule skeleton (#81 phase 3.5)

Writes /etc/security/faillock.conf via the same defensive sed-replace
pattern as alma9, plus a pam-auth-update profile at
/usr/share/pam-configs/ks-gen-faillock and a DEBIAN_FRONTEND=noninteractive
pam-auth-update --enable --package call that wires pam_faillock into
common-auth/common-account. PAM wiring is required on Ubuntu because
libpam-modules ships pam_faillock.so but does NOT auto-enable it.
emit_tailoring + exception_entry deferred to audit-story PR.

First test pins the faillock.conf path."
```

NO `Co-Authored-By` trailer in the commit message.

---

## Task 2: `applies` semantics tests

Two tests for the `applies` short-circuit: default cfg → True, `enable=False` → False.

**Files:**
- Modify: `tests/rules/test_ubuntu2404_faillock_safety.py`

- [ ] **Step 1: Append two applies tests**

```python
def test_applies_when_enabled(ubuntu_cfg_factory):
    # Default cfg.overrides.faillock.enable is True.
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_applies_short_circuits_when_disabled(ubuntu_cfg_factory):
    # When the operator sets enable=False, the rule is excluded from
    # late-commands entirely (the registry's applies() filter drops it).
    from ks_gen.config import FaillockCfg, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(faillock=FaillockCfg(enable=False))}
    )
    assert RULE.applies(cfg) is False
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/rules/test_ubuntu2404_faillock_safety.py -v`
Expected: 3 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_faillock_safety.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert faillock_safety applies honors enable flag"
```

---

## Task 3: faillock.conf shape tests

Six tests covering the on-disk shape of `/etc/security/faillock.conf`:
unlock_time, deny, even_deny_root comment-out with yes/no marker, and
cfg-override responsiveness for unlock_time + deny.

**Files:**
- Modify: `tests/rules/test_ubuntu2404_faillock_safety.py`

- [ ] **Step 1: Append six faillock.conf tests**

```python
def test_post_reasserts_unlock_time_from_cfg(ubuntu_cfg_factory):
    # Default unlock_time is 900 (FaillockCfg in src/ks_gen/config.py).
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "unlock_time = 900" in out


def test_post_reasserts_deny_from_cfg(ubuntu_cfg_factory):
    # Default deny is 3.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "deny = 3" in out


def test_post_comments_out_even_deny_root_with_no_marker(ubuntu_cfg_factory):
    # Default even_deny_root=False -> the line is commented out with a
    # trailing "no" marker so an auditor reads the cfg intent.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "# even_deny_root removed by ks-gen: no" in out


def test_post_comments_out_even_deny_root_with_yes_marker(ubuntu_cfg_factory):
    # When operator opts into even_deny_root=True, the directive is STILL
    # commented out (we never assert it positively), but the marker
    # reflects the cfg.
    from ks_gen.config import FaillockCfg, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(faillock=FaillockCfg(even_deny_root=True))}
    )
    out = RULE.emit_post(cfg)
    assert "# even_deny_root removed by ks-gen: yes" in out


def test_post_reflects_unlock_time_override(ubuntu_cfg_factory):
    from ks_gen.config import FaillockCfg, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(faillock=FaillockCfg(unlock_time=300))}
    )
    out = RULE.emit_post(cfg)
    assert "unlock_time = 300" in out
    assert "unlock_time = 900" not in out


def test_post_reflects_deny_override(ubuntu_cfg_factory):
    from ks_gen.config import FaillockCfg, Overrides

    cfg = ubuntu_cfg_factory().model_copy(
        update={"overrides": Overrides(faillock=FaillockCfg(deny=5))}
    )
    out = RULE.emit_post(cfg)
    assert "deny = 5" in out
    assert "deny = 3" not in out
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/rules/test_ubuntu2404_faillock_safety.py -v`
Expected: 9 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_faillock_safety.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert faillock_safety faillock.conf shape"
```

---

## Task 4: pam-auth-update profile tests

Three tests for the `/usr/share/pam-configs/ks-gen-faillock` profile file: path, PAM directive lines for preauth + authfail, Account block requiring pam_faillock.

**Files:**
- Modify: `tests/rules/test_ubuntu2404_faillock_safety.py`

- [ ] **Step 1: Append three profile tests**

```python
def test_post_writes_pam_configs_profile_at_ks_gen_faillock(ubuntu_cfg_factory):
    # The "ks-gen-" prefix is unique so the profile name doesn't collide
    # with any future Debian-shipped pam-faillock profile.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/usr/share/pam-configs/ks-gen-faillock" in out


def test_post_profile_contains_preauth_and_authfail_lines(ubuntu_cfg_factory):
    # preauth runs before pam_unix (counts failures), authfail runs
    # after a failure to record it. Both required for pam_faillock to
    # be functional.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "pam_faillock.so preauth" in out
    assert "pam_faillock.so authfail" in out


def test_post_profile_contains_account_required_line(ubuntu_cfg_factory):
    # Account: required pam_faillock.so — runs on every account check
    # and zeroes the counter on success. Without this, the counter
    # would only grow.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "Account-Type: Primary" in out
    assert "required" in out
    assert "pam_faillock.so" in out
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/rules/test_ubuntu2404_faillock_safety.py -v`
Expected: 12 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_faillock_safety.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert faillock_safety pam-auth-update profile"
```

---

## Task 5: pam-auth-update enable tests

Two tests for the activation command: the `pam-auth-update --enable
ks-gen-faillock --package` invocation and the `DEBIAN_FRONTEND=noninteractive`
prefix.

**Files:**
- Modify: `tests/rules/test_ubuntu2404_faillock_safety.py`

- [ ] **Step 1: Append two enable tests**

```python
def test_post_enables_profile_via_pam_auth_update(ubuntu_cfg_factory):
    # --enable activates the profile we just wrote.
    # --package tells pam-auth-update this is a package-managed,
    # non-interactive run -> survives libpam-runtime upgrades that
    # regenerate the common-* files.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "pam-auth-update --enable ks-gen-faillock --package" in out


def test_post_uses_debian_frontend_noninteractive(ubuntu_cfg_factory):
    # No TTY in late-commands, so any prompt would hang the install.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "DEBIAN_FRONTEND=noninteractive pam-auth-update" in out
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/rules/test_ubuntu2404_faillock_safety.py -v`
Expected: 14 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_faillock_safety.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert faillock_safety pam-auth-update enable"
```

---

## Task 6: Protocol contract tests

Five tests guarding the Rule Protocol contract.

**Files:**
- Modify: `tests/rules/test_ubuntu2404_faillock_safety.py`

- [ ] **Step 1: Append five protocol tests**

```python
def test_emit_packages_returns_empty(ubuntu_cfg_factory):
    # pam_faillock.so ships in libpam-modules, pam-auth-update in
    # libpam-runtime — both Essential: yes. No apt deps.
    assert RULE.emit_packages(ubuntu_cfg_factory()) == []


def test_emit_tailoring_returns_empty_deferred(ubuntu_cfg_factory):
    # Deferred until ssg-ubuntu2404-ds.xml faillock rule survey lands
    # in the audit-story PR.
    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []


def test_exception_entry_returns_none_deferred(ubuntu_cfg_factory):
    # Deferred until ssg-ubuntu2404-ds.xml faillock rule survey lands.
    assert RULE.exception_entry(ubuntu_cfg_factory()) is None


def test_depends_on_is_empty(ubuntu_cfg_factory):
    # Mirrors meta's empty DEPENDS_ON.
    assert RULE.depends_on == []


def test_id_and_summary_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules._meta import faillock_safety as meta

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY
```

- [ ] **Step 2: Run all tests in the file**

Run: `pytest tests/rules/test_ubuntu2404_faillock_safety.py -v`
Expected: 19 tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/rules/test_ubuntu2404_faillock_safety.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(rules/ubuntu2404): assert protocol contract for faillock_safety"
```

---

## Task 7: Regenerate the ubuntu_minimal golden snapshot

**Files:**
- Modify: `tests/golden/__snapshots__/test_ubuntu_minimal.ambr`

- [ ] **Step 1: Run the golden test to confirm it fails**

Run: `pytest tests/golden/ -v -k ubuntu_minimal`
Expected: FAIL — syrupy reports the snapshot diff for the new
faillock_safety band.

(Note: the snapshot may already be modified in the working tree if an
earlier `pytest -q` run via pre-commit hooks regen'd it during prior
tasks. In that case Step 1 still works — just verify the diff against
expectations in Step 3.)

- [ ] **Step 2: Regenerate the snapshot if not already updated**

If the snapshot test failed in Step 1:
Run: `pytest tests/golden/ --snapshot-update -k ubuntu_minimal`

If `git status` already shows the snapshot file as modified, skip the
update command — the existing changes are what we want to inspect.

- [ ] **Step 3: Inspect the diff**

Run: `git diff tests/golden/__snapshots__/test_ubuntu_minimal.ambr`

Expected diff (and ONLY these changes):

1. `- Applied rules: 6` → `+ Applied rules: 7` in the Summary section.
2. `+ - `faillock_safety` — Set faillock unlock_time and disable
   even_deny_root for remote safety.` inserted alphabetically into the
   Applied rules list (between `crypto_policy` and `ssh_config_apply`).
3. A new `# rule:faillock_safety ──────────...` band inside
   `late-commands` containing the three blocks: the faillock.conf
   sed-replace lines, the `/usr/share/pam-configs/ks-gen-faillock`
   heredoc, and the `DEBIAN_FRONTEND=noninteractive pam-auth-update
   --enable ks-gen-faillock --package` call.

If any alma9 snapshot diffs, STOP — investigate before proceeding. No
`autoinstall.packages:` changes expected.

**Merge-order assumption.** The 6 → 7 count assumes this branch sits
on main at `2ba0cc5` (post-v0.18.0, phases 3.0/3.1/3.2/3.3/3.4 merged
= 6 ubuntu rules). If unrelated work landed first that added another
rule, regenerate and confirm "+1 your rule, nothing else."

- [ ] **Step 4: Commit the snapshot**

```bash
git add tests/golden/__snapshots__/test_ubuntu_minimal.ambr
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(golden): regen ubuntu_minimal snapshot for faillock_safety rule"
```

---

## Task 8: CI parity + push + PR

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
Expected: ~819 tests pass (800 from end of phase 3.4 + 19 new faillock_safety tests).

- [ ] **Step 5: Verify signed-clean**

Run: `git log --show-signature -8 --oneline`
Expected: every commit since `a6acc4f` (spec) is signed with key `BE707B220C995478`.

- [ ] **Step 6: Push**

Run: `git push -u origin feat/phase-3-5-faillock-safety`
Expected: push succeeds; GitHub returns the PR URL.

If push fails with `GH007`, STOP and surface to user.

- [ ] **Step 7: Open the PR**

```bash
gh pr create --title "feat(rules/ubuntu2404): faillock_safety port (#81 phase 3.5)" --body "$(cat <<'EOF'
## Summary

- Ports the `faillock_safety` rule to ubuntu2404 (issue #81 phase 3.5).
- Writes `/etc/security/faillock.conf` via the same defensive sed-replace pattern as alma9 (path is identical; file ships in libpam-modules).
- **Wires `pam_faillock` into the PAM stack** via Ubuntu's pam-auth-update profile mechanism. This is the key divergence from alma9 — libpam-modules ships pam_faillock.so but does NOT auto-enable it, so writing faillock.conf alone would be a no-op on Ubuntu.
  - Profile written at `/usr/share/pam-configs/ks-gen-faillock` (unique name avoids future collision with any Debian-shipped pam-faillock profile).
  - Activated via `DEBIAN_FRONTEND=noninteractive pam-auth-update --enable ks-gen-faillock --package`. The `--package` flag makes the activation survive subsequent `libpam-runtime` upgrades that regenerate common-*.
- `emit_tailoring` + `exception_entry` deferred to the audit-story PR.

Spec: `docs/superpowers/specs/2026-06-19-ubuntu-stig-autoinstall-phase-3-5-faillock-safety-design.md`
Plan: `docs/superpowers/plans/2026-06-19-ubuntu-stig-autoinstall-phase-3-5-faillock-safety.md`

## Test plan

- [x] 19 new unit tests in `tests/rules/test_ubuntu2404_faillock_safety.py` cover the `applies` short-circuit, faillock.conf shape (unlock_time / deny / even_deny_root marker / cfg overrides), pam-auth-update profile (path / PAM directive lines / account block), the enable invocation (`--enable ks-gen-faillock --package` + `DEBIAN_FRONTEND=noninteractive`), and the Rule Protocol contract.
- [x] `tests/golden/__snapshots__/test_ubuntu_minimal.ambr` regenerated — diff adds the `# rule:faillock_safety` band (3 blocks) and bumps Applied-rules header 6 → 7. No `autoinstall.packages:` changes.
- [x] Full CI chain run locally: `ruff check && ruff format --check && mypy && pytest -q` — all four green.
- [x] Each commit on this branch is GPG-signed with `BE707B220C995478`.
EOF
)"
```

- [ ] **Step 8: Wait for GitHub CI**

Run: `gh pr checks <pr-number>`
Expected: 5/5 checks pass.

Or poll:
```bash
until gh pr checks <pr-number> --json bucket --jq 'all(.[]; .bucket != "pending")' | grep -q true; do sleep 30; done
gh pr checks <pr-number>
```

If any check fails, STOP and report.
