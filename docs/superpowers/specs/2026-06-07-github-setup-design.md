# GitHub setup — design

Date: 2026-06-07
Target release: pre-v0.4.0 (infra-only, no Python version bump)
Status: design approved, implementation plan to follow

## 1. Problem

`SupremeCommanderHedgehog/ks-gen` is a private GitHub repo with a minimal
setup: one CI workflow, default labels, no branch protection, no project
board, no security workflows, no release automation, no contributor docs.
It will eventually be made public. This change configures every
GitHub-side surface to be production-grade and public-ready in one
coherent rollout, with a clean handoff at the visibility flip.

## 2. Goals

- Track all work as GitHub issues attached to a single user-level Project
  v2 board with the same custom fields the labels expose.
- Automate the issue lifecycle: new issues auto-added to the project,
  closed items auto-archived 30 days after closing, label values mirrored
  into project fields.
- Harden CI: SHA-pinned actions, minimal `permissions`, concurrency
  cancellation, harden-runner audit, fast-path lint job.
- Lock `main`: required status checks, signed commits, linear history,
  no force-push and no deletion, with the owner on the bypass list until
  public launch.
- Add security tooling: Dependabot (pip + github-actions, grouped),
  CodeQL workflow (dormant on private, single-line activation at public),
  SBOM on every release, private vulnerability reporting.
- Automate releases via release-please: changelog managed from
  conventional commits, GitHub Releases auto-created, SBOM auto-attached.
- Provide all public-readiness docs: SECURITY, CONTRIBUTING, CODE_OF_CONDUCT,
  expanded README, repo metadata (topics, description, social).
- Make every public-launch action a one-step item in a runbook so the
  switch from private to public is mechanical, not a scramble.

## 3. Non-goals (deferred, called out in §11)

- Codecov / coverage measurement and reporting.
- GitHub Apps (PAT-based automation only).
- Multi-repo project (single-repo binding).
- CODEOWNERS / FUNDING.yml / sponsors.
- Re-signing tags after release-please takes over.
- Migrating historical pre-v0.3.0 changelog entries.
- DCO / sign-off requirements.
- Custom auto-close-from-PR automation (relying on built-in).
- Auto-merging Dependabot PRs (separate brainstorm later).
- Repository templates.

## 4. Implementation strategy

Two PRs in order:

- **PR-A (foundation):** repo metadata + docs, issue/PR templates, label
  retag, CI hardening, branch ruleset (with owner on bypass list).
- **PR-B (automation):** Project v2 setup steps documented, project
  workflows, Dependabot, CodeQL (dormant), SBOM, release-please.

The branch ruleset lands in PR-A but with the owner bypass-listed from
day one, so PR-B doesn't get stuck behind PR-A's own requirements.

## 5. Repo metadata, docs, discoverability

### 5.1 New top-level files

- `SECURITY.md` — supported-versions table (`0.3.x` yes, earlier no),
  pointer to GitHub's private vulnerability reporting, out-of-band email
  + PGP fingerprint, 5-business-day response SLA, coordinated disclosure
  language.
- `CONTRIBUTING.md` — dev setup (`pip install -e ".[dev]"`, pre-commit
  install), CI parity chain
  (`ruff check && ruff format --check && mypy && pytest -q`), commit
  convention (conventional commits, signed), branch naming
  (`impl/v<version>-<topic>`), good-bug-report guidance.
- `CODE_OF_CONDUCT.md` — Contributor Covenant v2.1.

### 5.2 README badges (top of `README.md`)

CI status, license (Apache-2.0), Python versions supported, latest
release (auto-updated by release-please), GitHub Issues count,
dependency-graph badge. No Codecov badge.

### 5.3 Repository-level settings (via `gh api`)

- `description`: `Remote-safe DISA STIG kickstart generator for AlmaLinux 9`
- `topics`: `kickstart`, `almalinux`, `stig`, `oscap`, `compliance`,
  `disa`, `python`, `security-hardening`
- `has_wiki`: `false`
- `has_discussions`: `true`
- `delete_branch_on_merge`: `true`
- Private vulnerability reporting: `enabled`

### 5.4 `pyproject.toml` extensions

`[project.urls]` adds `Homepage`, `Documentation`, `Issues`,
`Changelog`. `[project]` gains `keywords` and `classifiers` (POSIX/Linux,
Topic :: System :: Installation/Setup, Apache-2.0 license classifier).

