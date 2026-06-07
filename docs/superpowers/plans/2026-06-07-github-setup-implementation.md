# GitHub setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configure every GitHub-side surface for `SupremeCommanderHedgehog/ks-gen` to be production-grade and public-ready, in two PRs: PR-A (foundation: docs, templates, label retag, CI hardening, branch ruleset with owner bypass) then PR-B (automation: Project v2 workflows, Dependabot, dormant CodeQL, SBOM, release-please).

**Architecture:** Config-as-code where possible (YAML/JSON files in `.github/`), `gh api` for repository-level settings, documented manual steps for browser-only actions (Project v2 creation, PAT generation, GitHub Release creation). No new Python code; existing `pyproject.toml` gets metadata fields. CI hardening is in-place on the existing `ci.yml`.

**Tech Stack:** GitHub Actions workflows (YAML), GitHub Issue Forms (YAML), GitHub repository rulesets (JSON via REST), `gh` CLI, release-please-action v4, Dependabot v2, CodeQL action v3, CycloneDX SBOM, pre-commit, step-security/harden-runner.

**Spec:** `docs/superpowers/specs/2026-06-07-github-setup-design.md`

**Conventions and prerequisites (read before starting):**

- Project CLAUDE.md mandates the full CI chain before claiming green:
  `ruff check src tests && ruff format --check src tests && mypy && pytest -q`.
  After every Python/config change that affects testing, run the chain.
- Commits are conventional-commits style. Sign every commit with the
  user's GPG key:
  `git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "..."`.
  Do **not** add `Co-Authored-By:` trailers.
- `gh` CLI must be authenticated (`gh auth status` should pass).
- Some tasks have user-action checkpoints (PAT creation, browser-only
  project setup). Stop at those and prompt the user; do not try to
  automate browser actions.
- When pinning action SHAs, look up the SHA at the latest tagged release:
  `gh api repos/<owner>/<repo>/git/ref/tags/<tag> --jq .object.sha`.
  Always include the human-readable version as a trailing comment.
- Do NOT enable the `pull_request` rule on the main ruleset in PR-A.
  That happens in the going-public runbook (§11 of the spec).

---

## Phase A — Foundation (PR-A)

### Task A1: Create the feature branch

**Files:** none (git ops only).

- [ ] **Step 1: Confirm clean state and current HEAD**

Run:
```
git status
git rev-parse HEAD
```
Expected: `On branch main`, working tree clean (untracked `.claude/` is
fine), HEAD at `e26d3cd` (the spec commit) or later.

- [ ] **Step 2: Create and check out the feature branch**

Run:
```
git checkout -b impl/github-setup-foundation
```

---

### Task A2: SECURITY.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md

**Files:**
- Create: `SECURITY.md`
- Create: `CONTRIBUTING.md`
- Create: `CODE_OF_CONDUCT.md`

- [ ] **Step 1: Resolve the public security email**

Ask the user which email address to publish as the security contact in
`SECURITY.md`. The default suggestion is
`github.v5f9w@bitbucket.onl` (matches the GPG uid), but the user may
prefer a dedicated address. Wait for an answer before writing the file.

- [ ] **Step 2: Write `SECURITY.md`**

Use the contact email from Step 1 in the `<security-email>` slot below.

```markdown
# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.3.x   | yes       |
| < 0.3   | no        |

## Reporting a vulnerability

Please use **GitHub's private vulnerability reporting** for new reports:

  https://github.com/SupremeCommanderHedgehog/ks-gen/security/advisories/new

For out-of-band contact, email **<security-email>** (PGP fingerprint
`5741F291946EBD4A8B698BA1BE707B220C995478`). Do **not** open a public
issue for security problems.

Expect an initial response within 5 business days. Once a fix lands,
we will coordinate disclosure timing with you before publishing.

## Release attestation

Tags through `v0.3.0` are GPG-signed by the maintainer. From `v0.3.1`
forward, releases are automated via `release-please`; tags are
GitHub-attested (TLS + signed merge commits) rather than GPG-signed.
The release commit on `main` continues to be GPG-signed.

## Secret scanning

Once this repository is public, GitHub secret scanning and push
protection are enabled. Until then, the maintainer relies on local
pre-commit hooks and Dependabot for supply-chain coverage.
```

- [ ] **Step 3: Write `CONTRIBUTING.md`**

```markdown
# Contributing to ks-gen

Thanks for the interest! This project is a generator of remote-safe
DISA STIG kickstart files for AlmaLinux 9. Please read this whole
document before opening a PR.

## Development environment

Python 3.11+ is required. From a clean checkout:

```bash
python -m venv .venv
source .venv/bin/activate    # or .venv\Scripts\Activate.ps1 on Windows
pip install -e ".[dev]"
pre-commit install            # installs the local hook chain
```

## CI parity check — run before pushing

The CI workflow runs four commands in this order:

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Run this chain locally before claiming "lint clean" / "ready for PR"
/ "tests green" and before `git push`. Running only `ruff check`
misses formatting drift — `ruff format --check` is a separate check.

If `ruff format --check` fails, fix with `ruff format src tests`,
verify with `--check` again, then commit as `style:`.

## Snapshot tests

Golden snapshots use `syrupy` and live at `tests/__snapshots__/` and
`tests/golden/__snapshots__/`. Regenerate after intentional output
changes:

```bash
pytest tests/golden/ --snapshot-update
pytest tests/test_verify_report.py --snapshot-update
```

Inspect the diff before committing — a regeneration should change
exactly what the rule change predicts and nothing else.

## Commit messages

Conventional Commits:

- `feat:` — user-facing functional change.
- `fix:` — bug fix.
- `docs:` — documentation only.
- `refactor:` — restructuring without behavior change.
- `test:` — tests added/changed without behavior change.
- `style:` — formatting only (white-space, lint fixes).
- `chore:` — tooling, deps, build, CI changes.
- `ci:` — CI-config-only changes.

Subject line under 72 characters. Body wrapped at 72 columns. End with
a blank line; do not append `Co-Authored-By:` trailers.

Every commit on `main` is GPG-signed. Use `git commit -S`. If you do not
yet have a GPG key, ask the maintainer for guidance before opening a
non-trivial PR.

## Branch naming

`impl/v<version>-<topic>` for release-impacting work
(e.g. `impl/v0.4.0-disk-layout`). For short-lived branches off main
unrelated to a release, `chore/<topic>` or `docs/<topic>` is fine.

## Pull requests

- Open one PR per logical change. Avoid bundling unrelated commits.
- Fill out the PR template completely (run the CI parity check
  locally, paste the result).
- Reference the issue you close with `Closes #N` in the PR body.
- Wait for CI to pass before requesting review.

## Good first issues

Issues tagged `good-first-issue` are reviewed for clear scope and
self-contained implementation. Start there if you're new to the
codebase.

## Code of conduct

Participation is governed by `CODE_OF_CONDUCT.md`.
```

- [ ] **Step 4: Write `CODE_OF_CONDUCT.md`**

Copy the Contributor Covenant v2.1 verbatim from
https://www.contributor-covenant.org/version/2/1/code_of_conduct/code_of_conduct.md
into `CODE_OF_CONDUCT.md`. Replace the literal
`[INSERT CONTACT METHOD]` token near the end with the security email
from Task A2 Step 1 (same address — it's the same channel for both
security and conduct reports).

- [ ] **Step 5: Run the CI chain (no Python changed, but be sure)**

```
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```
Expected: clean (these are docs-only changes).

- [ ] **Step 6: Commit**

```
git add SECURITY.md CONTRIBUTING.md CODE_OF_CONDUCT.md
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "docs: add SECURITY, CONTRIBUTING, CODE_OF_CONDUCT

Public-readiness docs: security policy + private vulnerability
reporting pointer, contributor setup + CI parity + commit conventions,
Contributor Covenant v2.1.

Part of github-setup PR-A. See docs/superpowers/specs/2026-06-07-github-setup-design.md."
```

---

### Task A3: README badges and top-of-file polish

**Files:**
- Modify: `README.md` (top of file only)

- [ ] **Step 1: Read the current top of `README.md`**

Use the Read tool on `README.md` lines 1–10 to confirm the current
title `# ks-gen — remote-safe DISA STIG kickstart generator for AlmaLinux 9`
and the next paragraph.

- [ ] **Step 2: Insert a badge block immediately after the H1**

After line 1 (the title), insert a blank line, then this badge block,
then another blank line before the existing first prose paragraph:

```markdown
[![ci](https://github.com/SupremeCommanderHedgehog/ks-gen/actions/workflows/ci.yml/badge.svg)](https://github.com/SupremeCommanderHedgehog/ks-gen/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](https://pypi.org/project/ks-gen/)
[![Latest release](https://img.shields.io/github/v/release/SupremeCommanderHedgehog/ks-gen?display_name=tag&sort=semver)](https://github.com/SupremeCommanderHedgehog/ks-gen/releases/latest)
[![Open issues](https://img.shields.io/github/issues/SupremeCommanderHedgehog/ks-gen)](https://github.com/SupremeCommanderHedgehog/ks-gen/issues)
```

The `Latest release` badge will show "no releases" until release-please
publishes the first one in PR-B; that is expected and fine.

- [ ] **Step 3: Commit**

