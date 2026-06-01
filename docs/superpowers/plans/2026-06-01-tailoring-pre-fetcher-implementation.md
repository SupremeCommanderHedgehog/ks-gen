# Tailoring `%pre` Fetcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HTTP-served and ISO-injected kickstarts actually deliver `tailoring.xml` to `oscap-anaconda-addon`, by emitting a `%pre` shim into every generated `ks.cfg`.

**Architecture:** Insert a static `%pre` block in `src/ks_gen/templates/ks.cfg.j2` immediately before `%packages`. The block reads `/proc/cmdline` for `inst.ks=`, then `curl`s `tailoring.xml` from the same base URL (HTTP path) or `cp`s it from `/run/install/repo` (`hd:LABEL=` path), and exits non-zero on any failure so Anaconda aborts loudly instead of silently applying base STIG.

**Tech Stack:** Python 3.11+, Jinja2, pytest + syrupy snapshots, ruff, mypy --strict.

**Spec:** `docs/superpowers/specs/2026-06-01-tailoring-pre-fetcher-design.md`

**Branch:** `impl/v0.1.0` — PR #1 picks up new commits. No version bump (v0.1.0 not yet tagged).

**Commit conventions:**
- Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`)
- Every commit signed with key `BE707B220C995478`, author `github.v5f9w@bitbucket.onl`
- Use the form: `git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "..."`

---

## File structure

| File | Action | Responsibility |
|---|---|---|
| `src/ks_gen/templates/ks.cfg.j2` | modify | Insert static `%pre` block before `%packages` |
| `tests/test_skeleton.py` | modify | Add invariant test asserting the `%pre` block's required properties |
| `tests/golden/__snapshots__/test_minimal_dhcp.ambr` | regenerate | Snapshot picks up new template output |
| `tests/golden/__snapshots__/test_stig_strict.ambr` | regenerate | Snapshot picks up new template output |
| `tests/golden/__snapshots__/test_modern_crypto.ambr` | regenerate | Snapshot picks up new template output |
| `tests/golden/__snapshots__/test_bare_metal_usbguard.ambr` | regenerate | Snapshot picks up new template output |
| `MINIMAL-TEST.md` | modify | Step 5 narrative reflects real two-GET pattern (Anaconda + `%pre` curl) |
| `CHANGELOG.md` | modify | Add a `Fixed` entry under v0.1.0 |
| `docs/superpowers/specs/2026-06-01-alma-stig-kickstart-design.md` | modify | One-paragraph addendum in §2.1 pointing to the new spec |

The template is the only behavior change. Everything else is tests, snapshots, or docs that ride along.

---

## Task 1: Add `%pre` tailoring fetcher to ks.cfg.j2 (TDD)

**Files:**
- Modify: `tests/test_skeleton.py` (append new test function)
- Modify: `src/ks_gen/templates/ks.cfg.j2` (insert `%pre` block before line 31's `%packages`)
- Regenerate: `tests/golden/__snapshots__/*.ambr` (all four)

- [ ] **Step 1: Write the failing invariant test**

Append to `tests/test_skeleton.py`:

```python
def test_skeleton_emits_pre_tailoring_fetcher(minimal_cfg):
    out = render_skeleton(minimal_cfg, post_blocks=[])

    pre_idx = out.find("%pre --erroronfail --log=/tmp/ks-pre-tailoring.log")
    addon_idx = out.find("%addon org_fedora_oscap")
    packages_idx = out.find("%packages")

    assert pre_idx != -1, "missing %pre tailoring fetcher block"
    assert addon_idx != -1, "missing %addon block"
    assert packages_idx != -1, "missing %packages block"
    assert pre_idx < packages_idx < addon_idx, (
        "expected order: %pre < %packages < %addon"
    )

    pre_body = out[pre_idx:packages_idx]
    assert "set -euo pipefail" in pre_body, "missing strict shell flags"
    assert "[ -s /tailoring.xml ]" in pre_body, "missing idempotence guard"
    assert "/proc/cmdline" in pre_body, "must derive transport from cmdline"
    assert "http://*|https://*" in pre_body, "missing HTTP case branch"
    assert "hd:*" in pre_body, "missing hd: case branch"
    assert "curl -fsSL --retry 5 --retry-delay 3" in pre_body, (
        "missing curl with retry"
    )
    assert "/run/install/repo/tailoring.xml" in pre_body, (
        "missing hd: source path"
    )
    assert "head -c 5 /tailoring.xml | grep -q '<?xml'" in pre_body, (
        "missing xml sentinel check"
    )
    assert "exit 1" in pre_body, "missing fallback hard-fail for unknown transport"
    assert pre_body.count("%end") >= 1, "%pre block not closed"
```

- [ ] **Step 2: Run the new test, expect FAIL**

Run: `.venv\Scripts\python.exe -m pytest tests/test_skeleton.py::test_skeleton_emits_pre_tailoring_fetcher -v`

Expected: `FAILED` with `AssertionError: missing %pre tailoring fetcher block` (pre_idx == -1).

- [ ] **Step 3: Insert the `%pre` block into the template**

Edit `src/ks_gen/templates/ks.cfg.j2`. Find the line:

```
authselect select sssd --force

%packages
```

Replace with:

```
authselect select sssd --force

%pre --erroronfail --log=/tmp/ks-pre-tailoring.log
set -euo pipefail

if [ -s /tailoring.xml ]; then
  echo "ks-gen: /tailoring.xml already present, skipping fetch"
  exit 0
fi

ks_arg=$(awk -F'inst.ks=' 'NF>1{print $2}' /proc/cmdline | awk '{print $1}')
case "$ks_arg" in
  http://*|https://*)
    base="${ks_arg%/*}"
    curl -fsSL --retry 5 --retry-delay 3 "${base}/tailoring.xml" -o /tailoring.xml
    ;;
  hd:*)
    cp -f /run/install/repo/tailoring.xml /tailoring.xml || \
      cp -f /run/install/repo/tailoring.xml /tailoring.xml
    ;;
  *)
    echo "ks-gen: unsupported inst.ks transport '$ks_arg'; cannot fetch tailoring.xml" >&2
    exit 1
    ;;
esac

test -s /tailoring.xml
head -c 5 /tailoring.xml | grep -q '<?xml'
%end

%packages
```

Note: this block contains no Jinja syntax (`{{ }}`, `{% %}`), so `trim_blocks` / `lstrip_blocks` won't alter it. The `${ks_arg%/*}` is bash parameter expansion, not Jinja.

- [ ] **Step 4: Run the new test, expect PASS**

Run: `.venv\Scripts\python.exe -m pytest tests/test_skeleton.py::test_skeleton_emits_pre_tailoring_fetcher -v`

Expected: `1 passed`.

- [ ] **Step 5: Run the full suite, expect golden snapshot failures**

Run: `.venv\Scripts\python.exe -m pytest -q`

Expected: 4 golden snapshot tests fail (`test_minimal_dhcp`, `test_stig_strict`, `test_modern_crypto`, `test_bare_metal_usbguard`) because the rendered `ks.cfg` now contains the new `%pre` block that isn't in the stored snapshots. All other tests should pass.

- [ ] **Step 6: Regenerate the four golden snapshots**

Run: `.venv\Scripts\python.exe -m pytest tests/golden/ --snapshot-update -q`

Expected: 4 tests pass with a "snapshot updated" notice. `.ambr` files in `tests/golden/__snapshots__/` are rewritten.

- [ ] **Step 7: Run the full suite, expect all pass**

Run: `.venv\Scripts\python.exe -m pytest -q`

Expected: `154 passed` (or 155 with the new invariant test).

- [ ] **Step 8: Lint and type-check**

Run in parallel:
- `.venv\Scripts\python.exe -m ruff check src tests`
- `.venv\Scripts\python.exe -m ruff format --check src tests`
- `.venv\Scripts\python.exe -m mypy --strict src/ks_gen`

Expected: all clean.

- [ ] **Step 9: Commit**

```
git add src/ks_gen/templates/ks.cfg.j2 tests/test_skeleton.py tests/golden/__snapshots__/
git -c user.email="github.v5f9w@bitbucket.onl" \
    -c user.signingkey=BE707B220C995478 \
    commit -S -m "fix(template): %pre stages tailoring.xml before %addon

oscap-anaconda-addon reads tailoring-path as a local installer-FS path.
HTTP-served bundles and ks-gen iso bundles both leave /tailoring.xml
empty, so the addon silently falls back to the unmodified base STIG
profile — exactly the lockout failure ks-gen exists to neutralize.

Emit a static %pre block in every generated ks.cfg that reads
inst.ks= from /proc/cmdline and either curls tailoring.xml from the
same HTTP base (--retry 5 --retry-delay 3) or copies it from
/run/install/repo (hd:LABEL= delivery, used by ks-gen iso). Any
other transport, or a fetch failure, exits non-zero under
%pre --erroronfail so Anaconda aborts loudly.

Spec: docs/superpowers/specs/2026-06-01-tailoring-pre-fetcher-design.md"
```

Confirm the commit is signed: `git log -1 --show-signature 2>&1 | head -5` should show `Good signature from "Patrick Connallon"`.

---

## Task 2: Update operator docs, changelog, and parent design spec

**Files:**
- Modify: `MINIMAL-TEST.md` (Step 5 narrative)
- Modify: `CHANGELOG.md` (Fixed entry under v0.1.0)
- Modify: `docs/superpowers/specs/2026-06-01-alma-stig-kickstart-design.md` (addendum in §2.1)

- [ ] **Step 1: Fix MINIMAL-TEST.md Step 5 narrative**

In `MINIMAL-TEST.md`, find the block:

```
Within ~30 seconds, window #1 should log:

```
"GET /ks.cfg HTTP/1.1" 200 -
"GET /tailoring.xml HTTP/1.1" 200 -
```

That confirms Anaconda fetched the kickstart. The install proceeds
unattended — packages, oscap remediation, `%post` (admin user + sshd config +
crypto policy + …), then a reboot. Total: ~10-15 minutes on a modern host.
```

Replace with:

```
Within ~30 seconds, window #1 should log:

```
"GET /ks.cfg HTTP/1.1" 200 -
"GET /tailoring.xml HTTP/1.1" 200 -
```

The first GET is Anaconda parsing the kickstart. The second is the `%pre`
block inside `ks.cfg` reading `inst.ks=` from `/proc/cmdline` and curling
`tailoring.xml` from the same base URL into `/tailoring.xml` for
`oscap-anaconda-addon` to pick up. If you see only the first GET, the
`%pre` is failing — check the VM console for the `ks-gen:` prefix or
inspect `/tmp/ks-pre-tailoring.log` after Anaconda drops to a shell.

The install proceeds unattended — packages, oscap remediation, `%post`
(admin user + sshd config + crypto policy + …), then a reboot. Total:
~10-15 minutes on a modern host.
```

- [ ] **Step 2: Add a Fixed section to CHANGELOG.md v0.1.0**

In `CHANGELOG.md`, the v0.1.0 section currently only has `### Added`. Append after the Added block:

```
### Fixed
- `ks.cfg` now emits a `%pre` block that stages `tailoring.xml` at
  `/tailoring.xml` before `%addon` runs. Previously `oscap-anaconda-addon`
  found nothing at that path under both HTTP-served and `ks-gen iso`
  delivery, silently falling back to the unmodified base STIG profile.
  See `docs/superpowers/specs/2026-06-01-tailoring-pre-fetcher-design.md`.
```

- [ ] **Step 3: Add addendum to the parent design spec**

In `docs/superpowers/specs/2026-06-01-alma-stig-kickstart-design.md`, find the end of section §2.1 (line ~100, just before `### 2.2 External tool dependencies`):

```
Execution timeline inside Anaconda:

```
%packages → %addon org_fedora_oscap [reads tailoring.xml, remediates] → %post → reboot
```

### 2.2 External tool dependencies
```

Insert between the timeline code block and `### 2.2`:

```

**Tailoring delivery.** `oscap-anaconda-addon` reads `tailoring.xml` from
a local installer-FS path (`/tailoring.xml`), not a URL. A static `%pre`
block emitted into every `ks.cfg` is responsible for staging the file at
that path before `%addon` runs — `curl`-ing from the same base URL when
the kickstart was served over `http(s)://`, or `cp`-ing it from
`/run/install/repo` when delivered via `hd:LABEL=` (the `ks-gen iso`
path). See `docs/superpowers/specs/2026-06-01-tailoring-pre-fetcher-design.md`
for the full design.

### 2.2 External tool dependencies
```

- [ ] **Step 4: Re-run full suite to confirm docs-only changes broke nothing**

Run: `.venv\Scripts\python.exe -m pytest -q`

Expected: same pass count as Task 1 Step 7.

- [ ] **Step 5: Commit**

```
git add MINIMAL-TEST.md CHANGELOG.md docs/superpowers/specs/2026-06-01-alma-stig-kickstart-design.md
git -c user.email="github.v5f9w@bitbucket.onl" \
    -c user.signingkey=BE707B220C995478 \
    commit -S -m "docs: explain tailoring %pre fetcher in MINIMAL-TEST and parent spec

- MINIMAL-TEST.md Step 5: the second GET is from %pre, not Anaconda;
  point operators at /tmp/ks-pre-tailoring.log when it's missing.
- CHANGELOG.md: Fixed entry under v0.1.0 (lands before tag).
- alma-stig-kickstart-design.md §2.1: tailoring-delivery addendum
  pointing to the dedicated spec."
```

---

## Task 3: Regenerate the local operator bundle and self-verify

This task has no commit (`build/` is gitignored). It re-runs Steps 1 and 3 of `MINIMAL-TEST.md` so the user can re-execute Steps 4–8 in their admin PowerShell.

- [ ] **Step 1: Regenerate `build\web01` with the patched template**

Run: `.venv\Scripts\python.exe -m ks_gen gen --config build\web01.host.yaml --set disk.preset=minimal --out build\web01`

Expected: `Wrote bundle to build\web01`.

- [ ] **Step 2: Confirm the `%pre` block landed in the new ks.cfg**

Run: `Select-String -Path build\web01\ks.cfg -Pattern '%pre --erroronfail|http://\*\|https://\*|hd:\*'`

Expected: three matches showing the `%pre` header, the HTTP case, and the hd: case.

- [ ] **Step 3: Confirm the real SSH key (not the placeholder) is still in ks.cfg**

Run: `Select-String -Path build\web01\ks.cfg -Pattern 'pat@krypte.me|TESTKEYminimaldhcp'`

Expected: one match for `pat@krypte.me`, zero matches for `TESTKEYminimaldhcp`.

- [ ] **Step 4: Confirm the HTTP server (still running in the background from earlier) serves the new file**

Run: `Invoke-WebRequest -Uri 'http://172.19.176.1:8000/ks.cfg' -UseBasicParsing -TimeoutSec 5 | Select-Object -ExpandProperty Content | Select-String -Pattern '%pre --erroronfail'`

Expected: one match — the new `ks.cfg` is being served. (`python -m http.server` reads from disk on every request, so no restart is needed.)

---

## Task 4: Manual Hyper-V re-run (out-of-band, operator-driven)

Tracked here so the work isn't considered done until verified end-to-end. This is the v0.1.0 acceptance test from `MINIMAL-TEST.md`.

- [ ] **Step 1: From the admin PowerShell, create a fresh VM and boot it**

Re-run Steps 4–5 of `MINIMAL-TEST.md` verbatim with the `inst.ks=http://172.19.176.1:8000/ks.cfg` GRUB injection.

- [ ] **Step 2: Watch the local HTTP server log for both GETs**

Expect to see:

```
"GET /ks.cfg HTTP/1.1" 200 -
"GET /tailoring.xml HTTP/1.1" 200 -
```

Both must land within ~60 s of pressing Ctrl-X. The second GET is the smoke-test for this entire fix.

- [ ] **Step 3: After reboot, SSH in as `opsadmin` and run the Step 8 verification commands**

Per `MINIMAL-TEST.md` §"Step 8 — Verify STIG compliance and remote safety":

- `update-crypto-policies --show` → `DEFAULT` (matches `crypto.policy=MODERN`)
- `sudo sshd -T | egrep -i '^(port|permitrootlogin|passwordauth|clientalive)'` → expected values per the doc
- `sudo firewall-cmd --list-ports` → `22/tcp`
- `cat /etc/issue` / `sudo cat /etc/issue.net` → civilian banner, no "U.S. Government"
- `sudo oscap xccdf eval --profile xccdf_org.ssgproject.content_profile_stig --tailoring-file /tailoring.xml /usr/share/xml/scap/ssg/content/ssg-almalinux9-ds.xml | tail -40` → every failed rule matches a row in `build/web01/exceptions.md`

- [ ] **Step 4: Tick the PR #1 manual-install test-plan checkbox**

`gh pr edit 1` and check the "Manual, pre-release" box in the test plan.

- [ ] **Step 5: Cleanup**

Per `MINIMAL-TEST.md` §Cleanup:

```
Stop-VM 'ks-gen-web01' -Force
Remove-VM 'ks-gen-web01' -Force
Remove-Item 'C:\Hyper-V\Virtual Hard Disks\ks-gen-web01.vhdx'
```

And Ctrl-C the HTTP server background task.

---

## Verification — done-when

- `pytest -q` shows 155 passed (154 existing + 1 new invariant test).
- `ruff check src tests`, `ruff format --check src tests`, `mypy --strict` all clean.
- Two new signed commits on `impl/v0.1.0`: a `fix(template):` and a `docs:`.
- A regenerated `build/web01` whose `ks.cfg` contains the `%pre` block.
- A passing Hyper-V install with both GETs logged and `oscap` deviations matching `exceptions.md`.
- PR #1's manual-install test-plan box ticked.
