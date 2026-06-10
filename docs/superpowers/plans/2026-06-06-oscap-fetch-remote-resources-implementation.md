# `--fetch-remote-resources` on install-time oscap — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--fetch-remote-resources` to the chrooted `oscap xccdf eval --remediate` invocation in the kickstart template so install-time STIG evaluation pulls the AlmaLinux OVAL CVE feed instead of silently skipping OVAL-dependent rules. Closes the last v0.1-era gap.

**Architecture:** One-line edit to `src/ks_gen/templates/ks.cfg.j2` — append `--fetch-remote-resources` between the `--profile` and `--tailoring-file` arguments of the existing chrooted oscap eval block. Add one lint invariant in `src/ks_gen/lint.py` so the flag's presence is checked the same way the post-PR-#3 fetch/eval-split invariants are checked. Tighten existing skeleton tests to require the flag. Regenerate golden snapshots. Update CHANGELOG and MANUAL §10 (troubleshooting) for the expected fetch-failure log line on air-gapped (`hd:LABEL=`) installs.

**Tech Stack:** Jinja2 templates, Python 3.11+, `pytest` + `syrupy` for golden snapshot tests, `pykickstart` for ksvalidator, ruff + mypy --strict for CI.

**Companion spec:** `docs/superpowers/specs/2026-06-06-oscap-fetch-remote-resources-design.md` (commit `c0267d3`)

