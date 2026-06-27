# Phase 3.12 + #88 bundled port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port two rules to ubuntu2404 in one PR: `data_disks_preserve` (phase 3.12) and `container_host` minimal (#88). data_disks_preserve is a direct alma9 port minus `restorecon`; container_host minimal mirrors alma9 with SELinux-specific operations stripped (semanage, restorecon) and a trimmed package list. The custom AppArmor profile work is deferred to a follow-up PR after install-regression validation.

**Architecture:** Two rule modules + two test files + one new helper script asset (`create-rootless-user-ubuntu.sh`). Neither rule affects the ubuntu_minimal golden snapshot (both `applies` return False on default cfg).

**Tech Stack:** Python 3.11+, pydantic v2, jinja2, syrupy snapshots, pytest, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-06-20-ubuntu-stig-autoinstall-phase-3-12-and-issue-88-bundled-design.md`

**Branch:** `phase-3.12-data-disks-and-container-host` (already created off main at `d620678`; spec already committed at `b5c2d86`).

---

## Reference patterns

- **alma9 siblings (semantic source):**
  - `src/ks_gen/rules/alma9/data_disks_preserve.py` — fstab + mount logic.
  - `src/ks_gen/rules/alma9/container_host.py` — script drop + storage.conf + per-user provisioning.
  - `src/ks_gen/assets/create-rootless-user.sh` — alma9 helper script (291 lines).
- **alma9 test siblings:**
  - `tests/rules/test_data_disks_preserve.py` — 14 tests.
  - `tests/rules/test_container_host.py` — 14 tests.

The ubuntu ports use the same test shapes; tests instantiate config via the existing `ubuntu_cfg_factory` fixture from `tests/conftest.py` and override `disk` / `containers` per-test as needed.

---

## Task 1: data_disks_preserve port + tests

Direct port. Only meaningful difference vs. alma9: drop `restorecon -R {mounts}`.

**Files:**
- Create: `src/ks_gen/rules/ubuntu2404/data_disks_preserve.py`
- Create: `tests/rules/test_ubuntu2404_data_disks_preserve.py`

- [ ] **Step 1: Create the rule module**

Direct port of `src/ks_gen/rules/alma9/data_disks_preserve.py` with the `restorecon -R {mounts}` line dropped from `emit_post`. Docstring notes the Ubuntu-specific change.

- [ ] **Step 2: Create the test file**

Mirror of `tests/rules/test_data_disks_preserve.py` with these adjustments:
- Use `ubuntu_cfg_factory` fixture (factory pattern, ubuntu2404 distro).
- Replace per-test `model_copy` to use the factory cfg.
- Add `test_emit_post_drops_restorecon` — assert `"restorecon"` NOT in body (key Ubuntu port assertion).
- Drop the alma9 `test_rule_emit_post_handles_multiple_preserved_disks` assertion `"restorecon -R /data /archive"` since we don't emit it; replace with assertion that the body ends after `mount -a` (no trailing restorecon line).

- [ ] **Step 3: Run the tests**

Run: `pytest tests/rules/test_ubuntu2404_data_disks_preserve.py -v`
Expected: 12 tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/ks_gen/rules/ubuntu2404/data_disks_preserve.py tests/rules/test_ubuntu2404_data_disks_preserve.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(rules/ubuntu2404): add data_disks_preserve port (#81 phase 3.12)

Direct port of alma9 rule. Only difference: drop the trailing
\`restorecon -R {mounts}\` line from emit_post — SELinux file
labels have no Ubuntu analog. /etc/fstab syntax, mkdir -p, and
mount -a are universal.

applies when any data_disk has wipe=False. Same _fstab_spec
helper for partition / partition_uuid / partition_label
resolution. emit_packages, emit_tailoring, exception_entry
match alma9 (all empty/None).

12 tests pin: applies on/off, three _fstab_spec branches,
defaults fsoptions, only-preserved disks rendered, multiple
disks handled, drops restorecon (Ubuntu port assertion),
protocol contract."
```

---

## Task 2: container_host helper script port

Port `create-rootless-user.sh` to Ubuntu, stripping SELinux-specific operations.

**Files:**
- Create: `src/ks_gen/assets/create-rootless-user-ubuntu.sh`

- [ ] **Step 1: Create the Ubuntu helper script**

Port of `src/ks_gen/assets/create-rootless-user.sh` (291 lines) with these specific edits per the spec table:

| alma9 line | Action |
|---|---|
| 18 | Change `Target: AlmaLinux 9 / Podman` to `Target: Ubuntu 24.04 LTS / Podman` |
| 87-88 | Drop `command -v semanage` preflight |
| 104-107 | Drop the SELinux fcontext equivalence block (4 lines) |
| 142 | Drop `restorecon -R "${CONTAINERS_ROOT}/${user}"` |
| 163 | Drop `restorecon -R "$home/.ssh"` |
| 178-181 | Drop the semanage fcontext block in the `-q` Quadlet section |
| 184 | Drop `restorecon -RF "$appdata"` |
| 202, 222, 259 | Drop the `restorecon "..." 2>/dev/null \|\| true` lines after each Quadlet file write |