```
git add README.md
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "docs(readme): add CI, license, Python, release, issues badges

Standard discoverability badges at the top of README. The 'Latest
release' badge stays blank until release-please publishes the first
release in PR-B."
```

---

### Task A4: pyproject.toml metadata

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Read the existing `[project]` block in `pyproject.toml`**

Use the Read tool. The current block (per the brainstorming exploration)
includes `name`, `version`, `requires-python`, `description`, `authors`,
`license`, `dependencies`. Confirm these exist.

- [ ] **Step 2: Extend `[project]` with `keywords` and `classifiers`**

Add the following two assignments inside the `[project]` block,
immediately after the existing `dependencies = [...]` array. Preserve
existing whitespace/indentation conventions in the file.

```toml
keywords = [
  "kickstart",
  "almalinux",
  "stig",
  "disa",
  "oscap",
  "scap",
  "compliance",
  "security-hardening",
]
classifiers = [
  "Development Status :: 4 - Beta",
  "Environment :: Console",
  "Intended Audience :: System Administrators",
  "License :: OSI Approved :: Apache Software License",
  "Operating System :: POSIX :: Linux",
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Programming Language :: Python :: 3.13",
  "Topic :: System :: Installation/Setup",
  "Topic :: System :: Systems Administration",
]
```

- [ ] **Step 3: Add a `[project.urls]` table immediately after `[project]`**

```toml
[project.urls]
Homepage      = "https://github.com/SupremeCommanderHedgehog/ks-gen"
Documentation = "https://github.com/SupremeCommanderHedgehog/ks-gen/blob/main/MANUAL.md"
Issues        = "https://github.com/SupremeCommanderHedgehog/ks-gen/issues"
Changelog     = "https://github.com/SupremeCommanderHedgehog/ks-gen/blob/main/CHANGELOG.md"
Source        = "https://github.com/SupremeCommanderHedgehog/ks-gen"
```

- [ ] **Step 4: Run the CI chain**

```
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```
Expected: clean. The metadata fields don't affect Python imports.

- [ ] **Step 5: Commit**

```
git add pyproject.toml
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "chore(pyproject): add keywords, classifiers, project URLs

Discoverability metadata for PyPI and GitHub. No runtime impact."
```

---

### Task A5: Repository-level settings via `gh api`

**Files:** none (remote settings only). Verification via `gh api`.

- [ ] **Step 1: Set description, homepage, has_wiki, has_discussions, delete_branch_on_merge**

```
gh api -X PATCH repos/SupremeCommanderHedgehog/ks-gen \
  -f description='Remote-safe DISA STIG kickstart generator for AlmaLinux 9' \
  -F has_wiki=false \
  -F has_discussions=true \
  -F delete_branch_on_merge=true
```

Verify:
```
gh repo view SupremeCommanderHedgehog/ks-gen --json description,hasWikiEnabled,hasDiscussionsEnabled,deleteBranchOnMerge
```
Expected:
```
{
  "deleteBranchOnMerge": true,
  "description": "Remote-safe DISA STIG kickstart generator for AlmaLinux 9",
  "hasDiscussionsEnabled": true,
  "hasWikiEnabled": false
}
```

- [ ] **Step 2: Set repository topics**

```
gh api -X PUT repos/SupremeCommanderHedgehog/ks-gen/topics \
  -f 'names[]=kickstart' \
  -f 'names[]=almalinux' \
  -f 'names[]=stig' \
  -f 'names[]=oscap' \
  -f 'names[]=compliance' \
  -f 'names[]=disa' \
  -f 'names[]=python' \
  -f 'names[]=security-hardening'
```

Verify:
```
gh api repos/SupremeCommanderHedgehog/ks-gen/topics
```

- [ ] **Step 3: Enable private vulnerability reporting**

```
gh api -X PUT repos/SupremeCommanderHedgehog/ks-gen/private-vulnerability-reporting
```

Verify:
```
gh api repos/SupremeCommanderHedgehog/ks-gen/private-vulnerability-reporting
```
Expected: `{"enabled":true}`.

- [ ] **Step 4: Record evidence in the PR description (later)**

Note the output of each `gh api` verification. These commands changed
remote state, not files in the repo, so the evidence belongs in the
PR description for PR-A so a reviewer can see what changed.

(No commit for this task — remote-only changes.)

---

### Task A6: Issue forms and PR template

**Files:**
- Create: `.github/ISSUE_TEMPLATE/bug_report.yml`
- Create: `.github/ISSUE_TEMPLATE/feature_request.yml`
- Create: `.github/ISSUE_TEMPLATE/documentation.yml`
- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Create: `.github/pull_request_template.md`

- [ ] **Step 1: Write `.github/ISSUE_TEMPLATE/bug_report.yml`**

```yaml
name: Bug report
description: Report a defect or unexpected behavior
title: "bug: <one-line summary>"
labels: ["type:bug", "status:triage"]
body:
  - type: markdown
    attributes:
      value: |
        Thanks for taking the time to report a bug. Please fill out
        every required field. For security issues, use the private
        vulnerability reporting link in our `SECURITY.md`, not this
        form.
  - type: input
    id: version
    attributes:
      label: ks-gen version
      description: "Output of `ks-gen --version`."
      placeholder: "ks-gen, version 0.3.0"
    validations:
      required: true
  - type: input
    id: python_version
    attributes:
      label: Python version
      description: "Output of `python --version`."
      placeholder: "Python 3.12.4"
    validations:
      required: true
  - type: input
    id: os
    attributes:
      label: Operating system
      placeholder: "AlmaLinux 9.4, Ubuntu 24.04, Windows 11, ..."
    validations:
      required: true
  - type: textarea
    id: command
    attributes:
      label: Command run
      description: "The exact command that triggered the bug."
      render: shell
    validations:
      required: true
  - type: textarea
    id: expected
    attributes:
      label: Expected behavior
    validations:
      required: true
  - type: textarea
    id: actual
    attributes:
      label: Actual behavior
      description: "Include the full traceback if there is one."
      render: shell
    validations:
      required: true
  - type: textarea
    id: host_yaml
    attributes:
      label: host.yaml (if relevant)
      description: "Redact any secrets before pasting."
      render: yaml
    validations:
      required: false
```

- [ ] **Step 2: Write `.github/ISSUE_TEMPLATE/feature_request.yml`**

```yaml
name: Feature request
description: Propose a new capability or enhancement
title: "feat: <one-line summary>"
labels: ["type:feature", "status:triage"]
body:
  - type: textarea
    id: problem
    attributes:
      label: Problem statement
      description: "What can't you do today, or what's painful?"
    validations:
      required: true
  - type: textarea
    id: proposal
    attributes:
      label: Proposed solution
    validations:
      required: true
  - type: textarea
    id: alternatives
    attributes:
      label: Alternatives considered
    validations:
      required: true
  - type: textarea
    id: acceptance
    attributes:
      label: Acceptance criteria
      description: "How will we know this is done?"
    validations:
      required: true
```

- [ ] **Step 3: Write `.github/ISSUE_TEMPLATE/documentation.yml`**

```yaml
name: Documentation issue
description: Report a documentation problem or gap
title: "docs: <one-line summary>"
labels: ["type:docs", "status:triage"]
body:
  - type: input
    id: location
    attributes:
      label: Affected document and section
      placeholder: "MANUAL.md §3.2, README.md Quickstart, ..."
    validations:
      required: true
  - type: textarea
    id: issue
    attributes:
      label: What's confusing, wrong, or missing?
    validations:
      required: true
  - type: textarea
    id: suggestion
    attributes:
      label: Suggested fix (optional)
    validations:
      required: false
```

- [ ] **Step 4: Write `.github/ISSUE_TEMPLATE/config.yml`**

```yaml
blank_issues_enabled: false
contact_links:
  - name: Security vulnerability
    url: https://github.com/SupremeCommanderHedgehog/ks-gen/security/advisories/new
    about: Use GitHub's private vulnerability reporting for security issues.
  - name: Questions and discussion
    url: https://github.com/SupremeCommanderHedgehog/ks-gen/discussions
    about: Ask questions, share ideas, or discuss with the community.
```

- [ ] **Step 5: Write `.github/pull_request_template.md`**

```markdown
## Summary

<one to three sentences describing the change>

## Related issue

Closes #

## Test plan

- [ ] Local CI parity: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
- [ ] <feature-specific verification, if any>

## Checklist

- [ ] Conventional-commit subject (`feat:`, `fix:`, `docs:`, `refactor:`, `style:`, `test:`, `chore:`, `ci:`)
- [ ] Commits GPG-signed
- [ ] CHANGELOG entry added, or commits are conventional so release-please picks them up
- [ ] Documentation updated if behavior or surface changed
```

- [ ] **Step 6: Commit**

```
git add .github/ISSUE_TEMPLATE/ .github/pull_request_template.md
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "docs(github): add issue forms and PR template

Three YAML issue forms (bug, feature, docs) with required-field
validation and auto-applied type:* and status:triage labels. Blank
issues disabled; contact links route security and Q&A elsewhere.
PR template with CI-parity checkbox and conventional-commit checklist."
```

---

### Task A7: Label taxonomy retag and existing-issue migration

**Files:** none (label and issue state on GitHub).

- [ ] **Step 1: Delete unwanted default labels**

