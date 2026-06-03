# CLAUDE.md — ks-gen

Project-specific notes for Claude Code sessions in this repo. Global
instructions (signing key, commit author, etc.) live in
`~/.claude/CLAUDE.md` and still apply.

## Local CI parity check — run before pushing

CI (`.github/workflows/ci.yml`) gates on four commands in this order:

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Run the same chain locally before claiming "lint clean" / "ready for PR"
/ "tests green" and before `git push`. Running only `ruff check` misses
formatting drift — `ruff format --check` is a separate check that has
bounced a PR before (2026-06-02, PR #2).

If `ruff format --check` fails, fix with `ruff format src tests`, verify
with `--check` again, then commit as `style:`.

## Snapshot tests

Golden snapshots use syrupy and live at `tests/golden/__snapshots__/`.
Regenerate after intentional output changes:

```bash
pytest tests/golden/ --snapshot-update
```

Inspect the diff before committing — a regen should change exactly what
the rule change predicts and nothing else.