All other logic (useradd, usermod --add-subuids/--add-subgids, install -d storage dir, loginctl enable-linger, SSH key install, Quadlet scaffold, podman info verification) is preserved verbatim.

- [ ] **Step 2: Smoke-test the script syntactically**

Run: `bash -n src/ks_gen/assets/create-rootless-user-ubuntu.sh`
Expected: no syntax errors.

- [ ] **Step 3: Commit**

```bash
git add src/ks_gen/assets/create-rootless-user-ubuntu.sh
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(assets): add Ubuntu rootless-container helper script (#88)

Port of create-rootless-user.sh stripping SELinux-specific ops:
  - drop \`command -v semanage\` preflight
  - drop semanage fcontext equivalence block (CONTAINERS_ROOT -> /var/lib/containers)
  - drop 5x \`restorecon\` calls (per-user store, .ssh, Quadlet appdata + units)
  - drop semanage fcontext rule for per-user appdata in -q scaffold
  - retarget docstring to Ubuntu 24.04 LTS

All other logic (useradd, subuid/subgid allocation, storage dir
install, loginctl linger, SSH key install, Quadlet network/volume/
container scaffold, podman info verification) preserved verbatim."
```

---

## Task 3: container_host rule + tests

**Files:**
- Create: `src/ks_gen/rules/ubuntu2404/container_host.py`
- Create: `tests/rules/test_ubuntu2404_container_host.py`

- [ ] **Step 1: Create the rule module**

Mirror of `src/ks_gen/rules/alma9/container_host.py` with these specific changes:
- Load `create-rootless-user-ubuntu.sh` instead of `create-rootless-user.sh`.
- Drop the `restorecon -R /home/{user}/.ssh` line in the per-user loop.
- Package list: `["podman", "crun", "slirp4netns", "fuse-overlayfs"]` (drops `containers-common`, `podman-plugins`, `policycoreutils-python-utils`).
- Docstring notes the minimal-port scope (AppArmor extension deferred).

- [ ] **Step 2: Create the test file**

Mirror of `tests/rules/test_container_host.py` with these adjustments:
- Use `ubuntu_cfg_factory` fixture.
- Update `test_emit_packages_returns_podman_stack` → `test_emit_packages_returns_ubuntu_podman_stack`: assert the 4 packages present AND assert the alma9-only 3 packages NOT present.
- Add `test_emit_post_drops_restorecon_calls` — `"restorecon"` NOT in body.
- Add `test_helper_script_drops_semanage_calls` — `"semanage"` NOT in body.
- Add `test_helper_script_drops_restorecon_calls` — same assertion (catches Quadlet branch when -q is added post-install).
- Add `test_helper_script_targets_ubuntu` — `"Ubuntu"` in body (catches docstring retarget).
- Keep existing tests: applies on/off, metadata, tailoring/exception empty, emit_post script drop + storage.conf, empty users, per-user provisioning, multi-key, no Quadlet scaffold at kickstart-time.

- [ ] **Step 3: Run the tests**

Run: `pytest tests/rules/test_ubuntu2404_container_host.py -v`
Expected: 15 tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/ks_gen/rules/ubuntu2404/container_host.py tests/rules/test_ubuntu2404_container_host.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(rules/ubuntu2404): add container_host minimal port (#88)

Port of alma9 rule with SELinux-specific operations stripped:
  - load create-rootless-user-ubuntu.sh (Ubuntu helper)
  - drop \`restorecon -R /home/<user>/.ssh\` from per-user loop
  - package list: podman, crun, slirp4netns, fuse-overlayfs
    (drops containers-common, podman-plugins, and
    policycoreutils-python-utils — Ubuntu's podman pulls
    equivalents transitively; semanage isn't applicable)

Same /srv/containers/\$USER/storage shape, same storage.conf,
same per-user provisioning + authorized_keys flow.

Custom AppArmor profile for podman + /srv/containers is a queued
follow-up PR after install-regression validation. Without it,
podman's stock containers-default profile applies — operators
can use \`--security-opt apparmor=unconfined\` per-container as
workaround.

15 tests pin: metadata, applies on/off, packages (4 present, 3
alma-only absent), tailoring/exception empty, script drop +
storage.conf, empty users, multi-user provisioning, multi-key,
no -q at kickstart, drops restorecon, helper script drops
semanage + restorecon, helper script targets Ubuntu."
```

---

## Task 4: CI parity + push + PR

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
Expected: ~917 tests pass (890 from end of v0.23.0 + 27 new tests across
data_disks_preserve (12) + container_host (15)). Exact baseline may differ;
what matters is "+27 tests, all green, no existing tests regress."

- [ ] **Step 5: Verify signed-clean**

Run: `git log --show-signature -10 --oneline`
Expected: every commit on this branch since `b5c2d86` (spec) is
signed with key `BE707B220C995478`.

- [ ] **Step 6: Push**

Run: `git push -u origin phase-3.12-data-disks-and-container-host`

- [ ] **Step 7: Open the PR**

Title: `feat(rules/ubuntu2404): data_disks_preserve + container_host minimal ports (#81 phase 3.12, #88)`

Body: Per-rule summary, test plan, AppArmor follow-up callout, references to spec + plan docs.

- [ ] **Step 8: Wait for GitHub CI; squash-merge when green**