```
for label in duplicate invalid wontfix question bug enhancement documentation 'good first issue' 'help wanted'; do
  gh label delete "$label" --yes -R SupremeCommanderHedgehog/ks-gen || true
done
```

(`good first issue` and `help wanted` will be recreated below with
hyphenated names so they match GitHub Topic-style convention.)

- [ ] **Step 2: Create the prefixed label set**

```
# type:* (red family)
gh label create 'type:bug'       -c '#d73a4a' -d "Defect or unexpected behavior"               -R SupremeCommanderHedgehog/ks-gen
gh label create 'type:feature'   -c '#a2eeef' -d "New capability or enhancement"               -R SupremeCommanderHedgehog/ks-gen
gh label create 'type:docs'      -c '#0075ca' -d "Documentation only"                          -R SupremeCommanderHedgehog/ks-gen
gh label create 'type:refactor'  -c '#fbca04' -d "Restructure without behavior change"         -R SupremeCommanderHedgehog/ks-gen
gh label create 'type:security'  -c '#b60205' -d "Security issue or hardening"                 -R SupremeCommanderHedgehog/ks-gen
gh label create 'type:chore'     -c '#e4e669' -d "Tooling, deps, or build maintenance"         -R SupremeCommanderHedgehog/ks-gen
gh label create 'type:test'      -c '#bfd4f2' -d "Tests added or changed without behavior"     -R SupremeCommanderHedgehog/ks-gen

# area:* (blue family)
gh label create 'area:verify'    -c '#1d76db' -d "ks-gen verify subsystem"                     -R SupremeCommanderHedgehog/ks-gen
gh label create 'area:iso'       -c '#0e8a16' -d "ks-gen iso / install media"                  -R SupremeCommanderHedgehog/ks-gen
gh label create 'area:wizard'    -c '#5319e7' -d "ks-gen new interactive wizard"               -R SupremeCommanderHedgehog/ks-gen
gh label create 'area:disk'      -c '#0052cc' -d "Disk layout, LUKS, partitions"               -R SupremeCommanderHedgehog/ks-gen
gh label create 'area:cli'       -c '#1d76db' -d "CLI surface, flags, output"                  -R SupremeCommanderHedgehog/ks-gen
gh label create 'area:lint'      -c '#c5def5' -d "Generated-ks.cfg lint rules"                 -R SupremeCommanderHedgehog/ks-gen
gh label create 'area:templates' -c '#c5def5' -d "Jinja templates, skeleton emission"          -R SupremeCommanderHedgehog/ks-gen
gh label create 'area:ci'        -c '#bfdadc' -d "CI workflows, Actions"                       -R SupremeCommanderHedgehog/ks-gen
gh label create 'area:deps'      -c '#5319e7' -d "Dependencies"                                -R SupremeCommanderHedgehog/ks-gen
gh label create 'area:meta'      -c '#cccccc' -d "Repo metadata, project, releases"            -R SupremeCommanderHedgehog/ks-gen

# priority:* (gradient)
gh label create 'priority:p0'    -c '#b60205' -d "Drop everything"                             -R SupremeCommanderHedgehog/ks-gen
gh label create 'priority:p1'    -c '#d93f0b' -d "Next milestone"                              -R SupremeCommanderHedgehog/ks-gen
gh label create 'priority:p2'    -c '#fbca04' -d "Eventually"                                  -R SupremeCommanderHedgehog/ks-gen
gh label create 'priority:p3'    -c '#0e8a16' -d "Nice-to-have"                                -R SupremeCommanderHedgehog/ks-gen

# status:* (yellow family)
gh label create 'status:triage'         -c '#fef2c0' -d "Awaiting initial review"              -R SupremeCommanderHedgehog/ks-gen
gh label create 'status:blocked'        -c '#e99695' -d "Blocked on something external"        -R SupremeCommanderHedgehog/ks-gen
gh label create 'status:needs-info'     -c '#f9d0c4' -d "Waiting on reporter for info"         -R SupremeCommanderHedgehog/ks-gen
gh label create 'status:in-progress'    -c '#0e8a16' -d "Work in progress"                     -R SupremeCommanderHedgehog/ks-gen
gh label create 'status:ready-to-merge' -c '#0e8a16' -d "Approved, awaiting merge"             -R SupremeCommanderHedgehog/ks-gen

# Flag labels
gh label create 'good-first-issue'   -c '#7057ff' -d "Good for first-time contributors"        -R SupremeCommanderHedgehog/ks-gen
gh label create 'help-wanted'        -c '#008672' -d "Extra attention is needed"               -R SupremeCommanderHedgehog/ks-gen
gh label create 'breaking-change'    -c '#b60205' -d "Backwards-incompatible change"           -R SupremeCommanderHedgehog/ks-gen
gh label create 'dependencies'       -c '#0366d6' -d "Pull requests that update a dependency"  -R SupremeCommanderHedgehog/ks-gen
gh label create 'autorelease: pending'   -c '#ededed' -d "release-please: pending release PR"  -R SupremeCommanderHedgehog/ks-gen
gh label create 'autorelease: tagged'    -c '#ededed' -d "release-please: tag created"         -R SupremeCommanderHedgehog/ks-gen
gh label create 'autorelease: published' -c '#ededed' -d "release-please: release published"   -R SupremeCommanderHedgehog/ks-gen
```

- [ ] **Step 3: Verify the label set**

```
gh label list -R SupremeCommanderHedgehog/ks-gen --limit 60
```
Confirm all the labels above are present, and no `bug`, `enhancement`,
`documentation`, `duplicate`, `invalid`, `wontfix`, or `question`
labels remain.

- [ ] **Step 4: Re-label the 13 existing open issues**

Run each command and verify with `gh issue view`:

```
gh issue edit  6 --remove-label enhancement --add-label 'type:feature' --add-label 'area:iso'    --add-label 'priority:p2' -R SupremeCommanderHedgehog/ks-gen
gh issue edit  7 --remove-label enhancement --add-label 'type:feature' --add-label 'area:disk'   --add-label 'priority:p2' -R SupremeCommanderHedgehog/ks-gen
gh issue edit  8 --remove-label enhancement --add-label 'type:feature' --add-label 'area:disk'   --add-label 'priority:p1' -R SupremeCommanderHedgehog/ks-gen
gh issue edit  9 --remove-label enhancement --add-label 'type:feature' --add-label 'area:wizard' --add-label 'priority:p2' -R SupremeCommanderHedgehog/ks-gen
gh issue edit 10 --remove-label enhancement --add-label 'type:feature' --add-label 'area:verify' --add-label 'priority:p3' -R SupremeCommanderHedgehog/ks-gen
gh issue edit 11 --remove-label enhancement --add-label 'type:feature' --add-label 'area:verify' --add-label 'priority:p3' -R SupremeCommanderHedgehog/ks-gen
gh issue edit 12 --remove-label enhancement --add-label 'type:feature' --add-label 'area:verify' --add-label 'priority:p3' -R SupremeCommanderHedgehog/ks-gen
gh issue edit 13 --remove-label enhancement --add-label 'type:feature' --add-label 'area:verify' --add-label 'priority:p3' -R SupremeCommanderHedgehog/ks-gen
gh issue edit 14 --remove-label enhancement --add-label 'type:feature' --add-label 'area:verify' --add-label 'priority:p3' -R SupremeCommanderHedgehog/ks-gen
gh issue edit 15 --remove-label enhancement --add-label 'type:feature' --add-label 'area:verify' --add-label 'priority:p3' -R SupremeCommanderHedgehog/ks-gen
gh issue edit 16 --remove-label enhancement --add-label 'type:feature' --add-label 'area:verify' --add-label 'priority:p3' -R SupremeCommanderHedgehog/ks-gen
gh issue edit 17 --remove-label enhancement --add-label 'type:feature' --add-label 'area:verify' --add-label 'priority:p3' -R SupremeCommanderHedgehog/ks-gen
```

If `--remove-label enhancement` fails because the label was already
deleted in Step 1, that is fine — the relabel still applies the new
labels.

- [ ] **Step 5: Close issue #5 with a v0.3.0 pointer**

```
gh issue comment 5 -R SupremeCommanderHedgehog/ks-gen -b "Shipped in v0.3.0 (merge \`384ed90\`, tag \`v0.3.0\`). See https://github.com/SupremeCommanderHedgehog/ks-gen/releases/tag/v0.3.0 once the release is published."
gh issue close 5 -R SupremeCommanderHedgehog/ks-gen --reason completed
```

Note: the release URL above will 404 until PR-B creates the GitHub
Release in Task B9. That is intentional — the comment is correct
forward-looking.

(No commit for this task — remote-only changes.)

---

### Task A8: CI hardening

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Look up current action SHAs**

Run:
```
gh api repos/actions/checkout/git/ref/tags/v4.2.2 --jq .object.sha
gh api repos/actions/setup-python/git/ref/tags/v5.3.0 --jq .object.sha
gh api repos/step-security/harden-runner/git/ref/tags/v2.10.4 --jq .object.sha
gh api repos/actions/upload-artifact/git/ref/tags/v4.4.3 --jq .object.sha
```

Record the four 40-character SHA values. If a tag returned does not
exist (rare), use `gh api repos/<owner>/<repo>/releases/latest --jq '.tag_name'`
to find the latest tag, then re-query.