## 6. Issue forms, PR template, label taxonomy

### 6.1 Issue forms at `.github/ISSUE_TEMPLATE/`

YAML issue forms (not markdown templates):

- `bug_report.yml` — required fields: ks-gen version (auto-prompt
  `ks-gen --version`), Python version, command run, expected vs. actual,
  full traceback, `host.yaml` if relevant. Auto-applies `type:bug` +
  `status:triage`.
- `feature_request.yml` — required: problem statement, proposed solution,
  alternatives, acceptance criteria. Auto-applies `type:feature` +
  `status:triage`.
- `documentation.yml` — required: doc file/section affected, what's
  confusing or missing, suggested fix. Auto-applies `type:docs` +
  `status:triage`.
- `config.yml` — `blank_issues_enabled: false`. Contact links: "Security
  issues → private reporting URL", "Questions → Discussions".

### 6.2 PR template at `.github/pull_request_template.md`

Sections: Summary, Related issue (`Closes #`), Test plan (with the
CI parity command as a checkbox), Checklist (conventional-commit subject,
signed commits, CHANGELOG entry or release-please pickup, docs updated).

### 6.3 Label taxonomy

Replace defaults. Prefixed labels, colors chosen so prefixes form coherent
palettes.

| Prefix | Labels |
|---|---|
| `type:` | `bug`, `feature`, `docs`, `refactor`, `security`, `chore`, `test` |
| `area:` | `verify`, `iso`, `wizard`, `disk`, `cli`, `lint`, `templates`, `ci`, `deps`, `meta` |
| `priority:` | `p0`, `p1`, `p2`, `p3` |
| `status:` | `triage`, `blocked`, `needs-info`, `in-progress`, `ready-to-merge` |
| (flags) | `good-first-issue`, `help-wanted`, `breaking-change`, `dependencies` (auto, from Dependabot), `autorelease: pending`, `autorelease: tagged`, `autorelease: published` (auto, from release-please — exact names release-please applies) |

Labels deleted from defaults: `duplicate`, `invalid`, `wontfix`,
`question`, generic `bug`/`enhancement`/`documentation` (replaced by
prefixed equivalents).

### 6.4 Existing 13 issues re-labeled in PR-A

- `#5` (verify --host) — already shipped in v0.3.0; close with a comment
  pointing at the v0.3.0 release.
- `#6` iso bootloader → `type:feature`, `area:iso`, `priority:p2`.
- `#7` LUKS → `type:feature`, `area:disk`, `priority:p2`.
- `#8` disk.layout → `type:feature`, `area:disk`, `priority:p1`.
- `#9` wizard expansion → `type:feature`, `area:wizard`, `priority:p2`.
- `#10–#17` (verify deferrals) → `type:feature`, `area:verify`, mostly
  `priority:p3` (operator-driven re-prioritization later).

## 7. GitHub Project v2 + automation

### 7.1 Project shape

- Owner: user (`SupremeCommanderHedgehog`).
- Title: `ks-gen`.
- Linked repository: `SupremeCommanderHedgehog/ks-gen` (single-repo).
- README description: "Issue & PR tracking for the ks-gen kickstart
  generator."

### 7.2 Custom fields

| Field | Type | Options |
|---|---|---|
| `Status` | Single-select | `Backlog`, `Ready`, `In progress`, `In review`, `Done` |
| `Priority` | Single-select | `P0`, `P1`, `P2`, `P3` |
| `Area` | Single-select | `verify`, `iso`, `wizard`, `disk`, `cli`, `lint`, `templates`, `ci`, `deps`, `meta` |
| `Iteration` | Iteration | 2-week iterations, starts the Monday after creation |
| `Estimate` | Number | Optional |

`Priority` and `Area` options mirror the `priority:*` and `area:*` label
sets so the sync workflow has a 1:1 mapping.

### 7.3 Views (saved at project creation)

1. **Board (default)** — grouped by `Status`, kanban layout.
2. **Triage** — table, filter `Status=Backlog AND label:status:triage`,
   sorted by created-at ascending.
3. **By area** — board, grouped by `Area`.
4. **Roadmap** — roadmap layout, swimlanes by `Area`, x-axis `Iteration`.
5. **Closed (last 30 days)** — table, filter `is:closed AND
   closed-at > -30d`. The archive workflow's inspection queue.

