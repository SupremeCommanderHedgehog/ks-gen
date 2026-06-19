# Ubuntu STIG Autoinstall Phase 3.1 — `banner_text` Port Design

> **Status:** Approved design for phase 3.1 of #81. Scope-matched to phase 3.0's
> "defer tailoring + exception" pattern; the audit-story backfill (datastream
> survey + tailoring + exception for all ported ubuntu rules at once) is a
> separate later PR.

## Goal

Port the `banner_text` rule to `ubuntu2404` so an ubuntu autoinstall bundle
writes the civilian banner to the right places at install time, just as the
alma9 bundle already does. Keep the auditor-facing English and the operator
config surface (`cfg.banner.text`, `cfg.banner.apply_to`) identical across
distros.

## Locked decisions (from brainstorming)

| Decision | Choice | Reason |
| -------- | ------ | ------ |
| PR scope | `emit_post` only; `emit_tailoring` / `exception_entry` / `emit_packages` return empty / `None` / empty | Mirrors phase 3.0's locked decision #5. Datastream survey for `ssg-ubuntu2404-ds.xml` rule IDs lands later as a coordinated "ubuntu audit story" PR covering several ported rules at once. |
| Banner-target map | `issue` → `/etc/issue`, `issue_net` → `/etc/issue.net`, `motd` → `/etc/ssh/sshd-banner`, `gdm` → no-op | Matches spec §6 of `2026-06-18-ubuntu-stig-autoinstall-design.md`. On Ubuntu the motd is dynamic and not the canonical SSH login channel; sshd-banner is the file an sshd_config drop-in will point `Banner` at in a later phase. |
| Heredoc style | `<<'__KS_GEN_EOF__'` matching alma | Single-quoted heredoc neutralizes shell expansion inside banner text; same delimiter so shlex.quote round-trip behavior is identical to alma. |
| Late-command wrapping | One `curtin in-target ... bash -c` per rule, multi-line body wrapped by existing `_format_late_commands` | Phase 3.0 infrastructure already handles multi-line bash bodies in YAML literal blocks; no skeleton changes required. |
| Meta sharing | Reuse `src/ks_gen/rules/_meta/banner_text.py` unchanged | `ID`, `SUMMARY`, `DEPENDS_ON`, exception strings are distro-agnostic by design. |

## Architecture

### Rule module

`src/ks_gen/rules/ubuntu2404/banner_text.py` mirrors the shape of
`src/ks_gen/rules/alma9/banner_text.py`:

```python
_TARGET = {
    "issue": "/etc/issue",
    "issue_net": "/etc/issue.net",
    "motd": "/etc/ssh/sshd-banner",  # divergence from alma's "/etc/motd"
}

class _Rule:
    id, summary, depends_on, stig_rules_affected  # from _meta + empty list

    def applies(self, cfg) -> bool:
        return True

    def emit_tailoring(self, cfg) -> list[TailoringOp]:
        return []   # deferred — see audit-story PR

    def emit_post(self, cfg) -> str:
        # same heredoc loop as alma9, just over the ubuntu _TARGET map
        ...

    def emit_packages(self, cfg) -> list[str]:
        return []   # banner files are written by coreutils; nothing to install

    def exception_entry(self, cfg) -> ExceptionEntry | None:
        return None  # deferred — see audit-story PR
```

`stig_rules_affected` is `[]` for this PR (the field is informational for
`exceptions.md`; without a real tailoring/exception entry there's nothing to
populate).

### Behaviour on existing operator config

`cfg.banner.apply_to` defaults to `[issue, issue_net, motd, gdm]`. The
ubuntu rule iterates the same list:
- `issue` and `issue_net` produce identical bash to alma (same heredoc, same
  chmod).
- `motd` writes to `/etc/ssh/sshd-banner` instead of `/etc/motd`. Operators
  reading the rendered late-command see the divergence and can adjust
  `apply_to` per host if they want only some channels.
- `gdm` is skipped (`continue`) — same as alma. Ubuntu Server has no GDM;
  the entry is preserved for cross-distro config portability and will be
  meaningful once the (deferred) tailoring entry disables the matching
  oscap rule.

### Out of scope (later PRs)

- **sshd_config drop-in** that points `Banner` at `/etc/ssh/sshd-banner`.
  That's `ssh_config_apply`'s responsibility and will land with that rule's
  ubuntu2404 port in a later phase.
- **Datastream survey + tailoring + exception_entry backfill.** Coordinated
  PR after `ssg-ubuntu2404-ds.xml` rule IDs for the banner+DoD-text rules are
  enumerated. Will retroactively populate `emit_tailoring` and
  `exception_entry` for `admin_user_and_keys`, `ssh_keep_open`, and
  `banner_text` together.
- **Package contributions.** Banner write needs only coreutils (cat, chmod),
  pre-installed by subiquity. `emit_packages` returns `[]`.

## Test plan

### New unit tests

`tests/rules/test_ubuntu2404_banner_text.py` — mirror
`tests/rules/test_banner_text.py`:

- `test_post_writes_issue_files` — output contains `/etc/issue` + `/etc/issue.net`
- `test_post_writes_sshd_banner_not_motd` — output contains
  `/etc/ssh/sshd-banner` and does NOT contain `/etc/motd`
- `test_post_does_not_contain_dod_text` — no "U.S. Government" / "USG"
- `test_tailoring_is_empty_deferred` — `RULE.emit_tailoring(cfg) == []`
  (asserts the deferral contract so future audit-story PR is visibly
  the right place to add ops)
- `test_exception_entry_is_none_deferred` — `RULE.exception_entry(cfg) is None`
- `test_emit_packages_is_empty` — no apt deps

### Snapshot update

`tests/golden/__snapshots__/test_ubuntu_minimal.ambr` will gain a second
late-command entry containing the banner heredoc. Inspect the diff before
committing — it should be exactly the new entry plus nothing else.

### Cross-distro guard

`tests/rules/test_banner_text.py` (alma9) is untouched. Snapshot-driven check
that alma9 outputs are byte-identical to before is the existing alma9 golden
suite.

## Acceptance bar

- New ubuntu2404 banner_text module wired into `src/ks_gen/rules/ubuntu2404/__init__.py`.
- `pytest -q` green; the new ubuntu unit-test file passes; the ubuntu golden
  snapshot picks up the banner late-command and nothing else.
- Local CI parity chain (`ruff check && ruff format --check && mypy && pytest -q`) passes.
- Signed commit, PR opened against main, linked to #81 phase 3.1.