- [ ] **Step 2: Replace `.github/workflows/ci.yml`**

Write the file (use the SHAs and version comments from Step 1; the
`<sha-checkout>` etc. are placeholders to substitute):

```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

jobs:
  ruff:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions:
      contents: read
      actions: none
      checks: none
      id-token: none
    steps:
      - uses: step-security/harden-runner@<sha-harden-runner> # v2.10.4
        with:
          egress-policy: audit
      - uses: actions/checkout@<sha-checkout> # v4.2.2
      - uses: actions/setup-python@<sha-setup-python> # v5.3.0
        with:
          python-version: "3.13"
          cache: pip
      - name: Install ruff
        run: pip install ruff
      - name: ruff check
        run: ruff check src tests
      - name: ruff format --check
        run: ruff format --check src tests

  test:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    permissions:
      contents: read
      actions: none
      checks: none
      id-token: none
    strategy:
      fail-fast: false
      matrix:
        python: ["3.11", "3.12", "3.13"]
    steps:
      - uses: step-security/harden-runner@<sha-harden-runner> # v2.10.4
        with:
          egress-policy: audit
      - uses: actions/checkout@<sha-checkout> # v4.2.2
      - uses: actions/setup-python@<sha-setup-python> # v5.3.0
        with:
          python-version: ${{ matrix.python }}
          cache: pip
      - name: Install
        run: pip install -e ".[dev]"
      - name: Type check (mypy)
        run: mypy
      - name: Test (pytest)
        run: pytest -q
      - name: Upload failure artifacts
        if: failure()
        uses: actions/upload-artifact@<sha-upload-artifact> # v4.4.3
        with:
          name: pytest-artifacts-${{ matrix.python }}
          path: |
            tests/__snapshots__/**
            tests/golden/__snapshots__/**
          if-no-files-found: ignore
          retention-days: 7
```

The original ci.yml had four steps in one job (`Lint`, `Format check`,
`Type check`, `Test`). This split puts `ruff` in a fast non-matrix
job and keeps `mypy` + `pytest` in the matrix. The required status
checks the ruleset will list are `ruff`, `test (3.11)`, `test (3.12)`,
`test (3.13)`.

- [ ] **Step 3: Validate the workflow with actionlint**

```
docker run --rm -v "$PWD:/repo" rhysd/actionlint:latest -color
```

(If Docker is not available, push the branch and check the Actions tab
for parse errors after running. `actionlint` is the cheaper feedback.)

Expected: no errors.

- [ ] **Step 4: Commit**

```
git add .github/workflows/ci.yml
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "ci: harden workflow + split ruff into fast-path job

- SHA-pin every action with version comment.
- Explicit per-job permissions (id-token/actions/checks all none).
- Concurrency cancels superseded PR runs.
- step-security/harden-runner in audit mode at the top of each job.
- Fast 'ruff' job (no matrix) fails formatting drift in seconds.
- Matrix 'test' job runs mypy + pytest on 3.11/3.12/3.13.
- Upload tests/__snapshots__ on failure for post-mortem.

Status checks the branch ruleset will require:
ruff, test (3.11), test (3.12), test (3.13)."
```

---

### Task A9: Pre-commit hooks

**Files:**
- Create: `.pre-commit-config.yaml`

- [ ] **Step 1: Write `.pre-commit-config.yaml`**

```yaml
# Local hook chain mirroring the CI workflow at .github/workflows/ci.yml.
# Install once per checkout:  pre-commit install
# Run on demand:               pre-commit run --all-files
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.7.4
    hooks:
      - id: ruff
        args: [src, tests]
      - id: ruff-format
        args: [--check, src, tests]
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.13.0
    hooks:
      - id: mypy
        args: [--config-file=pyproject.toml]
        additional_dependencies:
          - pydantic>=2.6
          - types-PyYAML
          - typer>=0.12
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: check-yaml
      - id: check-toml
      - id: check-json
      - id: end-of-file-fixer
      - id: trailing-whitespace
        args: [--markdown-linebreak-ext=md]
      - id: mixed-line-ending
        args: [--fix=lf]
```

The CI yml at this point does not yet have these tools in a workflow,
but `pre-commit install` will execute them as a pre-commit local hook.
The user opts in by running `pre-commit install` once in their working
copy (already documented in CONTRIBUTING.md from Task A2).

- [ ] **Step 2: Optionally install and run locally to confirm pass**

```
pip install pre-commit
pre-commit run --all-files
```

If any hook fails, do **not** mass-apply fixes; investigate. The most
likely failure is `end-of-file-fixer` finding files that lack a final
newline — those can be fixed in this same commit if cleanup remains
small. If the failure is broad, raise it as an issue and skip the
local install step.

Expected (after fixes if any): all hooks pass.

- [ ] **Step 3: Commit**

```
git add .pre-commit-config.yaml
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "chore: add pre-commit config mirroring CI parity chain

Local hooks for ruff, mypy, and a few small text/json/yaml/toml
sanitychecks. Mirrors the CI parity chain so contributors catch lint
drift before pushing. Install via 'pre-commit install'."
```

---

### Task A10: Going-public runbook

**Files:**
- Create: `docs/going-public.md`

- [ ] **Step 1: Write `docs/going-public.md`**

```markdown
# Going-public runbook

When you decide to flip `SupremeCommanderHedgehog/ks-gen` from private
to public, walk this checklist in order. None of these steps are
automated; each is one short shell command or a click in the GitHub UI.

## 1. Flip visibility

GitHub UI → **Settings → General → Danger Zone → Change visibility →
Make public**. Confirm the repo name.

## 2. Enable secret scanning + push protection

```bash
gh api -X PATCH repos/SupremeCommanderHedgehog/ks-gen \
  -F security_and_analysis[secret_scanning][status]=enabled \
  -F security_and_analysis[secret_scanning_push_protection][status]=enabled
```

Verify:

```bash
gh api repos/SupremeCommanderHedgehog/ks-gen \
  --jq '.security_and_analysis'
```

## 3. Activate CodeQL on push and PR

Edit `.github/workflows/codeql.yml`. Find this block:

```yaml
on:
  workflow_dispatch:
  # Activate at public launch — see docs/going-public.md:
  # push:
  #   branches: [main]
  # pull_request:
  #   branches: [main]
  # schedule:
  #   - cron: '17 7 * * 1'  # Mondays 07:17 UTC
```

Uncomment the five lines under the comment. Commit on a branch, open
a PR titled `ci(codeql): activate scheduled and PR scans`, merge.

## 4. Tighten the branch ruleset

```bash
# Find the ruleset id:
gh api repos/SupremeCommanderHedgehog/ks-gen/rulesets --jq '.[] | select(.name == "main protection") | .id'
```

Edit the ruleset via REST:

```bash
RULESET_ID=<id from above>

# Remove the maintainer bypass and add a PR requirement.
gh api -X PUT repos/SupremeCommanderHedgehog/ks-gen/rulesets/$RULESET_ID \
  --input - <<'JSON'
{
  "name": "main protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "bypass_actors": [
    { "actor_type": "Integration", "actor_id": "<github-actions[bot] integration id>", "bypass_mode": "pull_request" }
  ],
  "rules": [
    { "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [
          {"context": "ruff"},
          {"context": "test (3.11)"},
          {"context": "test (3.12)"},
          {"context": "test (3.13)"}
        ]
      }
    },
    { "type": "required_signatures" },
    { "type": "required_linear_history" },
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 1,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": false
      }
    }
  ]
}
JSON
```

This removes your bypass and requires PRs with one approving review.
Owners can self-approve until other collaborators exist.

## 5. Reconsider Codecov / coverage

You opted out during the github-setup design. If usage justifies it
now, revisit by following Codecov's setup docs and adding a step to
the `test` job in `.github/workflows/ci.yml`.

## 6. Smoke-test CodeQL

```bash
gh workflow run codeql.yml -R SupremeCommanderHedgehog/ks-gen
```

Wait for the run to complete:

```bash
gh run list --workflow codeql.yml -L 1
```

Confirm green before announcing.

## 7. Open an announcement

In Discussions (which was enabled in PR-A), open a post in the
**Announcements** category titled "ks-gen is now public!". Link the
README, the latest release, and the security policy.
```

- [ ] **Step 2: Commit**

```
git add docs/going-public.md
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "docs: going-public runbook for the visibility flip

Numbered checklist for the once-only operation of making ks-gen
public: visibility flip, secret scanning, CodeQL activation,
branch ruleset tightening, smoke test, announcement."
```

---

### Task A11: Branch protection ruleset on `main`

**Files:** none (remote ruleset on GitHub).

- [ ] **Step 1: Find the maintainer's actor id**

```
gh api users/SupremeCommanderHedgehog --jq .id
```

Record the integer id. This is the `actor_id` for the bypass list.

The "Repository admin" role is `actor_type: "RepositoryRole"` with
`actor_id: 5` (built-in). Reference:
https://docs.github.com/en/rest/repos/rules

- [ ] **Step 2: Create the ruleset**

Write the JSON to a temp file (the JSON heredoc form is the simplest
way to keep escaping right):

