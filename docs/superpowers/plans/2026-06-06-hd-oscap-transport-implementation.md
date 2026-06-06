# `hd:LABEL=` oscap transport — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `hd:LABEL=` transport branch to the oscap `%post` tailoring fetch so `ks-gen iso` bundles run through oscap remediation at install time without an HTTP server. Closes the second of the two v0.1.x gaps before tagging v0.2.0.

**Architecture:** Split the existing single chrooted oscap `%post` block in `src/ks_gen/templates/ks.cfg.j2` into two adjacent blocks. The first runs `--nochroot` (installer environment — has both network and the install media at `/run/install/repo` accessible) and dispatches on the kickstart transport: `http(s)://*` keeps using `curl`, the new `hd:LABEL=*)` arm does `cp /run/install/repo/tailoring.xml ...`, both write into `/mnt/sysimage/root/tailoring.xml`. The second block stays chrooted, runs `oscap xccdf eval --remediate` against `/root/tailoring.xml` exactly as today. `iso.py` needs no change — it already places `tailoring.xml` at the ISO root.

**Tech Stack:** Jinja2 templates, Python 3.11+, `pytest` + `syrupy` for golden snapshot tests, `pykickstart` for ksvalidator, ruff + mypy --strict for CI.

**Companion spec:** `docs/superpowers/specs/2026-06-06-hd-oscap-transport-design.md` (commit `a42f829`)

