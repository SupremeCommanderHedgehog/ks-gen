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

## Code review — run /code-review before shipping

Run `/code-review` on the working diff before shipping ANY code change —
before `git push`, opening a PR, or merging. "Shipping" means the change
leaves your local working tree for others: a push, a PR, or a merge.

This is in addition to (not a replacement for) the CI parity check above:
CI catches lint/type/test regressions; `/code-review` catches correctness
bugs and reuse/simplification issues the automated gates don't. Address or
consciously dismiss each finding before shipping.

This applies to fixes made live during an install/debug session too — a
live install/debug session shipped two `%post`/tailoring bugs
(chpasswd `$6` abort, inert `cfg.exceptions`) that a diff review would
have flagged before they reached a real install.

## Snapshot tests

Golden snapshots use syrupy and live at `tests/golden/__snapshots__/`.
Regenerate after intentional output changes:

```bash
pytest tests/golden/ --snapshot-update
```

Inspect the diff before committing — a regen should change exactly what
the rule change predicts and nothing else.

## Debugging a generated install

- Console login is impossible by design — root + admin both `passwd -l`, sshd
  `PasswordAuthentication no`. Only SSH-with-key works; recovery without
  network requires GRUB emergency shell (`rd.break=switch_root`).
- Anaconda's "error at line N" dialog points at the `%post` block header,
  not the failing command. Real failure is in `/mnt/sysimage/root/ks-post.log`
  — last `+ <cmd>` line under `set -euxo pipefail`. Switch to tty2 before
  dismissing the dialog.
- For debug rebuilds, edit `src/ks_gen/iso/_menu.py` to drop `quiet` and add
  `inst.text rd.info`. Don't commit it.

## Install-regression harness (`.scratch/install-regression/`)

An on-demand end-to-end install regression harness lives under
`.scratch/install-regression/` (gitignored, per-developer). It runs the
full `ks-gen gen` → `ks-gen iso` → QEMU EFI boot → anaconda install →
SSH-in → smoke-check pipeline. Closed issue #57 (and that issue's final
comment) document the full local-only recipe — bootstrap the harness on
a new machine from there. Wall-clock: ~30-90 min on TCG.

**When to recommend running it.** Only when the diff plausibly affects
what anaconda does. Specifically:
- `src/ks_gen/iso/**` — builder, bootloader, _menu, xorriso pipeline
- `src/ks_gen/rules/*.py` — new/changed `emit_packages`, `emit_post`,
  or `emit_tailoring` (anything that writes shell into `%post` or
  contributes to `%packages`)
- `src/ks_gen/templates/ks.cfg.j2` or `templates/partials/*.j2`
- `src/ks_gen/writer.py` bundle composition changes
- `src/ks_gen/config.py` defaults for fields the install consumes
  (network, disk, packages)

**Do NOT recommend** for docs, CLI/typer changes that don't reach the
generated kickstart, test-only changes, or `verify` command work. The
30-90 min run isn't worth it for "extra confidence" — recommend it when
a real bug class would slip through the unit tests, not as a tax.

Don't run it yourself in a normal session — surface the recommendation
and let the user decide.