```
cat > /tmp/main-ruleset.json <<'JSON'
{
  "name": "main protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["~DEFAULT_BRANCH"],
      "exclude": []
    }
  },
  "bypass_actors": [
    { "actor_type": "RepositoryRole", "actor_id": 5, "bypass_mode": "always" }
  ],
  "rules": [
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [
          {"context": "ruff"},
          {"context": "test (3.11)"},
          {"context": "test (3.12)"},
          {"context": "test (3.13)"}
        ]
      }
    },
    { "type": "required_signatures" },
    { "type": "required_linear_history" },
    { "type": "deletion" },
    { "type": "non_fast_forward" }
  ]
}
JSON

gh api -X POST repos/SupremeCommanderHedgehog/ks-gen/rulesets \
  --input /tmp/main-ruleset.json
```

Note: the `RepositoryRole` actor with `actor_id: 5` is the Repository
admin role (you). `bypass_mode: always` means you can bypass any rule
for any push, including direct pushes. The `pull_request` rule is
deliberately **not** included — that's the going-public-runbook step.

- [ ] **Step 3: Verify the ruleset**

```
gh api repos/SupremeCommanderHedgehog/ks-gen/rulesets --jq '.[]'
```

Confirm `name: "main protection"`, `enforcement: "active"`, and the
rules list matches above.

- [ ] **Step 4: Smoke-test that you can still push to main**

After PR-A is merged (Task A12), confirm by doing one trivial
operation through the normal local-merge flow. The ruleset should
allow the merge because you're on the bypass list. If it blocks,
re-check the bypass_actor entry.

(No commit for this task — remote-only change. Note the ruleset id
returned by the create call in the PR-A description for posterity.)

---

### Task A12: Open PR-A and merge

**Files:** none (git ops).

- [ ] **Step 1: Push the feature branch**

```
git push -u origin impl/github-setup-foundation
```

- [ ] **Step 2: Open the PR**

```
gh pr create -R SupremeCommanderHedgehog/ks-gen \
  --base main --head impl/github-setup-foundation \
  --title "github-setup PR-A: foundation (docs, templates, labels, CI, ruleset)" \
  --body "$(cat <<'EOF'
## Summary

Foundation layer for the github-setup design. Lands public-readiness
docs, issue forms, PR template, label taxonomy retag (existing 13
issues relabeled, #5 closed), CI hardening with SHA-pinned actions
and a fast-path ruff job, and a branch ruleset on `main` with the
maintainer on the bypass list so the existing local-merge workflow
continues to work.

## Related issue

Spec: `docs/superpowers/specs/2026-06-07-github-setup-design.md`.

PR-B follows with Project v2 automation, Dependabot, dormant CodeQL,
SBOM, and release-please.

## Remote state changed (no commits)

- Description: "Remote-safe DISA STIG kickstart generator for AlmaLinux 9"
- Topics: kickstart, almalinux, stig, oscap, compliance, disa, python, security-hardening
- has_wiki: false, has_discussions: true, delete_branch_on_merge: true
- Private vulnerability reporting: enabled
- Labels: replaced default set with prefixed taxonomy (`type:*`, `area:*`, `priority:*`, `status:*`)
- 13 open issues re-labeled; #5 closed with a v0.3.0 pointer
- Branch ruleset created on `main` (name: "main protection")

## Test plan

- [ ] Local CI parity: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
- [ ] CI passes in PR view (ruff + 3.11/3.12/3.13 matrix)
- [ ] `gh ruleset list` shows "main protection" as active
- [ ] `gh repo view --json topics,description,hasWikiEnabled,hasDiscussionsEnabled,deleteBranchOnMerge` matches expected state

## Checklist

- [ ] Conventional-commit subjects
- [ ] Commits GPG-signed
- [ ] CHANGELOG entry added — N/A (no user-facing surface change)
- [ ] Documentation updated — yes, this PR is documentation
EOF
)"
```

- [ ] **Step 3: Wait for CI to pass on the PR**

```
gh pr checks --watch
```

Expected: all four checks (`ruff`, `test (3.11/3.12/3.13)`) green.

- [ ] **Step 4: Merge to main**

Match the project convention from memory (`--no-ff`, signed merge
commit, then push):

```
git checkout main
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
  merge --no-ff -S -m "Merge branch 'impl/github-setup-foundation'" impl/github-setup-foundation
ruff check src tests && ruff format --check src tests && mypy && pytest -q
git push origin main
```

- [ ] **Step 5: Delete the feature branch (the new `delete_branch_on_merge` setting will handle the remote; the local needs cleanup)**

```
git branch -d impl/github-setup-foundation
```

Phase A complete.

---

## Phase B — Automation (PR-B)

### Task B1: Create the feature branch

- [ ] **Step 1: Confirm clean state and branch off main**

```
git checkout main
git pull
git checkout -b impl/github-setup-automation
```

---

### Task B2: Create the user-level Project v2 (manual)

**Files:** none (browser-only).

This task is fully manual. The plan documents it so the engineer doesn't
get stuck.

- [ ] **Step 1: Create the project via the GitHub UI**

Navigate to https://github.com/SupremeCommanderHedgehog?tab=projects
→ **New project** → Template: **Board** → Title: `ks-gen` →
Description: `Issue & PR tracking for the ks-gen kickstart generator.`

- [ ] **Step 2: Link the project to the repository**

In the project settings (... → Settings → Manage access) add
`SupremeCommanderHedgehog/ks-gen` as a linked repository.

- [ ] **Step 3: Add custom fields**

Project → Settings → Custom fields. Add four:

| Name | Type | Values |
|---|---|---|
| Status | Single-select (already exists as default) | Backlog, Ready, In progress, In review, Done |
| Priority | Single-select | P0, P1, P2, P3 |
| Area | Single-select | verify, iso, wizard, disk, cli, lint, templates, ci, deps, meta |
| Iteration | Iteration | 2 weeks, start the upcoming Monday |
| Estimate | Number | (no preset values; numeric input) |

The `Status` field exists by default — confirm or rename its options to
match the list above.

- [ ] **Step 4: Create five views**

For each view: click the **+** next to existing views, give it a name,
configure as below.

1. **Board** — Layout: Board, Group by: Status. (Default board renamed.)
2. **Triage** — Layout: Table, Filter:
   `is:open status:Backlog label:status:triage`, Sort: Created ascending.
3. **By area** — Layout: Board, Group by: Area.
4. **Roadmap** — Layout: Roadmap, Markers/Lanes: Area, Date field:
   Iteration.
5. **Closed (last 30 days)** — Layout: Table, Filter:
   `is:closed closed:>=@today-30d`, Sort: Closed descending.

- [ ] **Step 5: Record the project URL and id**

The project URL is shown in the browser address bar. The id can be
found by:

```
gh api graphql -f query='
{
  user(login: "SupremeCommanderHedgehog") {
    projectsV2(first: 10) {
      nodes { id title number url }
    }
  }
}'
```

Note the `id` and `number` of the `ks-gen` project. The `number` goes
into the workflow files in later tasks; the `id` is used by the GraphQL
archive workflow.

(No commit for this task — manual setup.)

---

### Task B3: Create the project PAT and store as a repo secret (manual)

**Files:** none (browser + UI).

- [ ] **Step 1: Generate a fine-grained personal access token**

Navigate to https://github.com/settings/tokens?type=beta → **Generate
new token**.

- Token name: `ks-gen project automation`
- Expiration: 1 year (record the calendar reminder to rotate before
  expiry)
- Resource owner: `SupremeCommanderHedgehog`
- Repository access: Only select repositories → `ks-gen`
- Repository permissions:
  - Contents: Read-only
  - Metadata: Read-only
- Account permissions:
  - Projects: Read and write

Generate the token. Copy the value — you will not see it again.

- [ ] **Step 2: Store as a repo secret**

```
gh secret set KSGEN_PROJECT_TOKEN -R SupremeCommanderHedgehog/ks-gen
```

When prompted, paste the token value from Step 1.

Verify:

```
gh secret list -R SupremeCommanderHedgehog/ks-gen
```

`KSGEN_PROJECT_TOKEN` should appear.

(No commit for this task — secret state on GitHub.)

---

### Task B4: Dependabot configuration

**Files:**
- Create: `.github/dependabot.yml`

- [ ] **Step 1: Write `.github/dependabot.yml`**

```yaml
version: 2
updates:
  # Python dependencies declared in pyproject.toml (runtime + [dev]).
  - package-ecosystem: pip
    directory: /
    schedule:
      interval: weekly
      day: monday
      time: "06:00"
      timezone: America/New_York
    open-pull-requests-limit: 5
    labels:
      - "type:chore"
      - "dependencies"
      - "area:deps"
    commit-message:
      prefix: "chore(deps)"
      include: scope
    groups:
      dev-deps:
        patterns:
          - "pytest*"
          - "ruff*"
          - "mypy*"
          - "syrupy*"
          - "types-*"
      runtime-deps:
        patterns:
          - "*"
        exclude-patterns:
          - "pytest*"
          - "ruff*"
          - "mypy*"
          - "syrupy*"
          - "types-*"

  # GitHub Actions versions in .github/workflows/*.yml.
  # Keeps the SHA pins from Task A8 fresh.
  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
      day: monday
    open-pull-requests-limit: 5
    labels:
      - "type:chore"
      - "dependencies"
      - "area:ci"
    commit-message:
      prefix: "chore(actions)"
```

