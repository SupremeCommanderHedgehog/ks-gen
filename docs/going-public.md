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

## 4. Activate CodeQL on push and PR

Edit `.github/workflows/codeql.yml` (created in PR-B). Find this block
near the top:

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

Uncomment every line in that block (six lines — the three trigger keys
plus their three inline values). Commit on a branch, open a PR titled
`ci(codeql): activate scheduled and PR scans`, merge.

## 5. Tighten the branch ruleset

Find the ruleset id:

```bash
gh api repos/SupremeCommanderHedgehog/ks-gen/rulesets \
  --jq '.[] | select(.name == "main protection") | .id'
```

Edit the ruleset to remove the maintainer bypass and add a PR
requirement. The maintainer bypass actor id was `5` (Repository admin
role); the GitHub Actions bot bypass entry stays so release-please's
release PRs can still merge.

```bash
RULESET_ID=<id from above>

gh api -X PUT repos/SupremeCommanderHedgehog/ks-gen/rulesets/$RULESET_ID \
  --input - <<'JSON'
{
  "name": "main protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "bypass_actors": [
    { "actor_type": "Integration", "actor_id": 15368, "bypass_mode": "pull_request" }
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
You can self-approve as the owner until other collaborators exist.

## 6. Reconsider Codecov / coverage

You opted out of Codecov during the github-setup design. If usage
justifies it now, revisit by following Codecov's setup docs and adding
a step to the `test` job in `.github/workflows/ci.yml`.

## 7. Consider flipping harden-runner to `block` mode

The CI workflow runs `step-security/harden-runner` in `audit` mode,
which only logs egress. Once you have a baseline of expected egress
destinations from past audit-mode runs, you can flip to `block` mode
to prevent unexpected egress (e.g., a compromised dependency calling
home). Edit each `egress-policy: audit` to `egress-policy: block`,
then test on a branch — if a step legitimately needs egress to a host
you haven't listed, you'll see it fail and can add the host to an
allow-list.

## 8. Smoke-test CodeQL

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
