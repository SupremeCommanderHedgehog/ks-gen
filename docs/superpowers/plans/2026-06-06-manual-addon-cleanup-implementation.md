# MANUAL.md addon-cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace 8 stale references to `%addon org_fedora_oscap` / `oscap-anaconda-addon` in `MANUAL.md` with accurate descriptions of the current `%post`-driven oscap architecture, including a real package-list correction (verified against `src/ks_gen/config.py`) and four real lint-error troubleshooting bullets.

**Architecture:** Pure documentation change. Eight `Edit` operations against `MANUAL.md`, every old/new string given verbatim in the spec. No code, no tests. One signed commit. Existing CI parity chain (ruff/format/mypy/pytest) runs as a smoke check that nothing accidental leaked in.

**Tech Stack:** Markdown.

**Companion spec:** `docs/superpowers/specs/2026-06-06-manual-addon-cleanup-design.md` (commit `567ceb7`)

**Repo conventions to honor:**
- Conventional Commits (`docs:` here).
- Every commit signed with the user's GPG key `BE707B220C995478`. Use the explicit form: `git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "..."`.
- Local CI parity check (`ruff check src tests && ruff format --check src tests && mypy && pytest -q`) per `CLAUDE.md` before any `git push`. Doc edits shouldn't break it, but the check is the cheap insurance against accidental edits leaking elsewhere.
- Never run `Start-ScheduledTask -TaskName 'GitHub Backup'`.
- Don't push without explicit user instruction.

---

## File Structure

**Files modified:**
- `MANUAL.md` — 8 stale-architecture sites edited (§1, §3.1 table, §3.2, §3.3 timeline diagram, §4.10 packages.required, §10 troubleshooting bullet, §10 crypto-policy timing claim, §10 log-file pointer).

**Files NOT modified:**
- `src/ks_gen/lint.py` — the new troubleshooting bullets reference its existing error keys; no code change.
- `src/ks_gen/config.py` — the package-list fix removes a doc reference, not a code reference. `Packages.required` already does the right thing.
- `MANUAL.md` §11 (glossary) and §12 (references) — intentionally left alone per spec Non-goals.
- `MANUAL.md` §5.4 — PR #3 already touched it; this branch is independent.

**Files created:** none beyond the (already-committed) spec and this plan.

---

## Task 1: Baseline — confirm clean starting state

**Files:** none modified

- [ ] **Step 1: Confirm we're on the cleanup branch.**

Run from repo root (`C:\Users\yizshachuck\source\alma-linux-security`):

```powershell
git branch --show-current
```

Expected: `impl/v0.2.0-manual-cleanup`. If this prints anything else, stop and report — the spec commit `567ceb7` was made on this branch and the implementation must continue there.

- [ ] **Step 2: Confirm the spec commit is on HEAD.**

```powershell
git log --oneline -3
```