- [ ] **Step 2: Commit**

```
git add .github/dependabot.yml
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "ci(dependabot): weekly pip + github-actions updates with grouping

Two ecosystems (pip and github-actions), Monday schedule,
grouped so dev-deps and runtime-deps each emit one PR per week
instead of one per package. github-actions ecosystem keeps the
SHA-pinned actions from ci.yml fresh."
```

---

### Task B5: CodeQL workflow (dormant)

**Files:**
- Create: `.github/workflows/codeql.yml`

- [ ] **Step 1: Look up CodeQL action SHA**

```
gh api repos/github/codeql-action/git/ref/tags/v3.27.5 --jq .object.sha
```

(If v3.27.5 doesn't exist, find the latest v3.x:
`gh release list -R github/codeql-action -L 5 --exclude-pre-releases`.)

Use the same `actions/checkout` SHA from Task A8.

- [ ] **Step 2: Write `.github/workflows/codeql.yml`**

```yaml
name: codeql
on:
  workflow_dispatch:
  # Activate at public launch — see docs/going-public.md §3:
  # push:
  #   branches: [main]
  # pull_request:
  #   branches: [main]
  # schedule:
  #   - cron: '17 7 * * 1'  # Mondays 07:17 UTC

permissions:
  actions: read
  contents: read
  security-events: write

jobs:
  analyze:
    name: analyze (${{ matrix.language }})
    runs-on: ubuntu-latest
    timeout-minutes: 30
    strategy:
      fail-fast: false
      matrix:
        language: [python]
    steps:
      - uses: step-security/harden-runner@<sha-harden-runner> # v2.10.4
        with:
          egress-policy: audit
      - uses: actions/checkout@<sha-checkout> # v4.2.2
      - uses: github/codeql-action/init@<sha-codeql-action> # v3.27.5
        with:
          languages: ${{ matrix.language }}
          queries: security-extended,security-and-quality
      - uses: github/codeql-action/analyze@<sha-codeql-action> # v3.27.5
        with:
          category: "/language:${{ matrix.language }}"
```

- [ ] **Step 3: Validate with actionlint**

```
docker run --rm -v "$PWD:/repo" rhysd/actionlint:latest -color
```
Expected: no errors.

- [ ] **Step 4: Smoke-test the workflow_dispatch trigger (after merge to main)**

The workflow_dispatch trigger only appears in the UI after the file
exists on the default branch. After PR-B merges, run:

```
gh workflow run codeql.yml -R SupremeCommanderHedgehog/ks-gen
```

On a private repo this will likely fail with a permissions/billing
error at the analyze step (free CodeQL needs public). That is expected
and not a blocker. The going-public runbook §3 + §6 covers full
activation.

- [ ] **Step 5: Commit**

```
git add .github/workflows/codeql.yml
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "ci(codeql): add dormant workflow for python analysis

workflow_dispatch only on a private repo (free CodeQL requires
public). The push/pull_request/schedule triggers are commented out
with a docs/going-public.md §3 pointer. Wiring it now keeps it in
git history; activating it later is a five-line uncomment."
```

---

### Task B6: SBOM workflow

**Files:**
- Create: `.github/workflows/sbom.yml`

- [ ] **Step 1: Look up SHAs**

```
gh api repos/softprops/action-gh-release/git/ref/tags/v2.0.9 --jq .object.sha
```

Re-use the `actions/checkout` and `actions/setup-python` SHAs from
Task A8.

- [ ] **Step 2: Pin the cyclonedx-bom version**

The latest stable CycloneDX Python tool at plan-write time is
`cyclonedx-bom==4.7.0`. Verify:

```
pip index versions cyclonedx-bom 2>&1 | head -5
```

If a newer version is available, use that and update the pin below.

- [ ] **Step 3: Write `.github/workflows/sbom.yml`**

```yaml
name: sbom
on:
  release:
    types: [published]

permissions:
  contents: write  # required to upload a release asset

jobs:
  cyclonedx:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: step-security/harden-runner@<sha-harden-runner> # v2.10.4
        with:
          egress-policy: audit
      - uses: actions/checkout@<sha-checkout> # v4.2.2
        with:
          ref: ${{ github.event.release.tag_name }}
      - uses: actions/setup-python@<sha-setup-python> # v5.3.0
        with:
          python-version: "3.13"
          cache: pip
      - name: Install ks-gen and CycloneDX
        run: |
          pip install -e .
          pip install cyclonedx-bom==4.7.0
      - name: Generate SBOM (CycloneDX JSON)
        run: |
          cyclonedx-py environment \
            --of json \
            -o sbom-${{ github.event.release.tag_name }}.cdx.json
      - name: Attach SBOM to release
        uses: softprops/action-gh-release@<sha-action-gh-release> # v2.0.9
        with:
          tag_name: ${{ github.event.release.tag_name }}
          files: sbom-${{ github.event.release.tag_name }}.cdx.json
```

- [ ] **Step 4: Validate with actionlint**

```
docker run --rm -v "$PWD:/repo" rhysd/actionlint:latest -color
```
Expected: no errors.

- [ ] **Step 5: Commit**

```
git add .github/workflows/sbom.yml
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "ci(sbom): generate CycloneDX SBOM on release published

Triggers on release:published (release-please will emit this once
it's enabled). Installs ks-gen into a fresh environment and emits a
CycloneDX JSON SBOM, attached to the release as
sbom-<tag>.cdx.json."
```

---

### Task B7: Project automation workflows (add, archive, sync)

**Files:**
- Create: `.github/workflows/project-add.yml`
- Create: `.github/workflows/project-archive-closed.yml`
- Create: `.github/workflows/project-sync-labels.yml`

- [ ] **Step 1: Look up the actions/add-to-project SHA**

```
gh api repos/actions/add-to-project/git/ref/tags/v1.0.2 --jq .object.sha
```

- [ ] **Step 2: Write `.github/workflows/project-add.yml`**

Use the project URL from Task B2 Step 5 (`https://github.com/users/SupremeCommanderHedgehog/projects/<N>`).
Substitute `<N>` with the project number.

```yaml
name: project-add
on:
  issues:
    types: [opened, transferred, reopened]
  pull_request_target:
    types: [opened, reopened]

permissions:
  contents: read

concurrency:
  group: project-add-${{ github.event.number || github.run_id }}
  cancel-in-progress: false

jobs:
  add:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: step-security/harden-runner@<sha-harden-runner> # v2.10.4
        with:
          egress-policy: audit
      - uses: actions/add-to-project@<sha-add-to-project> # v1.0.2
        with:
          project-url: https://github.com/users/SupremeCommanderHedgehog/projects/<N>
          github-token: ${{ secrets.KSGEN_PROJECT_TOKEN }}
```

- [ ] **Step 3: Write `.github/workflows/project-archive-closed.yml`**

Substitute `<PROJECT_NODE_ID>` with the GraphQL node id from Task B2
Step 5 (the `id` field, format `PVT_kw...`).

```yaml
name: project-archive-closed
on:
  schedule:
    - cron: "0 6 * * *"   # 06:00 UTC daily
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: project-archive
  cancel-in-progress: false

jobs:
  archive:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: step-security/harden-runner@<sha-harden-runner> # v2.10.4
        with:
          egress-policy: audit
      - name: Archive closed-30d project items
        env:
          GH_TOKEN: ${{ secrets.KSGEN_PROJECT_TOKEN }}
          PROJECT_ID: <PROJECT_NODE_ID>
        run: |
          set -euo pipefail
          cutoff=$(date -u -d '30 days ago' '+%Y-%m-%dT%H:%M:%SZ')
          echo "Archiving project items where the linked issue or PR closed before $cutoff"

          # Page through project items; collect ids of items whose linked
          # content is closed and whose closedAt is older than cutoff.
          end_cursor=null
          to_archive=()
          while :; do
            after=""
            if [ "$end_cursor" != "null" ]; then
              after=", after: \"$end_cursor\""
            fi
            response=$(gh api graphql -f query="
              query {
                node(id: \"$PROJECT_ID\") {
                  ... on ProjectV2 {
                    items(first: 100$after) {
                      pageInfo { hasNextPage endCursor }
                      nodes {
                        id
                        isArchived
                        content {
                          __typename
                          ... on Issue       { closed closedAt }
                          ... on PullRequest { closed closedAt }
                        }
                      }
                    }
                  }
                }
              }
            ")

            echo "$response" | jq -r --arg cutoff "$cutoff" '
              .data.node.items.nodes[]
              | select(.isArchived == false)
              | select(.content.closed == true)
              | select(.content.closedAt != null and .content.closedAt < $cutoff)
              | .id
            ' | while read -r item_id; do
              to_archive+=("$item_id")
              echo "queue archive: $item_id"
            done

            has_next=$(echo "$response" | jq -r '.data.node.items.pageInfo.hasNextPage')
            end_cursor=$(echo "$response" | jq -r '.data.node.items.pageInfo.endCursor')
            [ "$has_next" = "true" ] || break
          done

          for item_id in "${to_archive[@]}"; do
            gh api graphql -f query="
              mutation {
                archiveProjectV2Item(input: { projectId: \"$PROJECT_ID\", itemId: \"$item_id\" }) {
                  item { id isArchived }
                }
              }
            " > /dev/null
            echo "archived: $item_id"
          done

          echo "Done. Archived ${#to_archive[@]} items."
```

