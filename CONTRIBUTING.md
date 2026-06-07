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
a blank line; do not append `Co-Authored-By:` trailers (this includes
AI-generated trailers some code-assistant tools add by default — turn
them off in your tool's config).

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
self-contained implementation. Start there if you are new to the
codebase.

## Code of conduct

Participation is governed by `CODE_OF_CONDUCT.md`.