Expected: top commit is `567ceb7 docs(spec): MANUAL.md cleanup — align with %post-driven oscap`. Second commit is the plan (which is what you're reading; that commit lands later via a separate handoff). Third commit is `18ebddc docs(plan): hd:LABEL= oscap transport implementation plan` (the main-branch tip we branched from).

If the plan commit has not yet landed, that's fine — the plan can be committed before or after the implementation starts; what matters is that the spec at `567ceb7` is reachable from HEAD.

- [ ] **Step 3: Confirm working tree clean.**

```powershell
git status --short
```

Expected: empty, or only `?? .claude/`.

- [ ] **Step 4: Confirm baseline CI parity chain green.**

```powershell
ruff check src tests; if ($LASTEXITCODE -ne 0) { throw "ruff check" }
ruff format --check src tests; if ($LASTEXITCODE -ne 0) { throw "ruff format --check" }
mypy; if ($LASTEXITCODE -ne 0) { throw "mypy" }
pytest -q; if ($LASTEXITCODE -ne 0) { throw "pytest" }
```

Expected: all four exit 0. (187 tests + 15 snapshots from the spec commit's baseline — same as the PR #3 branch since this branch was cut from `main` before PR #3 landed.)

---

## Task 2: Apply the 8 MANUAL.md edits

**Files:**
- Modify: `MANUAL.md` (8 disjoint regions)

All eight edits use the `Edit` tool with `replace_all: false` (default). Every `old_string` and `new_string` below is verbatim — copy exactly. If any `old_string` fails to match, stop and report: the file has drifted from what the spec captured.

- [ ] **Step 1: Site 1 — §1 "What ks-gen is" (line 31).**

`old_string`:

```
- **DISA STIG compliant** — most rules are applied by the upstream
  `scap-security-guide` profile (via the `oscap-anaconda-addon`),
  driven by a per-host `tailoring.xml`.
```

`new_string`:

```
- **DISA STIG compliant** — most rules are applied by the upstream
  `scap-security-guide` profile (`oscap xccdf eval --remediate`
  invoked from `%post` at install time), driven by a per-host
  `tailoring.xml`.
```

- [ ] **Step 2: Site 2 — §3.1 bundle-contents table (line 131).**

`old_string`:

```
| `tailoring.xml` | An XCCDF 1.2 tailoring document referenced by `%addon org_fedora_oscap`. | `oscap` during Anaconda's remediation phase. |
```

`new_string`:

```
| `tailoring.xml` | An XCCDF 1.2 tailoring document staged into the target rootfs by a `%post --nochroot` block at install time, then passed to `oscap --tailoring-file`. | `oscap` during the install-time `%post` remediation phase. |
```

- [ ] **Step 3: Site 3 — §3.2 (lines 145-146).**

`old_string`:

```
in v0.1. Everything else is owned by `oscap` remediation via the
`%addon org_fedora_oscap` block.
```

`new_string`:

```
in v0.1. Everything else is owned by `oscap` remediation via a
`%post` block that runs `oscap xccdf eval --remediate` directly.
```

- [ ] **Step 4: Site 4 — §3.3 execution-timeline diagram (around line 160).**

`old_string`:

```
%packages -> %addon org_fedora_oscap [reads tailoring.xml, remediates] -> %post -> reboot
```

`new_string`:

```
%packages
  -> %post --nochroot [stages tailoring.xml]
  -> %post [oscap reads tailoring.xml, remediates]
  -> %post [ks-gen rule overrides]
  -> reboot
```

- [ ] **Step 5: Site 5 — §4.10 packages.required (line 387).** Delete the `oscap-anaconda-addon` line.

`old_string`:

```
    - scap-security-guide
    - openscap-scanner
    - oscap-anaconda-addon
    - aide
```

`new_string`:

```
    - scap-security-guide
    - openscap-scanner
    - aide
```

- [ ] **Step 6: Site 6 — §10 troubleshooting bullet (lines 968-969).** Replace the single stale bullet with four bullets matching the actual current lint error keys.

`old_string`:

```
- **`missing: %addon does not reference tailoring.xml`** — The addon
  block was edited. Regenerate.
```

`new_string`:

```
- **`missing: %post --nochroot oscap fetch block`** — The leading
  `%post --nochroot` block that stages `tailoring.xml` is missing
  or its `--log=` path was hand-edited. Regenerate.
- **`ordering: oscap fetch block must precede oscap eval block`** —
  Something reordered the `%post` blocks; the fetch must run before
  the chrooted oscap eval. Regenerate.
- **`missing: hd:LABEL= branch in oscap fetch case`** — The
  `hd:LABEL=*)` arm of the fetch `case` statement was removed.
  ISO-delivered installs (`inst.ks=hd:LABEL=…`) will hard-fail
  without it. Regenerate.
- **`missing: hd: cp from /run/install/repo in oscap fetch case`** —
  The `hd:LABEL=` arm is present but the `cp /run/install/repo/...`
  line that does the actual staging was edited. Regenerate.
```

- [ ] **Step 7: Site 7 — §10 crypto-policy timing claim (lines 988-990).**

`old_string`:

```
The `%addon org_fedora_oscap` block runs *before* `%post`, so any
`crypto_policy` rule output in `%post` is too late to influence
oscap's view.
```

`new_string`:

```
The oscap remediation `%post` block runs *before* the `ks-gen`
rule-overrides `%post` block, so any `crypto_policy` rule output
in the overrides block is too late to influence oscap's view.
```

- [ ] **Step 8: Site 10 — §10 log-file pointer (line 979).**

`old_string`:

```
Check `/root/ks-post.log` (if you got far enough into `%post`) and
`/tmp/anaconda.log` on the install media or via VNC.
```

`new_string`:

```
Check `/root/ks-post-oscap-fetch.log`, `/root/ks-post-oscap.log`,
and `/root/ks-post.log` (in that order — they correspond to the
fetch / eval / overrides `%post` blocks), and `/tmp/anaconda.log`
on the install media or via VNC.
```

---

## Task 3: Verify the edits and the residual-stale-reference grep

**Files:** none modified

- [ ] **Step 1: Confirm exactly one file changed.**

```powershell
git status --short
git diff --stat
```

Expected: `MANUAL.md` is the only modified file. Untracked `.claude/` is fine. No other files should appear.

- [ ] **Step 2: Spot-check the diff for shape.**

```powershell
git diff MANUAL.md | Select-String -Pattern '^[+-]' | Select-Object -First 80
```

Expected: 8 disjoint hunks corresponding to the 8 sites. No hunks outside §1, §3, §4.10, §10.

- [ ] **Step 3: Confirm no residual `%addon org_fedora_oscap` or `oscap-anaconda-addon` references outside the intentionally-kept §11 glossary and §12 references.**

```powershell
Select-String -Path MANUAL.md -Pattern '%addon org_fedora_oscap', 'oscap-anaconda-addon'
```

Expected: 3 hits, all in §11 (glossary entry) and §12 (references-section link), at approximately lines 1027 (glossary), and 1061 (references). If any hit appears outside §11 / §12, a site was missed — investigate before committing.

Sanity check on the §11 / §12 hits:
```powershell
Select-String -Path MANUAL.md -Pattern '%addon org_fedora_oscap', 'oscap-anaconda-addon' |
  ForEach-Object { "$($_.LineNumber): $($_.Line.Trim())" }
```

Expected lines reference glossary/reference context (e.g., `**\`oscap-anaconda-addon\`** — Anaconda addon that runs \`oscap\`...` and the GitHub URL).

- [ ] **Step 4: Run the full CI parity chain — confirm nothing broke.**

```powershell
ruff check src tests
ruff format --check src tests
mypy
pytest -q
```

Expected: all four clean. (No tests touch MANUAL.md, but the chain catches accidental leakage.)

---

## Task 4: Commit

**Files:** none modified (just commits the staged work)

- [ ] **Step 1: Stage and commit.**

```powershell
git add MANUAL.md
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m @'
docs(manual): align with current %post-driven oscap architecture

Eight stale-architecture sites in MANUAL.md updated to match the
current %post-driven oscap implementation:

  - §1 (line 31): "via the oscap-anaconda-addon" -> "oscap xccdf
    eval --remediate invoked from %post at install time".
  - §3.1 bundle-contents table (line 131): tailoring.xml row now
    describes %post --nochroot staging + oscap --tailoring-file
    consumption.
  - §3.2 (lines 145-146): oscap ownership now attributed to a %post
    block, not the dropped %addon org_fedora_oscap.
  - §3.3 execution-timeline diagram (line 160): single-line addon
    timeline replaced with a four-line vertical form showing the
    three %post blocks (fetch / eval / overrides).
  - §4.10 packages.required example (line 387): removed
    "oscap-anaconda-addon" — package is not in
    src/ks_gen/config.py:148-160 defaults (a real doc-vs-code bug).
  - §10 troubleshooting (lines 968-969): one stale bullet
    referencing a lint error key that no longer exists, replaced
    with four bullets matching the actual current oscap-related
    lint keys (fetch-block presence, ordering, hd:LABEL= arm, hd:
    cp line).
  - §10 (lines 988-990): crypto-policy timing claim corrected to
    describe the new (oscap %post before overrides %post) ordering
    rather than the dropped addon-before-%post one.
  - §10 (line 979): log-file pointer now mentions all three /root/
    logs the install writes (fetch / eval / overrides).

Glossary entry (§11) and references-section link (§12) intentionally
remain as historical/educational context — see the spec's Non-goals.

Surfaced by the final-branch review of PR #3 (commit ffb1e4e).

Refs: docs/superpowers/specs/2026-06-06-manual-addon-cleanup-design.md
'@
```

- [ ] **Step 2: Verify the commit landed signed.**

```powershell
git log -1 --show-signature
```

Expected: subject line `docs(manual): align with current %post-driven oscap architecture`, `gpg: Good signature from "Patrick Connallon (SupremeCommanderHedgehog)"`, key fingerprint ending `BE707B220C995478` (full: `5741F291946EBD4A8B698BA1BE707B220C995478`).

---

## Task 5: Final verification

**Files:** none modified

- [ ] **Step 1: One more CI parity chain pass.**

```powershell
ruff check src tests
ruff format --check src tests
mypy
pytest -q
```

Expected: all four exit 0.

- [ ] **Step 2: Branch shape check.**

```powershell
git log --oneline 18ebddc..HEAD
git log --show-signature 18ebddc..HEAD 2>&1 | Select-String '^(commit|gpg: )'
```

Expected: two commits on this branch above `main` — `567ceb7 docs(spec)` and the new `docs(manual)` commit. Both signed.

- [ ] **Step 3: Report.**

Report to the user: implementation complete on branch `impl/v0.2.0-manual-cleanup`. One implementation commit added on top of the spec commit `567ceb7`, both signed. Local CI chain clean. Do NOT push, do NOT open the PR, and do NOT manually trigger the GitHub Backup scheduled task. The user will direct push / PR creation.