**Repo conventions to honor:**
- Conventional Commits (`feat:`, `test:`, `docs:`, `style:`, etc.)
- Every commit signed with the user's GPG key `BE707B220C995478`. Use the explicit form: `git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "..."`.
- Before any `git push` (this plan does NOT push — that's the user's call), run the full local CI parity chain: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`. Per `CLAUDE.md`: `ruff check` alone misses formatting drift.
- Golden snapshots live at `tests/golden/__snapshots__/*.ambr`. Regenerate with `pytest tests/golden/ --snapshot-update`. **Inspect the diff before committing** — a regen should change exactly what the template change predicts and nothing else.
- Never invoke any `Start-ScheduledTask` for the "GitHub Backup" task. Don't push without explicit user instruction.

---

## File Structure

**Files modified:**
- `src/ks_gen/templates/ks.cfg.j2` — split oscap `%post` block at current lines 42-75 into two adjacent blocks (fetch + eval).
- `src/ks_gen/lint.py` — extend `_internal_checks` with three new invariants: fetch-block presence, hd:LABEL= arm presence, fetch-precedes-eval ordering.
- `tests/test_lint.py` — add two negative tests for the new invariants.
- `tests/golden/__snapshots__/test_minimal_dhcp.ambr` — regenerated.
- `tests/golden/__snapshots__/test_modern_crypto.ambr` — regenerated.
- `tests/golden/__snapshots__/test_stig_strict.ambr` — regenerated.
- `tests/golden/__snapshots__/test_bare_metal_usbguard.ambr` — regenerated.
- `tests/golden/__snapshots__/test_unattended_disabled.ambr` — regenerated.
- `MANUAL.md` — §5.4 `ks-gen iso` gets a paragraph on the `%post --nochroot` staging.
- `README.md` — add an entry to the v0.1 known-limitations section (now removed/updated since ISO delivery works).
- `CHANGELOG.md` — new entry under `[Unreleased]`.
- `MINIMAL-TEST.md` — new ISO-delivery section after the HTTP walkthrough.

**Files created:** none beyond the plan and (already-committed) spec.

**Files NOT modified:**
- `src/ks_gen/iso.py` — already maps `tailoring.xml` to the ISO root; the new `hd:LABEL=*)` arm reads from `/run/install/repo/tailoring.xml` exactly where Anaconda mounts that media.
- Rule files in `src/ks_gen/rules/` — change is template + lint only.

---

## Task 1: Baseline — confirm clean starting state and create feature branch

**Files:** none modified

- [ ] **Step 1: Run the full CI parity chain to establish a known-green baseline.**

Run from repo root (`C:\Users\yizshachuck\source\alma-linux-security`):

```powershell
ruff check src tests; if ($LASTEXITCODE -ne 0) { throw "ruff check" }
ruff format --check src tests; if ($LASTEXITCODE -ne 0) { throw "ruff format --check" }
mypy; if ($LASTEXITCODE -ne 0) { throw "mypy" }
pytest -q; if ($LASTEXITCODE -ne 0) { throw "pytest" }
```

Expected: all four commands exit 0. If any fail BEFORE we've changed anything, stop and report — we're starting from a broken tree.

- [ ] **Step 2: Confirm `git status` is clean (apart from `.claude/` if it's already untracked per `gitStatus`).**

```powershell
git status --short
```

Expected: empty output, or only `?? .claude/`.

- [ ] **Step 3: Confirm the spec commit `a42f829` is on `main` (already done in the brainstorming step).**

```powershell
git log --oneline -3 main
```

Expected: the top commit is `a42f829 docs(spec): hd:LABEL= oscap transport design`.

- [ ] **Step 4: Create and check out the feature branch.**

Repo convention (e.g., recent `impl/v0.2.0-unattended-updates`) is to do feature work on an `impl/...` branch and merge via PR. Branch the spec commit:

```powershell
git checkout -b impl/v0.2.0-hd-oscap-transport
git branch --show-current
```

Expected: `impl/v0.2.0-hd-oscap-transport`.

The remaining tasks all commit to this branch. The plan does NOT push or open a PR — that's the user's call after the implementation lands.

---

## Task 2: Update the kickstart template — split oscap `%post`

**Files:**
- Modify: `src/ks_gen/templates/ks.cfg.j2:42-75`

- [ ] **Step 1: Read the current oscap `%post` block to confirm the exact byte sequence we're replacing.**

```powershell
# Lines 42-75 of the template hold the single oscap %post block we're splitting.
Get-Content src\ks_gen\templates\ks.cfg.j2 | Select-Object -Skip 41 -First 34
```

Expected output (confirm before editing):

```
%post --erroronfail --log=/root/ks-post-oscap.log
set -euo pipefail

# Fetch tailoring.xml from the kickstart server, then run oscap remediation
# directly. This replaces the org_fedora_oscap addon, which required
# tailoring to be pre-registered as "supplied content" — a path that
# doesn't fit ks-gen's per-host tailoring model. Running oscap from %post
# puts us in full control of remediation timing and leaves tailoring.xml
# on the installed system for later audit.
ks_arg=$(awk -F'inst.ks=' 'NF>1{print $2}' /proc/cmdline | awk '{print $1}')
case "$ks_arg" in
  http://*|https://*)
    base="${ks_arg%/*}"
    curl -fsSL --retry 5 --retry-delay 3 "${base}/tailoring.xml" -o /root/tailoring.xml
    ;;
  *)
    echo "ks-gen: unsupported inst.ks transport '$ks_arg' (v0.1 supports http(s) only)" >&2
    exit 1
    ;;
esac

test -s /root/tailoring.xml
head -c 5 /root/tailoring.xml | grep -q '<?xml'

# --remediate can exit non-zero when rules remain failed (e.g., exception-
# disabled rules). The next %post block (ks-gen rule overrides) re-asserts
# critical state, so don't abort the install on a non-zero oscap exit.
oscap xccdf eval --remediate \
  --profile xccdf_org.ssgproject.content_profile_{{ cfg.meta.profile }} \
  --tailoring-file /root/tailoring.xml \
  --results-arf /root/oscap-remediation-results.xml \
  --report /root/oscap-remediation-report.html \
  /usr/share/xml/scap/ssg/content/{{ cfg.meta.scap_content }} || true
%end
```

- [ ] **Step 2: Replace lines 42-75 with the split fetch + eval blocks using `Edit`.**

`old_string` (the block above, exactly — Jinja `{{ }}` braces included):

```
%post --erroronfail --log=/root/ks-post-oscap.log
set -euo pipefail

# Fetch tailoring.xml from the kickstart server, then run oscap remediation
# directly. This replaces the org_fedora_oscap addon, which required
# tailoring to be pre-registered as "supplied content" — a path that
# doesn't fit ks-gen's per-host tailoring model. Running oscap from %post
# puts us in full control of remediation timing and leaves tailoring.xml
# on the installed system for later audit.
ks_arg=$(awk -F'inst.ks=' 'NF>1{print $2}' /proc/cmdline | awk '{print $1}')
case "$ks_arg" in
  http://*|https://*)
    base="${ks_arg%/*}"
    curl -fsSL --retry 5 --retry-delay 3 "${base}/tailoring.xml" -o /root/tailoring.xml
    ;;
  *)
    echo "ks-gen: unsupported inst.ks transport '$ks_arg' (v0.1 supports http(s) only)" >&2
    exit 1
    ;;
esac

test -s /root/tailoring.xml
head -c 5 /root/tailoring.xml | grep -q '<?xml'

# --remediate can exit non-zero when rules remain failed (e.g., exception-
# disabled rules). The next %post block (ks-gen rule overrides) re-asserts
# critical state, so don't abort the install on a non-zero oscap exit.
oscap xccdf eval --remediate \
  --profile xccdf_org.ssgproject.content_profile_{{ cfg.meta.profile }} \
  --tailoring-file /root/tailoring.xml \
  --results-arf /root/oscap-remediation-results.xml \
  --report /root/oscap-remediation-report.html \
  /usr/share/xml/scap/ssg/content/{{ cfg.meta.scap_content }} || true
%end
```

`new_string`:

```
%post --nochroot --erroronfail --log=/mnt/sysimage/root/ks-post-oscap-fetch.log
set -euo pipefail

# Stage tailoring.xml into the target rootfs. Runs in the installer
# environment so both network (http(s)) and the kickstart media at
# /run/install/repo (hd:LABEL=) are reachable. The chrooted oscap
# block that follows reads /root/tailoring.xml unconditionally.
ks_arg=$(awk -F'inst.ks=' 'NF>1{print $2}' /proc/cmdline | awk '{print $1}')
case "$ks_arg" in
  http://*|https://*)
    base="${ks_arg%/*}"
    curl -fsSL --retry 5 --retry-delay 3 \
      "${base}/tailoring.xml" -o /mnt/sysimage/root/tailoring.xml
    ;;
  hd:LABEL=*)
    cp /run/install/repo/tailoring.xml /mnt/sysimage/root/tailoring.xml
    ;;
  *)
    echo "ks-gen: unsupported inst.ks transport '$ks_arg' (supports http(s) and hd:LABEL=)" >&2
    exit 1
    ;;
esac
chmod 0600 /mnt/sysimage/root/tailoring.xml
%end

%post --erroronfail --log=/root/ks-post-oscap.log
set -euo pipefail

test -s /root/tailoring.xml
head -c 5 /root/tailoring.xml | grep -q '<?xml'

# --remediate can exit non-zero when rules remain failed (e.g., exception-
# disabled rules). The next %post block (ks-gen rule overrides) re-asserts
# critical state, so don't abort the install on a non-zero oscap exit.
oscap xccdf eval --remediate \
  --profile xccdf_org.ssgproject.content_profile_{{ cfg.meta.profile }} \
  --tailoring-file /root/tailoring.xml \
  --results-arf /root/oscap-remediation-results.xml \
  --report /root/oscap-remediation-report.html \
  /usr/share/xml/scap/ssg/content/{{ cfg.meta.scap_content }} || true
%end
```

- [ ] **Step 3: Render the template against the minimal-dhcp golden config to eyeball the rendered output.**

Run from repo root:

```powershell
.venv\Scripts\python.exe -m ks_gen gen `
  --config tests\golden\minimal-dhcp.host.yaml `
  --set disk.preset=minimal `
  --out build\plan-smoke
Get-Content build\plan-smoke\ks.cfg | Select-String -Pattern '%post' -Context 0,3
```

Expected: four `%post` headers in this order:

1. `%post --nochroot --erroronfail --log=/mnt/sysimage/root/ks-post-oscap-fetch.log`
2. `%post --erroronfail --log=/root/ks-post-oscap.log`
3. `%post --erroronfail --log=/root/ks-post.log` (existing overrides block — unchanged)
4. (no fourth `%post` — there's only three `%post` blocks total)

Confirm the fetch block contains the `hd:LABEL=*)` arm by spot-grep:

```powershell
Select-String -Path build\plan-smoke\ks.cfg -Pattern 'hd:LABEL='
```

Expected: at least two hits — the `case` arm `hd:LABEL=*)` and the error-message string `(supports http(s) and hd:LABEL=)`.

- [ ] **Step 4: Clean up the smoke-test output so it doesn't accidentally get committed.**

```powershell
Remove-Item -Recurse -Force build\plan-smoke
```

- [ ] **Step 5: Run pytest golden tests and confirm they fail as expected (snapshot mismatch on all 5 scenarios).**

```powershell
pytest tests/golden/ -q
```

Expected: 5 failures, all of shape `AssertionError: assert '...' == '...'` with the diff showing the new `%post --nochroot` block. Failure count = 5 because there are 5 golden scenarios: `test_minimal_dhcp`, `test_modern_crypto`, `test_stig_strict`, `test_bare_metal_usbguard`, `test_unattended_disabled`.

- [ ] **Step 6: Run the existing lint tests and confirm they still pass.**

```powershell
pytest tests/test_lint.py -q
```

Expected: PASS. The existing lint invariants key off the eval-block header `%post --erroronfail --log=/root/ks-post-oscap.log` and the `oscap xccdf eval --remediate` invocation — both unchanged.

- [ ] **Step 7: Run ruff + mypy.**

```powershell
ruff check src tests
ruff format --check src tests
mypy
```

Expected: all clean. (The template change is Jinja text; no Python touched yet.)

- [ ] **Step 8: Stage and commit just the template change.**

```powershell
git add src\ks_gen\templates\ks.cfg.j2
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m @'
feat(template): split oscap %post into --nochroot fetch + chrooted eval

Splits the single oscap %post block into two adjacent blocks. The
first runs --nochroot (installer environment) and dispatches on the
inst.ks transport: existing http(s) branch keeps curl, new hd:LABEL=*)
arm cps from /run/install/repo/tailoring.xml. Both stage into
/mnt/sysimage/root/tailoring.xml. The second block stays chrooted and
runs oscap xccdf eval --remediate against /root/tailoring.xml exactly
as before.

Why the split: /run/install/repo is not bind-mounted into the chroot
during %post by default, so a single chrooted-%post hd: branch would
silently fail. --nochroot has access to both the install media and
the network, so both transports converge on one fetch path.

Golden snapshots will fail until regenerated in the next commit.
Existing lint invariants pass unchanged (eval-block header
preserved). New lint invariants for the fetch block + hd:LABEL= arm
land in a later commit.

Refs: docs/superpowers/specs/2026-06-06-hd-oscap-transport-design.md
'@
```

- [ ] **Step 9: Verify the commit landed with a good GPG signature.**

```powershell
git log -1 --show-signature
```

Expected: `gpg: Good signature from "Patrick Connallon (SupremeCommanderHedgehog)"` and the commit message above. If the signature line is missing or says BAD/UNKNOWN, stop and report.

---

## Task 3: Regenerate golden snapshots and inspect the diffs

**Files:**
- Modify: `tests/golden/__snapshots__/test_minimal_dhcp.ambr`
- Modify: `tests/golden/__snapshots__/test_modern_crypto.ambr`
- Modify: `tests/golden/__snapshots__/test_stig_strict.ambr`
- Modify: `tests/golden/__snapshots__/test_bare_metal_usbguard.ambr`
- Modify: `tests/golden/__snapshots__/test_unattended_disabled.ambr`

- [ ] **Step 1: Regenerate all golden snapshots.**

```powershell
pytest tests/golden/ --snapshot-update -q
```

Expected: snapshots updated for all 5 scenarios; pytest reports PASS after the update.

- [ ] **Step 2: Inspect the diff on each `.ambr` file — confirm the change shape matches the spec.**

```powershell
git diff --stat tests\golden\__snapshots__\
```

Expected: 5 files changed, each with roughly +14/-7 lines (one block becomes two; comment block changes wording; new `hd:LABEL=*)` arm + `chmod`; case-statement reflow). No file outside `tests/golden/__snapshots__/` should appear in the diff.

```powershell
git diff tests\golden\__snapshots__\test_minimal_dhcp.ambr | Select-String -Pattern '^[+-]' | Select-Object -First 80
```

Expected diff regions, in order:

- The line `%post --erroronfail --log=/root/ks-post-oscap.log` is replaced by `%post --nochroot --erroronfail --log=/mnt/sysimage/root/ks-post-oscap-fetch.log`.
- The comment block changes from the v0.1 "addon supplied-content" rationale to the new "--nochroot environment" rationale.
- The `curl` line gains a backslash + line-break and the `-o` path changes from `/root/tailoring.xml` to `/mnt/sysimage/root/tailoring.xml`.
- New `hd:LABEL=*)` arm + `cp` line + `;;` added before the `*)` fallback.
- The fallback's error string updates from `(v0.1 supports http(s) only)` to `(supports http(s) and hd:LABEL=)`.
- New `chmod 0600 /mnt/sysimage/root/tailoring.xml` line.
- New `%end` (closing the fetch block) and new `%post --erroronfail --log=/root/ks-post-oscap.log` + `set -euo pipefail` (opening the eval block).
- Everything from `test -s /root/tailoring.xml` onward is unchanged in content (but may appear in the diff as a context-shift artifact).

If any `.ambr` shows a diff outside this shape — e.g., rule-block reorder, partitioning churn, tailoring.xml mutation — stop and investigate. A regen that touches anything else means an unintended side-effect.

Repeat the spot-check for the other four snapshots:

```powershell
foreach ($f in 'test_modern_crypto', 'test_stig_strict', 'test_bare_metal_usbguard', 'test_unattended_disabled') {
  Write-Host "===== $f =====" -ForegroundColor Cyan
  git diff tests\golden\__snapshots__\$f.ambr | Select-String -Pattern '^[+-]%post' -Context 0,2
}
```

Expected: each scenario shows the same `%post` header pattern (the old single header line gone, two new header lines added).

- [ ] **Step 3: Run the full test suite to confirm nothing else broke.**

```powershell
pytest -q
```

Expected: PASS (every test). If anything other than the goldens fails, investigate — the template change should not affect rule-emit tests, config-validation tests, or CLI tests.

- [ ] **Step 4: Run the full CI parity chain end-to-end.**

```powershell
ruff check src tests
ruff format --check src tests
mypy
pytest -q
```

Expected: all four clean.

- [ ] **Step 5: Commit the regenerated snapshots.**

```powershell
git add tests\golden\__snapshots__\
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m @'
test(golden): regenerate snapshots for oscap %post split

Five golden scenarios regenerated to match the split fetch + eval
%post blocks introduced in the previous commit. Diff shape verified
across all five scenarios: one %post header becomes two, the case
statement gains the hd:LABEL=*) arm, the curl/cp targets move from
/root/ to /mnt/sysimage/root/, and the fallback error string updates.
No rule-block reorder, no partitioning or tailoring.xml churn.

Refs: docs/superpowers/specs/2026-06-06-hd-oscap-transport-design.md
'@
git log -1 --show-signature
```

Expected: signed commit, message above, `gpg: Good signature`.

---

## Task 4: Add new lint invariants — fetch block + hd:LABEL= arm

**Files:**
- Modify: `src/ks_gen/lint.py` — extend `_internal_checks`
- Modify: `tests/test_lint.py` — add two negative tests

- [ ] **Step 1: Write the first failing negative test — fetch block absent should be caught by lint.**

Append to `tests/test_lint.py`:

```python
def test_lint_detects_missing_oscap_fetch_block(tmp_path):
    out = _generate(tmp_path)
    ks = out / "ks.cfg"
    text = ks.read_text(encoding="utf-8")
    # Mangle the fetch %post header so the block is no longer recognisable
    text = text.replace(
        "%post --nochroot --erroronfail --log=/mnt/sysimage/root/ks-post-oscap-fetch.log",
        "%post --nochroot --log=/mnt/sysimage/root/ks-post-oscap-fetch.log",
    )
    ks.write_text(text, encoding="utf-8")
    report = lint_kickstart(ks)
    assert not report.ok
    assert any("missing: %post --nochroot oscap fetch block" in f for f in report.failures)
```

- [ ] **Step 2: Run the new test — confirm it fails.**

```powershell
pytest tests/test_lint.py::test_lint_detects_missing_oscap_fetch_block -v
```

Expected: FAIL. Mode of failure: `assert not report.ok` — lint currently passes the mutated text because the fetch-block invariant doesn't exist yet, so `report.ok` is `True`.

- [ ] **Step 3: Write the second failing negative test — missing `hd:LABEL=*)` arm should be caught.**

Append to `tests/test_lint.py`:

```python
def test_lint_detects_missing_hd_label_branch(tmp_path):
    out = _generate(tmp_path)
    ks = out / "ks.cfg"
    text = ks.read_text(encoding="utf-8")
    # Rename the hd: arm header so lint's branch-presence check fails
    text = text.replace("hd:LABEL=*)", "hd:DISARMED=*)")
    ks.write_text(text, encoding="utf-8")
    report = lint_kickstart(ks)
    assert not report.ok
    assert any("hd:LABEL= branch in oscap fetch case" in f for f in report.failures)
```

- [ ] **Step 4: Run the second new test — confirm it fails for the same reason.**

```powershell
pytest tests/test_lint.py::test_lint_detects_missing_hd_label_branch -v
```

Expected: FAIL. `assert not report.ok` — lint currently passes the mutated text.

- [ ] **Step 5: Read the current `src/ks_gen/lint.py` `_internal_checks` so the next edit lands precisely.**

The function spans lines 27-47 today. Edit will replace its body to add the three new invariants (fetch block presence, hd:LABEL= arm presence, fetch-precedes-eval ordering).

- [ ] **Step 6: Replace `_internal_checks` in `src/ks_gen/lint.py`.**

`old_string`:

```python
def _internal_checks(text: str) -> list[str]:
    failures: list[str] = []
    if "authorized_keys" not in text:
        failures.append("missing: authorized_keys write in %post")
    a = text.find("# ===== admin_user_and_keys =====")
    s = text.find("# ===== ssh_config_apply =====")
    if a == -1:
        failures.append("missing: admin_user_and_keys post block")
    if s == -1:
        failures.append("missing: ssh_config_apply post block")
    if a != -1 and s != -1 and a >= s:
        failures.append("ordering: admin_user_and_keys must precede ssh_config_apply")
    oscap_idx = text.find("%post --erroronfail --log=/root/ks-post-oscap.log")
    if oscap_idx == -1:
        failures.append("missing: %post oscap remediation block")
    else:
        if "oscap xccdf eval --remediate" not in text[oscap_idx:]:
            failures.append("missing: oscap remediation invocation in %post oscap block")
        if "--tailoring-file /root/tailoring.xml" not in text[oscap_idx:]:
            failures.append("missing: --tailoring-file reference in %post oscap block")
    return failures
```

`new_string`:

```python
def _internal_checks(text: str) -> list[str]:
    failures: list[str] = []
    if "authorized_keys" not in text:
        failures.append("missing: authorized_keys write in %post")
    a = text.find("# ===== admin_user_and_keys =====")
    s = text.find("# ===== ssh_config_apply =====")
    if a == -1:
        failures.append("missing: admin_user_and_keys post block")
    if s == -1:
        failures.append("missing: ssh_config_apply post block")
    if a != -1 and s != -1 and a >= s:
        failures.append("ordering: admin_user_and_keys must precede ssh_config_apply")
    fetch_idx = text.find(
        "%post --nochroot --erroronfail --log=/mnt/sysimage/root/ks-post-oscap-fetch.log"
    )
    oscap_idx = text.find("%post --erroronfail --log=/root/ks-post-oscap.log")
    if fetch_idx == -1:
        failures.append("missing: %post --nochroot oscap fetch block")
    if oscap_idx == -1:
        failures.append("missing: %post oscap remediation block")
    else:
        if "oscap xccdf eval --remediate" not in text[oscap_idx:]:
            failures.append("missing: oscap remediation invocation in %post oscap block")
        if "--tailoring-file /root/tailoring.xml" not in text[oscap_idx:]:
            failures.append("missing: --tailoring-file reference in %post oscap block")
    if fetch_idx != -1 and oscap_idx != -1:
        if fetch_idx >= oscap_idx:
            failures.append("ordering: oscap fetch block must precede oscap eval block")
        else:
            fetch_region = text[fetch_idx:oscap_idx]
            if "hd:LABEL=*)" not in fetch_region:
                failures.append("missing: hd:LABEL= branch in oscap fetch case")
            if (
                "cp /run/install/repo/tailoring.xml /mnt/sysimage/root/tailoring.xml"
                not in fetch_region
            ):
                failures.append("missing: hd: cp from /run/install/repo in oscap fetch case")
    return failures
```

- [ ] **Step 7: Run the two new negative tests — they should now pass.**

```powershell
pytest tests/test_lint.py::test_lint_detects_missing_oscap_fetch_block tests/test_lint.py::test_lint_detects_missing_hd_label_branch -v
```

Expected: both PASS.

- [ ] **Step 8: Run the full lint test file — all four existing tests + two new ones should pass.**

```powershell
pytest tests/test_lint.py -v
```

Expected: 6 PASS. The existing `test_lint_accepts_known_good`, `test_lint_detects_missing_authorized_keys`, `test_lint_detects_sshd_before_admin`, and `test_lint_detects_missing_oscap_post_block` all continue to pass (they test invariants unaffected by the new checks).

- [ ] **Step 9: Run the full CI parity chain.**

```powershell
ruff check src tests
ruff format --check src tests
mypy
pytest -q
```

Expected: all four clean. If `ruff format --check` complains, fix with `ruff format src tests` and re-verify with `ruff format --check src tests`.

- [ ] **Step 10: Commit the lint additions.**

```powershell
git add src\ks_gen\lint.py tests\test_lint.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m @'
test(lint): hd:LABEL= and oscap fetch-block invariants

Extends _internal_checks with three new invariants matched to the
split oscap %post:

  - fetch block (%post --nochroot) presence
  - fetch-precedes-eval ordering
  - hd:LABEL=*) arm + matching cp from /run/install/repo present
    inside the fetch block

Adds two negative tests in test_lint.py that mutate the rendered
ks.cfg to break each invariant and assert lint catches it. The
existing positive test (test_lint_accepts_known_good) exercises the
new invariants implicitly.

Refs: docs/superpowers/specs/2026-06-06-hd-oscap-transport-design.md
'@
git log -1 --show-signature
```

Expected: signed commit, `gpg: Good signature`.

---

## Task 5: Documentation — MANUAL, README, CHANGELOG, MINIMAL-TEST

**Files:**
- Modify: `MANUAL.md` (around §5.4, line ~563-590)
- Modify: `README.md` (the "v0.1 known limitations" section)
- Modify: `CHANGELOG.md` (the `[Unreleased]` block)
- Modify: `MINIMAL-TEST.md` (new ISO walkthrough after Step 5)

- [ ] **Step 1: Update `MANUAL.md` §5.4 `ks-gen iso` to note the `%post --nochroot` staging.**

`old_string` (current §5.4 between `**v0.1 limitation:**` and the `xorriso` note):

```
**v0.1 limitation:** the wrapper places the files at the ISO root
but does NOT rewrite `isolinux/isolinux.cfg` or
`EFI/BOOT/grub.cfg`. At the Anaconda boot prompt you must press
**Tab** (BIOS) or **e** (UEFI) and append:

```
inst.ks=hd:LABEL=ALMA9:/ks.cfg
```

Bootloader rewriting for fully unattended installs is tracked for
v0.2.
```

`new_string`:

```
**v0.1 limitation:** the wrapper places the files at the ISO root
but does NOT rewrite `isolinux/isolinux.cfg` or
`EFI/BOOT/grub.cfg`. At the Anaconda boot prompt you must press
**Tab** (BIOS) or **e** (UEFI) and append:

```
inst.ks=hd:LABEL=ALMA9:/ks.cfg
```

Bootloader rewriting for fully unattended installs is tracked for
v0.2.

**How `tailoring.xml` gets to oscap:** the generated `ks.cfg` opens
with a `%post --nochroot` block that runs in the Anaconda installer
environment (not the target chroot) and copies
`/run/install/repo/tailoring.xml` — the path Anaconda mounts the
boot media at — to `/root/tailoring.xml` on the installed system.
A chrooted `%post` block then runs `oscap xccdf eval --remediate`
against it. The same `--nochroot` block handles HTTP delivery via
`curl`; the transport is auto-detected from `/proc/cmdline`. No HTTP
server is needed for the ISO path.
```

- [ ] **Step 2: Update `README.md` — remove the now-obsolete "v0.1 known limitations" entry about `ks-gen iso`, since the only remaining v0.1 limitation there is the bootloader-rewrite issue (which is real and stays).**

Read the current `## v0.1 known limitations` section (lines 42-52). The first bullet currently reads:

```
- **`ks-gen iso` does not rewrite the ISO's bootloader.** It places `ks.cfg`
  and `tailoring.xml` at the ISO root, but the operator must type
  `inst.ks=hd:LABEL=<volid>:/ks.cfg` at the Anaconda boot prompt. Fully
  unattended installs from the generated ISO land in v0.2.
```

This bullet stays as-is — that limitation is real and unaddressed by this change. No edit needed in `README.md` for §"v0.1 known limitations".

Instead, add one line to the Quickstart section (lines 13-25) about ISO delivery being a supported alternative. `old_string`:

```
## Quickstart

```bash
pipx install .
ks-gen new --out ./build
# Walks you through a few prompts, writes ./build/<hostname>/{host.yaml,ks.cfg,tailoring.xml,exceptions.md}

ks-gen gen --config ./build/<hostname>/host.yaml --out ./build/<hostname>
ks-gen iso --src AlmaLinux-9-latest-x86_64-dvd.iso \
           --ks ./build/<hostname>/ks.cfg \
           --tailoring ./build/<hostname>/tailoring.xml \
           --out ./<hostname>-installer.iso
```
```

`new_string`:

```
## Quickstart

```bash
pipx install .
ks-gen new --out ./build
# Walks you through a few prompts, writes ./build/<hostname>/{host.yaml,ks.cfg,tailoring.xml,exceptions.md}

ks-gen gen --config ./build/<hostname>/host.yaml --out ./build/<hostname>
ks-gen iso --src AlmaLinux-9-latest-x86_64-dvd.iso \
           --ks ./build/<hostname>/ks.cfg \
           --tailoring ./build/<hostname>/tailoring.xml \
           --out ./<hostname>-installer.iso
```

Delivery modes: HTTP (`inst.ks=http://…/ks.cfg`) or ISO
(`inst.ks=hd:LABEL=<volid>:/ks.cfg`, with the ISO from `ks-gen iso`).
Both run oscap remediation at install time; see `MANUAL.md` §5.4.
```

- [ ] **Step 3: Update `CHANGELOG.md` — add an `[Unreleased]` entry.**

Read the current `## [Unreleased]` section, then `Edit` to add the new entry above the `unattended_updates` one (newer-first ordering).

`old_string`:

```
## [Unreleased]

### Added
- `unattended_updates` rule + `overrides.unattended_updates` config block.
```

`new_string`:

```
## [Unreleased]

### Added
- **`hd:LABEL=` transport for oscap tailoring fetch.** The oscap `%post`
  block is now split into a `--nochroot` fetch stage and a chrooted
  eval stage. ISO-delivered bundles (`ks-gen iso`) now reach oscap
  remediation at install time; previously, install failed with
  `unsupported inst.ks transport`. HTTP delivery is unchanged
  operator-visibly. Closes the second of the two v0.1.x gaps queued
  before v0.2.0.
- `unattended_updates` rule + `overrides.unattended_updates` config block.
```

- [ ] **Step 4: Update `MINIMAL-TEST.md` — add the ISO walkthrough as a new "Alternative: ISO delivery" section after Step 5.**

Read the current Step 5 / pre-Step 6 region to find a clean insertion point. The text right before "## Step 6 — Find the VM's IP after reboot" is the end of the HTTP install narrative (around line 145-146: "Total wall-clock: ~10-15 minutes on a modern host, then a reboot.").

`old_string`:

```
Total wall-clock: ~10-15 minutes on a modern host, then a reboot.

## Step 6 — Find the VM's IP after reboot
```

`new_string`:

```
Total wall-clock: ~10-15 minutes on a modern host, then a reboot.

## Alternative — ISO delivery (instead of Steps 1-5)

Use this path when you want to verify the `hd:LABEL=` transport — i.e.,
that a `ks-gen iso` bundle installs end-to-end without an HTTP server.

### A. Build the tailored ISO

```powershell
cd C:\Users\yizshachuck\source\alma-linux-security
.venv\Scripts\python.exe -m ks_gen iso `
  --src AlmaLinux-9-latest-x86_64-dvd.iso `
  --ks  build\web01\ks.cfg `
  --tailoring build\web01\tailoring.xml `
  --out build\web01\ks-gen-web01.iso `
  --volid ALMA9KS
```

The `--volid ALMA9KS` label is distinct from the v0.1.0 default `ALMA9`
to make the LABEL → boot-prompt mapping visually obvious below.

### B. Create the VM (replaces Step 4)

Same `New-VM` block as Step 4, but attach the tailored ISO instead of
the stock one:

```powershell
$ISO  = 'C:\Users\yizshachuck\source\alma-linux-security\build\web01\ks-gen-web01.iso'
$VHDX = 'C:\Hyper-V\Virtual Hard Disks\ks-gen-web01.vhdx'
# ...rest of Step 4 unchanged...
```

### C. Boot and inject `inst.ks=hd:LABEL=…` (replaces Step 5)

At the GRUB `e`-edit prompt, append (note leading space):

```
 inst.ks=hd:LABEL=ALMA9KS:/ks.cfg
```

The label must match the `--volid` from step A. No HTTP server is
needed; window #1 (`python -m http.server`) is irrelevant for this path.

### D. Expected signals during install

- Anaconda mounts the ISO at `/run/install/repo` and reads `/ks.cfg`
  from there. You won't see GETs in any HTTP server log.
- The first `%post --nochroot` block stages
  `/run/install/repo/tailoring.xml` into the target rootfs at
  `/mnt/sysimage/root/tailoring.xml` (= `/root/tailoring.xml` on the
  installed system).
- The second `%post` block runs `oscap xccdf eval --remediate` against
  `/root/tailoring.xml` exactly as on the HTTP path.

After reboot, both logs should exist on the installed system:

```bash
ls -l /root/ks-post-oscap-fetch.log /root/ks-post-oscap.log /root/ks-post.log
```

Continue to Steps 6 (find VM IP), 7 (SSH in), and 8 (verify STIG
compliance) below — they are transport-agnostic.

## Step 6 — Find the VM's IP after reboot
```

- [ ] **Step 5: Run the full CI parity chain — doc edits should not have moved anything.**

```powershell
ruff check src tests
ruff format --check src tests
mypy
pytest -q
```

Expected: all four clean. (Doc edits don't touch Python or templates; this confirms no accidental changes leaked in.)

- [ ] **Step 6: Spot-check the modified docs render sensibly.**

```powershell
git diff --stat MANUAL.md README.md CHANGELOG.md MINIMAL-TEST.md
```

Expected: 4 files changed, modest +N/-M counts (CHANGELOG ~+9, README ~+4, MANUAL ~+12, MINIMAL-TEST ~+55).

```powershell
git diff MANUAL.md | Select-Object -First 60
```

Eyeball the diff — confirm only the §5.4 paragraph addition is present (no accidental rewrites elsewhere). Repeat for `README.md`, `CHANGELOG.md`, `MINIMAL-TEST.md`.

- [ ] **Step 7: Commit the documentation.**

```powershell
git add MANUAL.md README.md CHANGELOG.md MINIMAL-TEST.md
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m @'
docs: hd:LABEL= transport — MANUAL, README, CHANGELOG, MINIMAL-TEST

MANUAL §5.4: explain that the generated ks.cfg stages tailoring.xml
via %post --nochroot from /run/install/repo (ISO) or curl (HTTP),
no HTTP server needed for ISO delivery.

README quickstart: note that both HTTP and ISO delivery are
supported transports.

CHANGELOG [Unreleased]: hd:LABEL= entry above the unattended_updates
entry.

MINIMAL-TEST: new "Alternative — ISO delivery" section after Step 5,
mirroring Steps 1-5 of the HTTP walkthrough but using ks-gen iso +
inst.ks=hd:LABEL=ALMA9KS:/ks.cfg. Steps 6-8 (find IP, SSH, verify
STIG) are transport-agnostic and referenced rather than duplicated.

Refs: docs/superpowers/specs/2026-06-06-hd-oscap-transport-design.md
'@
git log -1 --show-signature
```

Expected: signed commit, `gpg: Good signature`.

---

## Task 6: Final verification — full CI chain end-to-end

**Files:** none modified

- [ ] **Step 1: Run the full CI parity chain one more time, exactly as `.github/workflows/ci.yml` will run it.**

```powershell
ruff check src tests
ruff format --check src tests
mypy
pytest -q
```

Expected: all four exit 0.

- [ ] **Step 2: Confirm the four implementation commits + the pre-existing spec commit are all signed.**

```powershell
git log --show-signature -5
```

Expected: 5 commits, in this order from newest to oldest:

1. `docs: hd:LABEL= transport — MANUAL, README, CHANGELOG, MINIMAL-TEST`
2. `test(lint): hd:LABEL= and oscap fetch-block invariants`
3. `test(golden): regenerate snapshots for oscap %post split`
4. `feat(template): split oscap %post into --nochroot fetch + chrooted eval`
5. `docs(spec): hd:LABEL= oscap transport design`

Each commit should show `gpg: Good signature from "Patrick Connallon (SupremeCommanderHedgehog)"`.

- [ ] **Step 3: Confirm `git status` is clean.**

```powershell
git status --short
```

Expected: empty (or only `?? .claude/`).

- [ ] **Step 4: Report.**

Report to the user: implementation complete on branch `impl/v0.2.0-hd-oscap-transport`. 4 implementation commits added on top of the spec commit `a42f829`, all signed. Local CI chain clean. ISO-delivery acceptance test on Hyper-V is the remaining manual verification gate — see `MINIMAL-TEST.md` "Alternative — ISO delivery" section. Do NOT push, do NOT open the PR, and do NOT manually trigger the GitHub Backup scheduled task. After the user's go-ahead, this finishes the second of the two v0.1.x gaps; the OVAL `--fetch-remote-resources` change is the remaining blocker before tagging v0.2.0.