- [ ] **Step 4: Write `.github/workflows/project-sync-labels.yml`**

Substitute `<PROJECT_NODE_ID>`, and look up the field+option ids by
running this query once after the project exists:

```
gh api graphql -f query='
{
  node(id: "<PROJECT_NODE_ID>") {
    ... on ProjectV2 {
      fields(first: 30) {
        nodes {
          ... on ProjectV2SingleSelectField {
            id name options { id name }
          }
        }
      }
    }
  }
}'
```

Record the `id` of the `Priority` and `Area` fields, and the `id` of
each option (e.g. `P0`, `P1`, ..., `verify`, `iso`, ...). The script
below uses associative arrays mapping label → option id.

```yaml
name: project-sync-labels
on:
  issues:
    types: [labeled, unlabeled]
  pull_request_target:
    types: [labeled, unlabeled]

permissions:
  contents: read

concurrency:
  group: project-sync-${{ github.event.issue.number || github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  sync:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: step-security/harden-runner@<sha-harden-runner> # v2.10.4
        with:
          egress-policy: audit
      - name: Compute and apply field values
        env:
          GH_TOKEN: ${{ secrets.KSGEN_PROJECT_TOKEN }}
          PROJECT_ID: <PROJECT_NODE_ID>
          PRIORITY_FIELD_ID: <PRIORITY_FIELD_ID>
          AREA_FIELD_ID: <AREA_FIELD_ID>
          # Label → option id maps (filled in by hand after project is created):
          P0_OPT: <opt-id-P0>
          P1_OPT: <opt-id-P1>
          P2_OPT: <opt-id-P2>
          P3_OPT: <opt-id-P3>
          VERIFY_OPT: <opt-id-verify>
          ISO_OPT: <opt-id-iso>
          WIZARD_OPT: <opt-id-wizard>
          DISK_OPT: <opt-id-disk>
          CLI_OPT: <opt-id-cli>
          LINT_OPT: <opt-id-lint>
          TEMPLATES_OPT: <opt-id-templates>
          CI_OPT: <opt-id-ci>
          DEPS_OPT: <opt-id-deps>
          META_OPT: <opt-id-meta>
          CONTENT_NODE_ID: ${{ github.event.issue.node_id || github.event.pull_request.node_id }}
        run: |
          set -euo pipefail

          # Resolve the project item id for this content.
          item_id=$(gh api graphql -f query="
            query {
              node(id: \"$CONTENT_NODE_ID\") {
                ... on Issue       { projectItems(first: 20) { nodes { id project { id } } } }
                ... on PullRequest { projectItems(first: 20) { nodes { id project { id } } } }
              }
            }
          " | jq -r --arg pid "$PROJECT_ID" '
            (.data.node.projectItems.nodes // [])
            | map(select(.project.id == $pid))
            | .[0].id // empty
          ')

          if [ -z "$item_id" ]; then
            echo "Content not in project — project-add workflow may not have run yet."
            exit 0
          fi

          # Pull current labels.
          labels=$(gh api graphql -f query="
            query {
              node(id: \"$CONTENT_NODE_ID\") {
                ... on Issue       { labels(first: 50) { nodes { name } } }
                ... on PullRequest { labels(first: 50) { nodes { name } } }
              }
            }
          " | jq -r '.data.node.labels.nodes[].name')

          set_field() {
            local field_id="$1"; local option_id="$2"
            gh api graphql -f query="
              mutation {
                updateProjectV2ItemFieldValue(input: {
                  projectId: \"$PROJECT_ID\",
                  itemId: \"$item_id\",
                  fieldId: \"$field_id\",
                  value: { singleSelectOptionId: \"$option_id\" }
                }) { projectV2Item { id } }
              }" > /dev/null
          }

          # Priority sync.
          for L in $labels; do
            case "$L" in
              priority:p0) set_field "$PRIORITY_FIELD_ID" "$P0_OPT" ;;
              priority:p1) set_field "$PRIORITY_FIELD_ID" "$P1_OPT" ;;
              priority:p2) set_field "$PRIORITY_FIELD_ID" "$P2_OPT" ;;
              priority:p3) set_field "$PRIORITY_FIELD_ID" "$P3_OPT" ;;
            esac
          done

          # Area sync.
          for L in $labels; do
            case "$L" in
              area:verify)    set_field "$AREA_FIELD_ID" "$VERIFY_OPT" ;;
              area:iso)       set_field "$AREA_FIELD_ID" "$ISO_OPT" ;;
              area:wizard)    set_field "$AREA_FIELD_ID" "$WIZARD_OPT" ;;
              area:disk)      set_field "$AREA_FIELD_ID" "$DISK_OPT" ;;
              area:cli)       set_field "$AREA_FIELD_ID" "$CLI_OPT" ;;
              area:lint)      set_field "$AREA_FIELD_ID" "$LINT_OPT" ;;
              area:templates) set_field "$AREA_FIELD_ID" "$TEMPLATES_OPT" ;;
              area:ci)        set_field "$AREA_FIELD_ID" "$CI_OPT" ;;
              area:deps)      set_field "$AREA_FIELD_ID" "$DEPS_OPT" ;;
              area:meta)      set_field "$AREA_FIELD_ID" "$META_OPT" ;;
            esac
          done

          echo "Sync complete for $CONTENT_NODE_ID (item $item_id)."
```

- [ ] **Step 5: Validate all three with actionlint**

```
docker run --rm -v "$PWD:/repo" rhysd/actionlint:latest -color
```
Expected: no errors.

- [ ] **Step 6: Commit**

```
git add .github/workflows/project-add.yml .github/workflows/project-archive-closed.yml .github/workflows/project-sync-labels.yml
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "ci(project): add-on-open + archive-after-30d + label-to-field sync

Three workflows talking to the user-level Project v2 via the
KSGEN_PROJECT_TOKEN secret. The default GITHUB_TOKEN cannot reach
user-level projects, hence the PAT. Archive workflow runs daily;
sync workflow runs on every label change; add runs on issue/PR open."
```

---

### Task B8: release-please

**Files:**
- Create: `release-please-config.json`
- Create: `.release-please-manifest.json`
- Create: `.github/workflows/release-please.yml`

- [ ] **Step 1: Look up the release-please-action SHA**

```
gh api repos/googleapis/release-please-action/git/ref/tags/v4.1.4 --jq .object.sha
```

- [ ] **Step 2: Write `.release-please-manifest.json`**

```json
{
  ".": "0.3.0"
}
```

- [ ] **Step 3: Write `release-please-config.json`**

```json
{
  "$schema": "https://raw.githubusercontent.com/googleapis/release-please/main/schemas/config.json",
  "packages": {
    ".": {
      "release-type": "python",
      "package-name": "ks-gen",
      "changelog-path": "CHANGELOG.md",
      "changelog-sections": [
        { "type": "feat",     "section": "Features" },
        { "type": "fix",      "section": "Bug Fixes" },
        { "type": "perf",     "section": "Performance" },
        { "type": "refactor", "section": "Refactoring" },
        { "type": "docs",     "section": "Documentation" },
        { "type": "test",     "section": "Tests",  "hidden": true },
        { "type": "ci",       "section": "CI",     "hidden": true },
        { "type": "chore",    "section": "Chores", "hidden": true },
        { "type": "style",    "section": "Style",  "hidden": true }
      ],
      "extra-files": ["pyproject.toml"],
      "include-component-in-tag": false,
      "draft": false,
      "prerelease": false
    }
  }
}
```

- [ ] **Step 4: Write `.github/workflows/release-please.yml`**

```yaml
name: release-please
on:
  push:
    branches: [main]

permissions:
  contents: write
  pull-requests: write

concurrency:
  group: release-please
  cancel-in-progress: false

jobs:
  release:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: step-security/harden-runner@<sha-harden-runner> # v2.10.4
        with:
          egress-policy: audit
      - uses: googleapis/release-please-action@<sha-release-please-action> # v4.1.4
        with:
          config-file: release-please-config.json
          manifest-file: .release-please-manifest.json
          token: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **Step 5: Validate with actionlint**

```
docker run --rm -v "$PWD:/repo" rhysd/actionlint:latest -color
```
Expected: no errors.

- [ ] **Step 6: Commit**

```
git add release-please-config.json .release-please-manifest.json .github/workflows/release-please.yml
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "ci(release-please): config + workflow for python single-package mode

Manifest pinned at 0.3.0 (the current shipped version). Release type
'python' so pyproject.toml's version and CHANGELOG.md are managed
together. Conventional-commit categories from the spec; hidden
categories (test/ci/chore/style) still produce changelog entries via
release-please's internal log but are suppressed from the rendered
CHANGELOG.md."
```

---

### Task B9: Manually create the v0.3.0 GitHub Release

**Files:** none (remote release object).

Before release-please can compute the next release, it needs to see a
GitHub Release object at the current `latest` tag. The tag exists; the
Release object does not.

- [ ] **Step 1: Create the GitHub Release for v0.3.0**

```
gh release create v0.3.0 -R SupremeCommanderHedgehog/ks-gen \
  --verify-tag \
  --title "v0.3.0 — ks-gen verify --host" \
  --notes-from-tag