### 7.4 Automation workflows at `.github/workflows/`

- `project-add.yml` — triggers on `issues: [opened, transferred]` and
  `pull_request_target: [opened]`. Uses `actions/add-to-project@v1` to add
  the new item to the project. Token: `secrets.KSGEN_PROJECT_TOKEN`.

- `project-archive-closed.yml` — `schedule: cron '0 6 * * *'` (06:00 UTC
  daily). GraphQL query for project items where the linked issue/PR is
  closed and `closedAt < now() - 30 days`; sets `archived=true` on each.
  Idempotent. Token: `secrets.KSGEN_PROJECT_TOKEN`.

- `project-sync-labels.yml` — triggers on `issues: [labeled, unlabeled]`
  and `pull_request_target: [labeled, unlabeled]`. Reads new label set,
  computes target `Priority` and `Area` field values, writes them to the
  project item via GraphQL. Labels are authoritative; the field is
  one-way-synced from labels. Token: `secrets.KSGEN_PROJECT_TOKEN`.

### 7.5 PAT setup (manual, documented)

The default `GITHUB_TOKEN` cannot reach user-level projects. A
fine-grained PAT is required with:

- Repository access: `SupremeCommanderHedgehog/ks-gen` only.
- Repository permissions: `Contents: Read`, `Metadata: Read`.
- Account permissions: `Projects: Read and write`.
- Expiry: 1 year, with a calendar reminder to rotate.

The PAT is stored as repo secret `KSGEN_PROJECT_TOKEN`. PR-B includes a
one-shot manual backfill step: invoke `project-add.yml` once via
`workflow_dispatch` to attach the existing 13 open issues.

### 7.6 Why a PAT and not a GitHub App

App setup is heavier for a solo dev. A PAT works for this scope. Revisit
if app permissions ever change in a way that makes the PAT model break.

## 8. CI hardening + branch ruleset

### 8.1 `ci.yml` changes (in place)

- **SHA-pin every action**, with the human-readable version as a trailing
  comment:
  ```yaml
  - uses: actions/checkout@<40-char-sha> # v4.1.7
  - uses: actions/setup-python@<40-char-sha> # v5.1.1
  ```
- Top-of-workflow `permissions: contents: read` stays. Per-job
  `permissions:` explicitly declared with `id-token: none`,
  `actions: none`, `checks: none` so the principle is locked in for any
  jobs added later.
- Concurrency:
  ```yaml
  concurrency:
    group: ci-${{ github.workflow }}-${{ github.ref }}
    cancel-in-progress: ${{ github.event_name == 'pull_request' }}
  ```
- `step-security/harden-runner` as the first step in every job, in
  `audit` mode to establish a baseline; can be flipped to `block` later.
- Persist test artifacts on failure: pytest tail + any `.ambr` snapshot
  diffs uploaded as a workflow artifact.
- Add a fast-path `ruff` job that runs once (not matrixed) so format
  violations fail in seconds. Matrix job for the full chain stays.

### 8.2 Required status checks

The job names that must succeed for `main` merges:

- `ruff` (fast-path)
- `test (3.11)`
- `test (3.12)`
- `test (3.13)`

### 8.3 Branch protection ruleset on `main`

Created via `gh api repos/.../rulesets`. Schema:

```
Name: main protection
Target: branch = main
Enforcement: active

Rules:
  - required_status_checks:
      strict: true
      checks: ["ruff", "test (3.11)", "test (3.12)", "test (3.13)"]
  - required_signatures: true
  - required_linear_history: true
  - deletion: forbidden
  - non_fast_forward: forbidden
  - creation: allowed
  - update: allowed (with bypass list)
  - pull_request: NOT enabled in PR-A; enabled at public-launch

Bypass actors:
  - role: Repository admin, mode: always (owner)
  - actor: github-actions[bot], mode: pull_request (for release-please)
```

