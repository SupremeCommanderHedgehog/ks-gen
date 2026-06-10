# Going-public runbook

When you decide to flip `SupremeCommanderHedgehog/ks-gen` from private
to public, walk this checklist in order. None of these steps are
automated; each is one short shell command or a click in the GitHub UI.

## 1. Flip visibility

GitHub UI → **Settings → General → Danger Zone → Change visibility →
Make public**. Confirm the repo name.

## 2. Enable secret scanning + push protection

Secret scanning and push protection are free for public repos. Both
must be turned on after the visibility flip:

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

Both `secret_scanning` and `secret_scanning_push_protection` should
report `status: enabled`.

## 3. Enable private vulnerability reporting

This endpoint returns 404 on personal-account private repos but works
once the repo is public:

```bash
gh api -X PUT repos/SupremeCommanderHedgehog/ks-gen/private-vulnerability-reporting
```

Verify:

```bash
gh api repos/SupremeCommanderHedgehog/ks-gen/private-vulnerability-reporting
```

Expected: `{"enabled":true}`.

This is the channel `SECURITY.md` already points at — `https://github.com/SupremeCommanderHedgehog/ks-gen/security/advisories/new`.

## 4. Verify CodeQL triggers are active

Confirm `.github/workflows/codeql.yml` has all four trigger keys
active (not commented out):

```yaml
on:
  workflow_dispatch:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: '17 7 * * 1'  # Mondays 07:17 UTC
```

These were activated in the going-public sweep (commit `86753fd`,
PR #45). If a future change reverts any of them, restore them and
PR with `ci(codeql): re-enable scheduled and PR scans`.

**Code Scanning enable.** On a public repo, Code Scanning auto-enables
on the first successful SARIF upload from this workflow — no UI step or
API call is required. On a private personal repo without GitHub
Advanced Security the upload step fails with `Code scanning is not
enabled for this repository. Please enable code scanning in the
repository settings.` That means **do not attempt to smoke-test the
codeql workflow before step 1 (visibility flip) is complete** — the
analyze step will run cleanly but the upload will hard-fail.

## 5. Tighten the branch ruleset

Find the ruleset id:

```bash
gh api repos/SupremeCommanderHedgehog/ks-gen/rulesets \
  --jq '.[] | select(.name == "main protection") | .id'
```

Edit the ruleset to remove ALL bypass actors (including the maintainer)
and require PRs. Three constraints to know about before reading the JSON
below — they are why the values look like they do:

1. **Rebase-merge + `required_signatures` is a hard GitHub deadlock.**
   Rebase produces new commits that GitHub cannot sign automatically,
   and `required_signatures` then refuses the merge with
   `"Base branch requires signed commits. Rebase merges cannot be
   automatically signed by GitHub."` Neither `--admin` nor bypass
   entries override this — it's a server-side precondition. Resolution:
   constrain `allowed_merge_methods` to `["squash"]`. Squash commits
   are signed by GitHub's web-flow key, which satisfies
   `required_signatures` and preserves linear history.

2. **`required_approving_review_count: 1` self-blocks a solo
   maintainer.** GitHub will not let you approve your own PR, so a
   1-review requirement on a solo repo locks you out of every merge.
   Set it to `0` until a second collaborator joins.

3. **`actor_type: "Integration"` bypass entries do not work on
   personal-account repos — public OR private.** GitHub returns
   `422: must be part of the ruleset source or owner organization` in
   both states. (This contradicts older guidance suggesting it works
   once the repo is public. It does not, on personal accounts.) The
   only workable model on a personal repo is `bypass_actors: []` — the
   maintainer goes through the same gate as everyone else.

```bash
RULESET_ID=<id from above>

gh api -X PUT repos/SupremeCommanderHedgehog/ks-gen/rulesets/$RULESET_ID \
  --input - <<'JSON'
{
  "name": "main protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "bypass_actors": [],
  "rules": [
    { "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [
          {"context": "ruff"},
          {"context": "test (3.11)"},
          {"context": "test (3.12)"},
          {"context": "test (3.13)"},
          {"context": "analyze (python)"}
        ]
      }
    },
    { "type": "required_signatures" },
    { "type": "required_linear_history" },
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "pull_request",
      "parameters": {
        "allowed_merge_methods": ["squash"],
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": true
      }
    }
  ]
}
JSON
```

This makes every change to `main` go through a PR that passes ruff,
the three test matrix legs, and CodeQL `analyze (python)`. All commits
on `main` are signed (squash commits by GitHub's web-flow key, other
commits by the contributor). Linear history is preserved. release-please
release PRs go through the same gate — squash-merge them manually.

## 6. Reconsider Codecov / coverage

You opted out of Codecov during the github-setup design. If usage
justifies it now, revisit by following Codecov's setup docs and adding
a step to the `test` job in `.github/workflows/ci.yml`.

## 7. Consider flipping harden-runner to `block` mode

`step-security/harden-runner` starts in `audit` mode, which only logs
egress. Once you have a baseline of expected destinations from past
audit-mode runs, you can flip to `block` mode to prevent unexpected
egress (e.g., a compromised dependency calling home). Edit each
`egress-policy: audit` to `egress-policy: block`, add an
`allowed-endpoints:` block, then test on a branch — if a step
legitimately needs egress to an unlisted host, the run fails and you
add the host.

**State as of 2026-06-09:**

- `.github/workflows/ci.yml` — flipped to `block` in PR #46. The
  9-endpoint allowlist there (`agent.api.stepsecurity.io`,
  `api.github.com`, `codeload.github.com`, `files.pythonhosted.org`,
  `github.com`, `objects.githubusercontent.com`,
  `prod.app-api.stepsecurity.io`, `pypi.org`,
  `results-receiver.actions.githubusercontent.com`) is a reusable
  starting point for any Python `pip install -e .[dev]` + ruff + mypy +
  pytest job.
- `.github/workflows/codeql.yml` — still `audit`. CodeQL needs
  additional hosts (the CodeQL bundle CDN, `uploads.github.com` for
  SARIF). Tighten in a separate PR.
- `.github/workflows/release-please.yml` — still `audit`. Needs the
  npm registry. Tighten in a separate PR.

## 8. Smoke-test CodeQL

> **Prerequisite:** step 1 (visibility flip) must be complete. See the
> note under step 4 — on a private personal repo the upload step
> hard-fails with `Code scanning is not enabled for this repository`,
> regardless of whether the action SHAs and analyze step are healthy.

```bash
gh workflow run codeql.yml -R SupremeCommanderHedgehog/ks-gen
```

Wait for the run to complete:

```bash
gh run list --workflow codeql.yml -L 1
```

Confirm green before announcing.

## 9. Open an announcement

In Discussions (which was enabled in PR-A), open a post in the
**Announcements** category titled "ks-gen is now public!". Link the
README, the latest release, and the security policy.