```

The `--notes-from-tag` flag reuses the tag's annotated message as the
release body, which matches the rich tag message we created in the
verify session.

Verify:

```
gh release view v0.3.0 -R SupremeCommanderHedgehog/ks-gen
```

(No commit for this task — remote-only change.)

---

### Task B10: Add github-actions[bot] to the ruleset bypass list

**Files:** none (remote ruleset edit).

release-please's release PR is authored as `github-actions[bot]`.
With `required_signatures` enforced, that PR can't merge without a
bypass. Add the bot to the bypass list with `bypass_mode: pull_request`
so the bot can only bypass when merging a PR (not arbitrary pushes).

- [ ] **Step 1: Find the GitHub Actions bot integration id**

This is a constant across GitHub: `15368`. Reference:
https://github.com/orgs/community/discussions/13836

Verify (optional):

```
gh api /users/github-actions%5Bbot%5D --jq '{login, id}'
```

- [ ] **Step 2: Find the ruleset id**

```
RULESET_ID=$(gh api repos/SupremeCommanderHedgehog/ks-gen/rulesets --jq '.[] | select(.name == "main protection") | .id')
echo "ruleset id: $RULESET_ID"
```

- [ ] **Step 3: Update the ruleset to add the bot bypass**

```
cat > /tmp/main-ruleset-update.json <<JSON
{
  "name": "main protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["~DEFAULT_BRANCH"],
      "exclude": []
    }
  },
  "bypass_actors": [
    { "actor_type": "RepositoryRole", "actor_id": 5,     "bypass_mode": "always" },
    { "actor_type": "Integration",    "actor_id": 15368, "bypass_mode": "pull_request" }
  ],
  "rules": [
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [
          {"context": "ruff"},
          {"context": "test (3.11)"},
          {"context": "test (3.12)"},
          {"context": "test (3.13)"}
        ]
      }
    },
    { "type": "required_signatures" },
    { "type": "required_linear_history" },
    { "type": "deletion" },
    { "type": "non_fast_forward" }
  ]
}
JSON

gh api -X PUT repos/SupremeCommanderHedgehog/ks-gen/rulesets/$RULESET_ID \
  --input /tmp/main-ruleset-update.json
```

- [ ] **Step 4: Verify**

```
gh api repos/SupremeCommanderHedgehog/ks-gen/rulesets/$RULESET_ID --jq '.bypass_actors'
```

Expected: array contains both the `RepositoryRole`/5/always entry and
the `Integration`/15368/pull_request entry.

(No commit for this task — remote-only change.)

---

### Task B11: One-shot project backfill

**Files:** none (remote workflow run).

After PR-B merges, the `project-add.yml` workflow will only fire on
*new* issues/PRs. The existing 13 open issues (well, 12 — #5 was
closed in Task A7) need to be added manually.

- [ ] **Step 1: Confirm PR-B is merged so the workflow exists on `main`**

```
gh workflow list -R SupremeCommanderHedgehog/ks-gen
```

`project-add` should appear with state `active`.

- [ ] **Step 2: Loop over open issues and add to project**

```
PROJECT_URL='https://github.com/users/SupremeCommanderHedgehog/projects/<N>'

for n in $(gh issue list -R SupremeCommanderHedgehog/ks-gen --state open --limit 100 --json number --jq '.[].number'); do
  echo "adding #$n"
  gh project item-add <N> --owner SupremeCommanderHedgehog --url "https://github.com/SupremeCommanderHedgehog/ks-gen/issues/$n"
done
```

(`gh project` requires `gh` >= 2.39; verify with `gh --version`. If
not available, the backfill can also be done by adding each via the
Project's UI "+ Add item" search field.)

- [ ] **Step 3: Trigger the sync workflow for each backfilled issue**

The sync workflow normally fires on label change. Touching each issue
with `gh issue edit --add-label '<no-op-label>' --remove-label '<no-op-label>'`
is the cheapest trigger. Alternative: just wait for the next label
change naturally; existing items already have correct labels from
Task A7, so the only missed thing is the Priority/Area field values
on the project — which the user can fill in manually for these 12
backfilled items, or trigger the sync by re-applying an existing label
in a loop.

For thoroughness:

```
for n in $(gh issue list -R SupremeCommanderHedgehog/ks-gen --state open --limit 100 --json number --jq '.[].number'); do
  current=$(gh issue view "$n" --json labels --jq '.labels[].name' | tr '\n' ',' | sed 's/,$//')
  # Strip then re-add 'status:triage' to force a label event.
  gh issue edit "$n" --remove-label 'status:triage' || true
  gh issue edit "$n" --add-label 'status:triage'
done
```

(No commit for this task — remote-only action.)

---

### Task B12: Open PR-B and merge

**Files:** none (git ops).

- [ ] **Step 1: Push the feature branch**

```
git push -u origin impl/github-setup-automation
```

- [ ] **Step 2: Open the PR**

```
gh pr create -R SupremeCommanderHedgehog/ks-gen \
  --base main --head impl/github-setup-automation \
  --title "github-setup PR-B: automation (project, dependabot, codeql, sbom, release-please)" \
  --body "$(cat <<'EOF'
## Summary

Automation layer for the github-setup design: Dependabot configured
for pip + github-actions, dormant CodeQL workflow, SBOM generation on
release publish, three Project v2 automation workflows (add on open,
archive after 30 days, sync labels to fields), release-please for
changelog + GitHub Release automation.

## Related issue

Spec: `docs/superpowers/specs/2026-06-07-github-setup-design.md`.
Builds on PR-A foundation.

## Remote state changed (no commits)

- User-level Project v2 'ks-gen' created and linked to the repo
- Fine-grained PAT created and stored as KSGEN_PROJECT_TOKEN secret
- GitHub Release object created at v0.3.0 (the tag already existed)
- Ruleset 'main protection' updated to add github-actions[bot] bypass
  (mode: pull_request)
- 12 existing open issues backfilled into the project

## Test plan

- [ ] Local CI parity: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
- [ ] All workflow files validate via actionlint
- [ ] After merge: open a test issue and confirm it auto-adds to the project
- [ ] After merge: relabel a test issue with priority:p1 and confirm the Priority field updates
- [ ] After merge: confirm release-please opens its first release PR (will be a no-op until the next feat/fix lands)

## Checklist

- [ ] Conventional-commit subjects
- [ ] Commits GPG-signed
- [ ] CHANGELOG entry — N/A, release-please will manage CHANGELOG from here
- [ ] Documentation updated — yes, spec and going-public runbook
EOF
)"
```

- [ ] **Step 3: Wait for CI to pass**

```
gh pr checks --watch
```

- [ ] **Step 4: Merge to main**

```
git checkout main
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
  merge --no-ff -S -m "Merge branch 'impl/github-setup-automation'" impl/github-setup-automation
ruff check src tests && ruff format --check src tests && mypy && pytest -q
git push origin main
```

- [ ] **Step 5: Delete the feature branch**

```
git branch -d impl/github-setup-automation
```

- [ ] **Step 6: Final smoke tests after merge**

Open a throwaway issue:
```
n=$(gh issue create -R SupremeCommanderHedgehog/ks-gen \
  --title "test: smoke github-setup automation" \
  --body "Verifying project-add and label-sync work end-to-end. Will close immediately." \
  --label 'type:chore' --label 'area:meta' --label 'priority:p3' \
  | tail -1 | sed 's|.*/||')
echo "opened #$n"
```

Within 1–2 minutes:
- The issue should appear on the project board.
- Priority field should be `P3` and Area field should be `meta`.

Then close:
```
gh issue close $n -R SupremeCommanderHedgehog/ks-gen --reason 'not planned' --comment "smoke test done"
```

The closed-30d archive workflow will not act on this for 30 days; if
you want to trigger it sooner just delete the item from the project
manually.

Phase B complete. The repo is fully wired.

---

## Final verification

- [ ] **Step 1: Confirm `main` has both merges**

```
git log --oneline -8
```

Expected: most recent two commits are `Merge branch 'impl/github-setup-automation'`
followed by `Merge branch 'impl/github-setup-foundation'`, both signed.

- [ ] **Step 2: Confirm CI is green on main**

```
gh run list -R SupremeCommanderHedgehog/ks-gen --branch main -L 2
```

Both runs should show `success`.

- [ ] **Step 3: Confirm the ruleset is enforcing**

```
gh api repos/SupremeCommanderHedgehog/ks-gen/rulesets --jq '.[] | {name, enforcement, bypass: .bypass_actors}'
```

Expected: `"enforcement": "active"`, bypass list contains owner +
github-actions[bot].

- [ ] **Step 4: Confirm Dependabot is ready**

```
gh api repos/SupremeCommanderHedgehog/ks-gen/dependabot/secrets 2>&1 | head -3
```

(Just to confirm the endpoint responds. Dependabot itself will start
opening PRs on the next Monday 06:00 ET cycle.)

- [ ] **Step 5: Confirm release-please workflow exists**

```
gh workflow view release-please -R SupremeCommanderHedgehog/ks-gen
```

Status should be `active`. The release PR will open on the next push
to main that includes a `feat:` or `fix:` commit.

Done. The next user-visible action is to start writing `feat:` or
`fix:` commits — release-please takes care of the rest. When you want
to go public, follow `docs/going-public.md`.