Today the owner bypasses everything, so the local `git merge --no-ff` +
`git push` flow keeps working. Required signatures still applies in
practice because the owner always signs anyway. The bot bypass on
`pull_request` is so release-please's release PR can merge without
human-side signature checks failing (the bot's commits aren't signed
with the owner's key — see §10).

### 8.4 Solo-dev escape hatch

`gh ruleset` makes flipping bypass on/off a one-liner if an emergency
fix needs to land without CI.

## 9. Security scanning

### 9.1 `.github/dependabot.yml`

```yaml
version: 2
updates:
  - package-ecosystem: pip
    directory: /
    schedule:
      interval: weekly
      day: monday
      time: "06:00"
      timezone: America/New_York
    open-pull-requests-limit: 5
    labels: [type:chore, dependencies, area:deps]
    commit-message:
      prefix: chore(deps)
      include: scope
    groups:
      dev-deps:
        patterns: ["pytest*", "ruff*", "mypy*", "syrupy*", "types-*"]
      runtime-deps:
        patterns: ["*"]
        exclude-patterns: ["pytest*", "ruff*", "mypy*", "syrupy*", "types-*"]

  - package-ecosystem: github-actions
    directory: /
    schedule:
      interval: weekly
      day: monday
    open-pull-requests-limit: 5
    labels: [type:chore, dependencies, area:ci]
    commit-message:
      prefix: chore(actions)
```

The github-actions ecosystem keeps the SHA-pinned actions from §8.1
fresh. Grouping minimizes weekly PR noise.

### 9.2 CodeQL workflow at `.github/workflows/codeql.yml`

Wired now, dormant until public launch:

```yaml
name: codeql
on:
  workflow_dispatch:
  # Activate at public launch — see docs/going-public.md:
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
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        language: [python]
    steps:
      - uses: actions/checkout@<sha> # v4
      - uses: github/codeql-action/init@<sha> # v3
        with:
          language: ${{ matrix.language }}
          queries: security-extended,security-and-quality
      - uses: github/codeql-action/analyze@<sha> # v3
```

`workflow_dispatch` lets the workflow be smoke-tested on demand even on
a private repo (won't upload alerts but proves the YAML parses and the
actions resolve). The 5-line activation block is gated by a comment that
the going-public runbook (§10) tells you to uncomment.

### 9.3 SBOM workflow at `.github/workflows/sbom.yml`

```yaml
name: sbom
on:
  release:
    types: [published]
permissions:
  contents: write
jobs:
  cyclonedx:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<sha>
        with: { ref: ${{ github.event.release.tag_name }} }
      - uses: actions/setup-python@<sha>
        with: { python-version: '3.13' }
      - run: pip install -e . cyclonedx-bom==<pinned>
      - run: cyclonedx-py environment --of json -o sbom-${{ github.event.release.tag_name }}.cdx.json
      - uses: softprops/action-gh-release@<sha>
        with:
          tag_name: ${{ github.event.release.tag_name }}
          files: sbom-${{ github.event.release.tag_name }}.cdx.json
```

CycloneDX JSON format. Triggers on `release: published` (release-please
publishes; SBOM attaches).

### 9.4 Private vulnerability reporting

Turn on via:

```bash
gh api -X PATCH repos/SupremeCommanderHedgehog/ks-gen \
  -f security_and_analysis[private_vulnerability_reporting][status]=enabled
```

Free for any repo, public or private. Lets reporters draft an advisory
in a private fork before public disclosure.

### 9.5 Secret scanning + push protection

Free for public repos only. Plan: turn on at public-launch:

```bash
gh api -X PATCH repos/SupremeCommanderHedgehog/ks-gen \
  -F security_and_analysis[secret_scanning][status]=enabled \
  -F security_and_analysis[secret_scanning_push_protection][status]=enabled
```

Step in the going-public runbook (§10).

### 9.6 `SECURITY.md` content

```markdown
# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.3.x   | yes       |
| < 0.3   | no        |

## Reporting a vulnerability

Use GitHub's private vulnerability reporting:
https://github.com/SupremeCommanderHedgehog/ks-gen/security/advisories/new

For out-of-band contact: <security-email> (PGP <fingerprint>).
Do not open a public issue for security problems.

Initial response within 5 business days. Coordinated disclosure
timing once a fix lands.
```

The `<security-email>` and `<fingerprint>` placeholders get concrete
values during PR-A implementation (the contact email is whichever address
the owner wants public; the PGP fingerprint is the existing
`BE707B220C995478`).

## 10. release-please

### 10.1 Configuration files at repo root

`.release-please-manifest.json`:
```json
{".": "0.3.0"}
```

`release-please-config.json`:
```json
{
  "packages": {
    ".": {
      "release-type": "python",
      "package-name": "ks-gen",
      "changelog-path": "CHANGELOG.md",
      "changelog-sections": [
        {"type": "feat",     "section": "Features"},
        {"type": "fix",      "section": "Bug Fixes"},
        {"type": "perf",     "section": "Performance"},
        {"type": "refactor", "section": "Refactoring"},
        {"type": "docs",     "section": "Documentation"},
        {"type": "test",     "section": "Tests", "hidden": true},
        {"type": "ci",       "section": "CI", "hidden": true},
        {"type": "chore",    "section": "Chores", "hidden": true},
        {"type": "style",    "section": "Style", "hidden": true}
      ],
      "extra-files": ["pyproject.toml"],
      "include-component-in-tag": false,
      "draft": false,
      "prerelease": false
    }
  },
  "$schema": "https://raw.githubusercontent.com/googleapis/release-please/main/schemas/config.json"
}
```

`release-type: python` makes release-please update `pyproject.toml`'s
`version =` line and `CHANGELOG.md` together in the release PR.

### 10.2 Workflow at `.github/workflows/release-please.yml`

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
    steps:
      - uses: googleapis/release-please-action@<sha> # v4.x
        with:
          config-file: release-please-config.json
          manifest-file: .release-please-manifest.json
          token: ${{ secrets.GITHUB_TOKEN }}
```

### 10.3 Release flow once enabled

1. A `feat:` or `fix:` commit lands on main.
2. release-please opens or updates a long-lived PR titled
   `chore(main): release X.Y.Z` with the CHANGELOG diff and the
   `pyproject.toml` version bump.
3. The release PR is merged when ready to ship.
4. release-please creates the git tag, publishes a GitHub Release, and
   the SBOM workflow (§9.3) fires.

### 10.4 Migration from current tag scheme

The signed tag `v0.3.0` exists but has no GitHub Release object. PR-B
creates one manually before enabling the workflow:

```bash
gh release create v0.3.0 --notes-from-tag --verify-tag
```

This gives release-please a "last release" anchor for the next bump.
Pre-v0.3.0 changelog entries stay in `CHANGELOG.md` as-is; release-please
only owns from v0.3.0 forward.

### 10.5 Signed-commit interaction (accepted tradeoff)

release-please opens its release PR as `github-actions[bot]`. Those
commits are not signed by the owner's GPG key. The branch ruleset's
`required_signatures` rule needs an exception so release PRs can merge.

Choice: add `github-actions[bot]` to the ruleset bypass list for
`pull_request` action only. Documented in `SECURITY.md` so consumers
know release PR commits are GitHub-attested rather than GPG-signed.

### 10.6 Signed-tag interaction (accepted tradeoff)

release-please does not GPG-sign the tags it creates. Today's tags
(`v0.1.0` through `v0.3.0`) are all owner-signed. From v0.3.1 forward,
tags will be lightweight (GitHub-attested via TLS + the merge commit
being signed gives equivalent provenance).

Documented in `SECURITY.md`. Re-signing tags after release-please is a
deferred follow-up (§3 non-goal); if you ever want it back, the path is a
post-release workflow step using a stored GPG key.

## 11. Public-launch runbook

Lives at `docs/going-public.md`, lands in PR-A. Steps you walk through
once at the visibility flip:

1. Settings → General → Change visibility → Public.
2. Enable secret scanning + push protection (§9.5 `gh api` commands).
3. Enable CodeQL on push/PR: uncomment the 5 trigger lines in
   `.github/workflows/codeql.yml`.
4. Tighten the branch ruleset:
   - Remove the owner from `bypass_actors`.
   - Enable `pull_request` rule with
     `required_approving_review_count: 1` (owner can self-approve until
     collaborators exist).
5. Revisit Codecov / coverage choice (currently opted out).
6. Smoke test: `gh workflow run codeql.yml` and confirm green before the
   first public push.
7. Open a Discussion post in the new Announcements category.

## 12. References

- Spec lives at this file (`docs/superpowers/specs/2026-06-07-github-setup-design.md`).
- Implementation plan to follow at
  `docs/superpowers/plans/2026-06-07-github-setup-implementation.md`.
- Conventional Commits: https://www.conventionalcommits.org/
- release-please:
  https://github.com/googleapis/release-please-action
- harden-runner:
  https://github.com/step-security/harden-runner
- Issue forms schema:
  https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-githubs-form-schema
- Rulesets API:
  https://docs.github.com/en/rest/repos/rules
- Project v2 GraphQL:
  https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/automating-projects-using-actions