**Repo conventions to honor:**
- Conventional Commits (`feat:`, `test:`, `docs:`, `style:`, etc.)
- Every commit signed with the user's GPG key `BE707B220C995478`. Use the explicit form: `git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "..."`.
- Before any `git push` (this plan does NOT push — that's the user's call), run the full local CI parity chain: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`. Per `CLAUDE.md`: `ruff check` alone misses formatting drift.
- Golden snapshots live at `tests/golden/__snapshots__/*.ambr`. Regenerate with `pytest tests/golden/ --snapshot-update`. **Inspect the diff before committing** — a regen should change exactly what the template change predicts and nothing else (one added line per rendered ks.cfg).
- Never invoke any `Start-ScheduledTask` for the "GitHub Backup" task. Don't push without explicit user instruction.

---

## File Structure

**Files modified:**
- `src/ks_gen/templates/ks.cfg.j2` — append `--fetch-remote-resources \` line in the chrooted oscap eval block (current lines 76-81).
- `src/ks_gen/lint.py` — extend `_internal_checks` with one new invariant: chrooted oscap eval block must contain `--fetch-remote-resources`.
- `tests/test_lint.py` — add one negative test for the new invariant.
- `tests/test_skeleton.py` — extend `test_skeleton_emits_oscap_post_block` to assert the flag is present in the eval body.
- `tests/golden/__snapshots__/test_minimal_dhcp.ambr` — regenerated.
- `tests/golden/__snapshots__/test_modern_crypto.ambr` — regenerated.
- `tests/golden/__snapshots__/test_stig_strict.ambr` — regenerated.
- `tests/golden/__snapshots__/test_bare_metal_usbguard.ambr` — regenerated.
- `tests/golden/__snapshots__/test_unattended_disabled.ambr` — regenerated.
- `CHANGELOG.md` — add a bullet under `### Added` of `[Unreleased]`.
- `MANUAL.md` — two surgical edits in §10 (troubleshooting): a new short subsection on the expected `hd:LABEL=` fetch-failure log line, plus one new entry in the lint-failures list for `--fetch-remote-resources`.

**Files created:** none beyond this plan and the (already-committed) spec.

**Files NOT modified:**
- `src/ks_gen/iso.py` — no ISO content changes.
- Rule files in `src/ks_gen/rules/` — no rule logic touches this.
- `MANUAL.md` §3 architecture: timeline diagram remains correct; the flag is internal to the eval block.
- `README.md`, `MINIMAL-TEST.md` — operator-facing surfaces unchanged for the common path.

---

## Task 1: Baseline — confirm clean starting state

**Files:** none modified

You should already be on branch `impl/v0.2.1-oscap-fetch-remote` (created when the spec was committed at `c0267d3`).

- [ ] **Step 1: Confirm branch and working tree are clean.**

Run from repo root (`<repo-root>`):

```powershell
git branch --show-current
git status -uno
```

Expected: branch is `impl/v0.2.1-oscap-fetch-remote`, status is `nothing to commit`.

- [ ] **Step 2: Run the full CI parity chain to establish a known-green baseline.**

```powershell
ruff check src tests; if ($LASTEXITCODE -ne 0) { throw "ruff check" }
ruff format --check src tests; if ($LASTEXITCODE -ne 0) { throw "ruff format --check" }
mypy; if ($LASTEXITCODE -ne 0) { throw "mypy" }
pytest -q; if ($LASTEXITCODE -ne 0) { throw "pytest" }
```

Expected: all four pass cleanly. If any fails, stop and report — that's a pre-existing problem to address before this work.

---

## Task 2: TDD red — extend the skeleton test to require the flag

**Files:**
- Modify: `tests/test_skeleton.py:52-99` (the existing `test_skeleton_emits_oscap_post_block` function)

We add an assertion that fails today, then make it pass in Task 3 by editing the template. This keeps each commit self-contained and provably TDD-shaped.

- [ ] **Step 1: Add the assertion.**

In `tests/test_skeleton.py`, locate the eval-block checks section (currently around lines 87-99, between `# Eval block checks: oscap remediation` and the `oscap_body.count("%end") == 2` assertion).

Add this assertion immediately after the existing `oscap xccdf eval --remediate` assertion:

```python
    assert "--fetch-remote-resources" in eval_body, (
        "oscap eval must fetch remote OVAL resources at install time"
    )
```

So the relevant block looks like:

```python
    # Eval block checks: oscap remediation
    assert "set -euo pipefail" in eval_body, "missing strict shell flags in eval block"
    assert "head -c 5 /root/tailoring.xml | grep -q '<?xml'" in eval_body, (
        "missing xml sentinel check in eval block"
    )
    assert "oscap xccdf eval --remediate" in eval_body, "missing oscap remediation invocation"
    assert "--fetch-remote-resources" in eval_body, (
        "oscap eval must fetch remote OVAL resources at install time"
    )
    assert "--tailoring-file /root/tailoring.xml" in eval_body, (
        "oscap must consume the fetched tailoring"
    )
```

- [ ] **Step 2: Run the test to verify it fails.**

```powershell
pytest tests/test_skeleton.py::test_skeleton_emits_oscap_post_block -v
```

Expected: FAIL with `AssertionError: oscap eval must fetch remote OVAL resources at install time`.

Do NOT commit this failing test on its own — TDD red → green within a single commit. Move to Task 3.

---

## Task 3: TDD green — add `--fetch-remote-resources` to the template

**Files:**
- Modify: `src/ks_gen/templates/ks.cfg.j2:76-81` (the chrooted oscap eval invocation)

- [ ] **Step 1: Edit the template.**

Locate the chrooted oscap eval invocation. Today it reads:

```
oscap xccdf eval --remediate \
  --profile xccdf_org.ssgproject.content_profile_{{ cfg.meta.profile }} \
  --tailoring-file /root/tailoring.xml \
  --results-arf /root/oscap-remediation-results.xml \
  --report /root/oscap-remediation-report.html \
  /usr/share/xml/scap/ssg/content/{{ cfg.meta.scap_content }} || true
```

Insert one new line between the `--profile` line and the `--tailoring-file` line, matching the surrounding 2-space indentation and trailing `\` style:

```
oscap xccdf eval --remediate \
  --profile xccdf_org.ssgproject.content_profile_{{ cfg.meta.profile }} \
  --fetch-remote-resources \
  --tailoring-file /root/tailoring.xml \
  --results-arf /root/oscap-remediation-results.xml \
  --report /root/oscap-remediation-report.html \
  /usr/share/xml/scap/ssg/content/{{ cfg.meta.scap_content }} || true
```

That is the ENTIRE template change. Nothing else moves.

- [ ] **Step 2: Run the skeleton test to verify it now passes.**

```powershell
pytest tests/test_skeleton.py::test_skeleton_emits_oscap_post_block -v
```

Expected: PASS.

- [ ] **Step 3: Run the full skeleton test file — should still all pass.**

```powershell
pytest tests/test_skeleton.py -v
```

Expected: all tests in `test_skeleton.py` pass.

- [ ] **Step 4: Run the golden tests — they will fail (snapshots out of date).**

```powershell
pytest tests/golden/ -v
```

Expected: 5 snapshot tests FAIL with a one-line diff each (the new `--fetch-remote-resources \` line appearing in the rendered ks.cfg). This is the expected failure shape — confirm the diff IS just that one inserted line in each ks.cfg snapshot.

If any snapshot diff shows changes OTHER than the new `--fetch-remote-resources \` line in the oscap eval block, STOP — that means the template edit accidentally changed something else.

---

## Task 4: Regenerate golden snapshots

**Files:**
- Modify: `tests/golden/__snapshots__/test_minimal_dhcp.ambr`
- Modify: `tests/golden/__snapshots__/test_modern_crypto.ambr`
- Modify: `tests/golden/__snapshots__/test_stig_strict.ambr`
- Modify: `tests/golden/__snapshots__/test_bare_metal_usbguard.ambr`
- Modify: `tests/golden/__snapshots__/test_unattended_disabled.ambr`

- [ ] **Step 1: Regenerate snapshots.**

```powershell
pytest tests/golden/ --snapshot-update
```

Expected: 5 snapshots updated.

- [ ] **Step 2: Inspect the diff — this is the critical safety step.**

```powershell
git diff tests/golden/__snapshots__/
```

Expected: the ONLY change in each `.ambr` snapshot is the addition of one line — `  --fetch-remote-resources \` — inside the chrooted oscap eval invocation, between `--profile ...` and `--tailoring-file ...`. No other content moves.

If any other change appears (line reflows, byte-equal but order-shuffled blocks, mtime artifacts, etc.), STOP and investigate before proceeding. A "regen should change exactly what the rule change predicts and nothing else" — per `CLAUDE.md`.

- [ ] **Step 3: Re-run all tests to verify green.**

```powershell
pytest -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit the template change + test tightening + regenerated snapshots together.**

```powershell
git add src/ks_gen/templates/ks.cfg.j2 tests/test_skeleton.py tests/golden/__snapshots__/
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m @'
feat(template): pass --fetch-remote-resources to install-time oscap eval

The chrooted oscap xccdf eval invocation now fetches remote OVAL
resources, so STIG rules tied to the AlmaLinux OVAL CVE feed
(security.almalinux.org/oval/org.almalinux.alsa-9.xml.bz2) run at
install time instead of silently skipping.

Air-gapped (hd:LABEL=) installs will see the fetch fail in the log;
the eval invocation is wrapped in `|| true`, so the install still
completes and OVAL-dependent rules skip the same way they do today.
That coverage gap is documented in MANUAL.md §10.

Tightens test_skeleton_emits_oscap_post_block to require the flag.
Regenerates golden snapshots — diff is one inserted line per rendered
ks.cfg, inside the eval block, and nothing else.

Closes the last v0.1-era gap. Targets v0.2.1.
'@
```

Note: the heredoc uses single-quoted `@'...'@` PowerShell syntax with the closing `'@` at column 0 on its own line.

Expected: signed commit succeeds.

---

## Task 5: TDD red — failing lint test for the new invariant

**Files:**
- Modify: `tests/test_lint.py` (append a new test after the existing `test_lint_detects_missing_hd_cp_line` at the end of the file)

- [ ] **Step 1: Add the negative test.**

Append this at the end of `tests/test_lint.py`:

```python
def test_lint_detects_missing_fetch_remote_resources(tmp_path):
    out = _generate(tmp_path)
    ks = out / "ks.cfg"
    text = ks.read_text(encoding="utf-8")
    # Delete the --fetch-remote-resources continuation line so the eval
    # invocation no longer pulls OVAL CVE feeds at install time.
    text = text.replace(
        "  --fetch-remote-resources \\\n",
        "",
    )
    ks.write_text(text, encoding="utf-8")
    report = lint_kickstart(ks)
    assert not report.ok
    assert any("--fetch-remote-resources" in f for f in report.failures)
```

The replacement string `"  --fetch-remote-resources \\\n"` matches the rendered line (two-space indent + flag + backslash + newline). Inside the Python source, `\\\n` is the two characters `\` then newline.

- [ ] **Step 2: Run the new test to verify it fails.**

```powershell
pytest tests/test_lint.py::test_lint_detects_missing_fetch_remote_resources -v
```

Expected: FAIL — `lint_kickstart` returns `ok=True` because the new invariant hasn't been added yet. The assertion `assert not report.ok` fails.

Do NOT commit yet — TDD red → green within a single commit. Proceed to Task 6.

---

## Task 6: TDD green — add the lint invariant

**Files:**
- Modify: `src/ks_gen/lint.py:27-65` (the `_internal_checks` function)

- [ ] **Step 1: Add the invariant.**

In `src/ks_gen/lint.py`, locate the existing `oscap_idx`-scoped checks (currently lines 47-51):

```python
    else:
        if "oscap xccdf eval --remediate" not in text[oscap_idx:]:
            failures.append("missing: oscap remediation invocation in %post oscap block")
        if "--tailoring-file /root/tailoring.xml" not in text[oscap_idx:]:
            failures.append("missing: --tailoring-file reference in %post oscap block")
```

Add one new check inside the same `else` branch (so it only runs when the eval block was found):

```python
    else:
        if "oscap xccdf eval --remediate" not in text[oscap_idx:]:
            failures.append("missing: oscap remediation invocation in %post oscap block")
        if "--tailoring-file /root/tailoring.xml" not in text[oscap_idx:]:
            failures.append("missing: --tailoring-file reference in %post oscap block")
        if "--fetch-remote-resources" not in text[oscap_idx:]:
            failures.append("missing: --fetch-remote-resources flag in %post oscap block")
```

Rationale for scoping by `text[oscap_idx:]`: matches the existing two checks above it, so the flag is required *inside* the chrooted eval block, not anywhere else in the file. (This avoids a future false positive if `--fetch-remote-resources` ever appears in a comment elsewhere.)

- [ ] **Step 2: Run the new lint test to verify it passes.**

```powershell
pytest tests/test_lint.py::test_lint_detects_missing_fetch_remote_resources -v
```

Expected: PASS.

- [ ] **Step 3: Run the full lint test file to confirm no regressions.**

```powershell
pytest tests/test_lint.py -v
```

Expected: all lint tests pass, including the existing `test_lint_accepts_known_good` (the freshly generated bundle now includes the flag because Task 3's template change is in place).

- [ ] **Step 4: Run the full test suite.**

```powershell
pytest -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit lint change + test together.**

```powershell
git add src/ks_gen/lint.py tests/test_lint.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m @'
feat(lint): guard --fetch-remote-resources in oscap eval block

Adds a load-bearing invariant to _internal_checks: the chrooted
oscap %post block must contain --fetch-remote-resources. Same
pattern as the three invariants PR #3 added for the fetch/eval
split — a refactor that drops the flag silently is now CI-loud
instead of CI-quiet.

Scoped to text[oscap_idx:] so the check fires only inside the
eval block and not against incidental occurrences elsewhere.

RED-phase negative test in tests/test_lint.py.
'@
```

Expected: signed commit succeeds.

---

## Task 7: Documentation updates

**Files:**
- Modify: `CHANGELOG.md` — add bullet under `### Added` of `[Unreleased]`
- Modify: `MANUAL.md` §10 troubleshooting — add new subsection + new lint-failure entry

- [ ] **Step 1: CHANGELOG entry.**

Open `CHANGELOG.md`. Locate the `## [Unreleased]` heading and its `### Added` section (currently the first bullet under it is the `hd:LABEL=` transport addition).

Add a new bullet at the top of `### Added` (most recent first):

```markdown
- **`--fetch-remote-resources` on install-time oscap eval.** The
  chrooted `oscap xccdf eval --remediate` invocation now passes
  `--fetch-remote-resources`, so STIG rules whose OVAL definitions
  reference the AlmaLinux CVE feed
  (`security.almalinux.org/oval/org.almalinux.alsa-9.xml.bz2`) run
  at install time instead of silently skipping. Air-gapped
  (`hd:LABEL=`) installs will log a failed fetch but complete
  normally; OVAL-dependent rules skip cleanly. See MANUAL.md §10.
  Closes the last v0.1-era gap. Lint guards the flag's presence.
```

- [ ] **Step 2: MANUAL.md §10 — new lint-failure entry.**

Open `MANUAL.md`. Locate the `### "ks-gen lint failed on my ks.cfg"` subsection (around line 961). Find the list of lint failures (currently 7 bullets ending with the `ksvalidator: ...` entry).

Add this new bullet immediately before the `ksvalidator: ...` entry, so it sits with the other oscap-block lint failures:

```markdown
- **`missing: --fetch-remote-resources flag in %post oscap block`** —
  The chrooted `oscap xccdf eval` invocation is missing the
  `--fetch-remote-resources` argument. Without it, STIG rules tied
  to the AlmaLinux OVAL CVE feed silently skip at install time.
  Regenerate.
```

- [ ] **Step 3: MANUAL.md §10 — new subsection on the expected hd:LABEL= fetch-failure log line.**

In the same `## 10. Troubleshooting` section, find the `### "oscap remediation failed during install"` subsection (around line 992).

Add this new subsection IMMEDIATELY AFTER that one (so it appears in the natural reading order: general oscap failures → specific air-gap log line):

```markdown
### "I see a fetch failure for security.almalinux.org in the oscap log on an ISO install"

Expected. The install-time `oscap xccdf eval` invocation passes
`--fetch-remote-resources` so STIG rules whose OVAL definitions
reference the AlmaLinux CVE feed at
`https://security.almalinux.org/oval/org.almalinux.alsa-9.xml.bz2`
can run. On an ISO-delivered (`hd:LABEL=`) install with no
install-time network access, that fetch fails — the eval wrapper
`|| true` swallows the non-zero exit, the install completes, and
the affected OVAL-dependent rules skip the same way they did in
v0.1.

If you need CVE-tied coverage on an air-gapped install, the rules
fire on the first post-install run against an updated SSG content
package — there is no installer-side workaround in v0.2.

If the failed fetch appears on an install that DOES have network
access (HTTP delivery, working DNS, no egress filtering of
`security.almalinux.org`), that's a real problem worth
investigating: check `/etc/resolv.conf`, the host firewall, and
any upstream proxy configuration.
```

- [ ] **Step 4: Sanity check the docs.**

```powershell
git diff --stat CHANGELOG.md MANUAL.md
```

Expected: both files modified, additions only (no incidental deletions).

```powershell
git diff CHANGELOG.md MANUAL.md
```

Read the diff. Verify exactly the three edits above and nothing else.

- [ ] **Step 5: Run the full CI parity chain — docs commits still need lint/format clean.**

```powershell
ruff check src tests; if ($LASTEXITCODE -ne 0) { throw "ruff check" }
ruff format --check src tests; if ($LASTEXITCODE -ne 0) { throw "ruff format --check" }
mypy; if ($LASTEXITCODE -ne 0) { throw "mypy" }
pytest -q; if ($LASTEXITCODE -ne 0) { throw "pytest" }
```

Expected: all four pass.

- [ ] **Step 6: Commit the docs.**

```powershell
git add CHANGELOG.md MANUAL.md
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m @'
docs: --fetch-remote-resources flag + air-gap troubleshooting

CHANGELOG: new [Unreleased]/Added bullet documenting the flag and
the air-gap log-line behavior.

MANUAL §10: new lint-failure entry for the
`missing: --fetch-remote-resources flag` message; new
troubleshooting subsection on the expected fetch failure to
security.almalinux.org on hd:LABEL= installs, with guidance for
distinguishing expected vs. unexpected failure modes.
'@
```

Expected: signed commit succeeds.

---

## Task 8: Final CI parity sweep and branch summary

**Files:** none modified

- [ ] **Step 1: One more full CI run on the integrated branch.**

```powershell
ruff check src tests; if ($LASTEXITCODE -ne 0) { throw "ruff check" }
ruff format --check src tests; if ($LASTEXITCODE -ne 0) { throw "ruff format --check" }
mypy; if ($LASTEXITCODE -ne 0) { throw "mypy" }
pytest -q; if ($LASTEXITCODE -ne 0) { throw "pytest" }
```

Expected: all four pass.

- [ ] **Step 2: Inspect the branch's commit log.**

```powershell
git log --oneline main..HEAD
```

Expected: four commits since `main`:

```
<sha>  docs: --fetch-remote-resources flag + air-gap troubleshooting
<sha>  feat(lint): guard --fetch-remote-resources in oscap eval block
<sha>  feat(template): pass --fetch-remote-resources to install-time oscap eval
c0267d3 docs(spec): --fetch-remote-resources for install-time oscap
```

(SHAs other than `c0267d3` will differ — that one is the already-committed spec.)

- [ ] **Step 3: Verify each commit is signed.**

```powershell
git log --show-signature main..HEAD --pretty=format:"%h %s%n" 2>&1 | Select-String -Pattern "Good signature|<sha>"
```

Or more simply:

```powershell
git log --pretty=format:"%h %G? %s" main..HEAD
```

Expected: every commit shows `G` in the signature column (good GPG signature with key `BE707B220C995478`).

- [ ] **Step 4: Stop and hand off to the user.**

Do NOT push, do NOT open a PR, do NOT tag — those are the user's call. Tell the user the branch is ready: four signed commits on `impl/v0.2.1-oscap-fetch-remote`, full local CI green, and they can review then decide on push / PR / direct merge / tag flow as they did for v0.2.0.

---

## Self-review notes (for the engineer executing this plan)

If you find any of the following, STOP and surface it to the user before continuing:

1. **Snapshot diff shows anything other than one inserted line per ks.cfg.** Investigate before regenerating again.
2. **`test_lint_accepts_known_good` fails after Task 6.** The flag is in the template (Task 3) but missing from a particular snapshot, or `_generate` is producing different output than the snapshots — that's a real regression.
3. **`ruff format --check` fails on a Python edit** (test_lint, lint.py, test_skeleton). Run `ruff format src tests` to fix, verify with `--check`, then amend or follow up with a `style:` commit per `CLAUDE.md` guidance.
4. **`mypy` fails on the lint edit.** The new check is a string `in` test with no new types, so this would be a surprise — surface it.
5. **A second `[Unreleased]` heading appears in CHANGELOG.md.** Only one should exist; add to the existing one.
