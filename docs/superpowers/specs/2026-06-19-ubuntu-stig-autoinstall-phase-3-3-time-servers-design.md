# Phase 3.3 — `time_servers` port to ubuntu2404

**Parent:** #81 ubuntu STIG autoinstall.
**Previous phases on this workstream:** 3.0 admin_user_and_keys + ssh_keep_open (#94), 3.1 banner_text (#101), 3.2 ssh_config_apply (#102).

## Goal

Port the `time_servers` rule to ubuntu2404 so the generated autoinstall
configures chrony with the operator's NTP servers from
`cfg.time.servers`, on Ubuntu Server 24.04, with the same civilian-default
exception posture as the alma9 path. No DoD time sources; same shape as
alma9, with two OS-specific divergences (config path, package install).

## Non-goals

- ssg-ubuntu2404-ds.xml time/NTP rule survey + `TailoringOps` +
  `ExceptionEntry` text. These are deferred to the coordinated
  audit-story PR per the established phase-3.x pattern (banner_text and
  ssh_config_apply both ship with empty `emit_tailoring` / `None`
  `exception_entry`).
- Explicit `systemd-timesyncd` disable in the late-command. The chrony
  apt package's postinst declares
  `Conflicts=systemd-timesyncd.service`, so installing chrony stops and
  masks timesyncd automatically. Mirrors alma9's config-only stance.
- Explicit `systemctl enable chrony` in the late-command. chrony's
  postinst auto-enables `chrony.service` on Ubuntu. Mirrors alma9, which
  also does not explicitly enable chronyd.

## Architecture

One new rule module + one new test file. Shared `_meta/time_servers.py`
is untouched — its `ID`, `SUMMARY`, and `DEPENDS_ON=[]` are already
distro-agnostic.

The rule plugs into the existing ubuntu2404 bundle pipeline:

- `emit_post` contributes a `# rule:time_servers` block to
  `late-commands` (via `_build_ubuntu2404_bundle` in `writer.py`).
- `emit_packages` contributes `"chrony"` to `autoinstall.packages:`
  (via the rule_packages plumbing landed in PR #99) — this rule is the
  **first ubuntu2404 rule that actually exercises that plumbing**;
  banner_text and ssh_config_apply both return `[]` because their tools
  are part of Ubuntu Server's default install.

No changes to `writer.py`, `skeleton.py`, the user-data template, or the
config schema. The plumbing already routes both halves.

## Files touched

- **Create:** `src/ks_gen/rules/ubuntu2404/time_servers.py`
- **Create:** `tests/rules/test_ubuntu2404_time_servers.py`
- **Modify:** `tests/test_writer.py` — one new test verifying the
  chrony package threads through to `autoinstall.packages` end-to-end.
- **Modify:** `tests/golden/__snapshots__/test_ubuntu_minimal.ambr` —
  snapshot regen.

## Rule behavior

### Body emitted into `late-commands`

```bash
# Chrony configuration (servers from host.yaml; STIG-compliant base)
install -d -m 755 /etc/chrony
cat > /etc/chrony/chrony.conf <<'__KS_GEN_EOF__'
server pool.ntp.org iburst
driftfile /var/lib/chrony/chrony.drift
makestep 1.0 3
rtcsync
logdir /var/log/chrony
__KS_GEN_EOF__
chmod 644 /etc/chrony/chrony.conf
```

(Default `cfg.time.servers = ["pool.ntp.org"]` and
`cfg.time.chrony_makestep_threshold = 1.0` produce the above; the
`server` lines and `makestep` value re-template from cfg.)

Body content matches alma9 line-for-line except:

1. **Path: `/etc/chrony/chrony.conf`**, not `/etc/chrony.conf`. Ubuntu's
   chrony package owns `/etc/chrony/` as a directory.
2. **Driftfile: `/var/lib/chrony/chrony.drift`**, not
   `/var/lib/chrony/drift`. Matches Ubuntu's chrony package default,
   which is what `apparmor`'s `usr.sbin.chronyd` profile expects and
   what `systemd-tmpfiles` recreates.
3. **`install -d -m 755 /etc/chrony`** belt — when this late-command
   runs the directory already exists (chrony installs before
   late-commands run), but the idempotent mkdir costs nothing and
   protects against re-runs.

### Module skeleton

```python
"""ubuntu2404 chrony NTP configuration.

Writes /etc/chrony/chrony.conf with operator-chosen servers from
cfg.time.servers. Adds the chrony package to autoinstall.packages so
it's present in the chroot before this late-command runs. Service
activation and systemd-timesyncd masking are owned by chrony's apt
postinst (Conflicts=systemd-timesyncd.service) — same config-only
stance as the alma9 rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import time_servers as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


def _emit(cfg: HostConfig) -> str:
    servers = "\n".join(f"server {s} iburst" for s in cfg.time.servers)
    thresh = cfg.time.chrony_makestep_threshold
    return f"""\
# Chrony configuration (servers from host.yaml; STIG-compliant base)
install -d -m 755 /etc/chrony
cat > /etc/chrony/chrony.conf <<'__KS_GEN_EOF__'
{servers}
driftfile /var/lib/chrony/chrony.drift
makestep {thresh} 3
rtcsync
logdir /var/log/chrony
__KS_GEN_EOF__
chmod 644 /etc/chrony/chrony.conf
"""


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        # Deferred: ssg-ubuntu2404-ds.xml time/NTP rule survey lands in the audit-story PR.
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return ["chrony"]

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        # Deferred: paired with emit_tailoring above; see audit-story PR.
        return None


RULE: Rule = cast(Rule, _Rule())
```

## Tests

### `tests/rules/test_ubuntu2404_time_servers.py`

All tests use the existing `ubuntu_cfg_factory` fixture from
`tests/rules/conftest.py`. Module-level import of `RULE` at top of file
(per phase 3.1 review feedback — no inline imports inside tests).

1. `test_post_writes_chrony_conf_at_ubuntu_path` — `/etc/chrony/chrony.conf`
   in output (and `/etc/chrony.conf\n` NOT in output, to catch path drift).
2. `test_post_writes_server_lines_for_each` — default
   `server pool.ntp.org iburst` is present.
3. `test_post_handles_multiple_servers` — overriding `cfg.time` with two
   servers yields both `server X iburst` lines.
4. `test_post_no_dod_servers_in_output` — `"usno"` and `"navy.mil"`
   absent.
5. `test_post_emits_drift_logdir_rtcsync` — `driftfile
   /var/lib/chrony/chrony.drift`, `logdir /var/log/chrony`, `rtcsync`
   lines all present.
6. `test_post_uses_configured_makestep_threshold` — overriding
   `chrony_makestep_threshold=2.5` yields `makestep 2.5 3`.
7. `test_post_chmod_644` — `chmod 644 /etc/chrony/chrony.conf` present.
8. `test_post_uses_install_dir_for_chrony_dir` — `install -d -m 755
   /etc/chrony` present (idempotent re-run protection).
9. `test_emit_packages_returns_chrony` — `RULE.emit_packages(cfg) ==
   ["chrony"]`.
10. `test_applies_always_true`.
11. `test_emit_tailoring_returns_empty_deferred`.
12. `test_exception_entry_returns_none_deferred`.
13. `test_depends_on_is_empty` — mirrors meta's empty `DEPENDS_ON`.
14. `test_id_and_summary_come_from_shared_meta`.

### `tests/test_writer.py` — one new test

```
test_build_bundle_ubuntu2404_packages_includes_chrony_when_time_servers_applies
```

Builds a ubuntu2404 bundle and asserts:
- `"chrony"` is in the rendered `user_data` under an
  `autoinstall.packages:` block, OR equivalently, by re-parsing the YAML
  and asserting `"chrony" in autoinstall["packages"]`. Parsing YAML is
  the more robust approach — string-search would false-positive on the
  `server` lines.

This is a writer-level integration test: it proves that
`rule.emit_packages` → `rule_packages` collection in
`_build_ubuntu2404_bundle` → `render_user_data(rule_packages=...)` →
`autoinstall.packages:` block actually works end-to-end with a real rule
that contributes a package.

## Snapshot regen

After tests pass, run:

```bash
pytest tests/golden/ --snapshot-update
```

Inspect the diff. Expected changes (and ONLY these):

- `tests/golden/__snapshots__/test_ubuntu_minimal.ambr`:
  - New `autoinstall.packages:` block under `autoinstall:` with one
    entry: `- "chrony"`.
  - New `# rule:time_servers ──────────...` band in late-commands with
    the body shown above.
  - The intro comment in the late-commands block (e.g.,
    `# Applied rules: N`) bumps from 4 to 5.

No alma9 snapshots should diff. If any do, that's a bug — investigate
before committing.

### Merge-order assumption

The 4 → 5 Applied-rules count assumes this phase merges on top of main
at `9a1b094` (which contains phases 3.0/3.1/3.2 = admin_user_and_keys,
ssh_keep_open, banner_text, ssh_config_apply = 4 rules). If unrelated
work landed in main first that adds another ubuntu2404 rule, regenerate
the snapshot and confirm the diff is "+1 your rule, nothing else" before
committing.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| chrony path drift between Ubuntu releases | Pinned to 24.04 LTS. If 22.04 support is ever added it'll be a sibling rule and we'll re-survey then. |
| Driftfile name divergence breaks apparmor on first chronyd start | Using Ubuntu's package default (`chrony.drift`), which is exactly what apparmor's `usr.sbin.chronyd` profile expects. |
| chrony postinst doesn't actually mask timesyncd in chroot | Confirmed by `apt-cache show chrony` in 24.04 (Conflicts directive). Even if not, dual-running timesyncd + chrony is a soft failure (one wins on systemd's last-writer logic), not a STIG audit fail. |
| late-command runs before chrony is installed | autoinstall installs `packages:` before `late-commands` runs. Same guarantee phases 3.0/3.1/3.2 already rely on. |

## CI parity check before push

Per `CLAUDE.md`, run the full chain locally before claiming "ready for
PR":

```bash
ruff check src tests \
  && ruff format --check src tests \
  && mypy \
  && pytest -q
```

If `ruff format --check` fails after writing the rule (heredoc
indentation is a common cause), fix with `ruff format src tests` and
re-verify. Both phase 3.1 and 3.2 hit this — it's the most common false
"green" in this workstream.

## Out of scope (deferred to audit-story PR)

- `emit_tailoring` returning actual `TailoringOp` entries for the
  ssg-ubuntu2404-ds.xml NTP rules (xccdf rule IDs along the lines of
  `xccdf_org.ssgproject.content_rule_chronyd_or_ntpd_specify_remote_server`
  and friends — exact IDs TBD by the survey).
- `exception_entry` returning the English justification text for the
  civilian-NTP exception against those rules.
