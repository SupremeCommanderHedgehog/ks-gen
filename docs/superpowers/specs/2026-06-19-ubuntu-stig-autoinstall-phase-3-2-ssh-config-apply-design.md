# Ubuntu STIG Autoinstall Phase 3.2 — `ssh_config_apply` Port Design

> **Status:** Approved design for phase 3.2 of #81. Same "defer tailoring +
> exception" scope pattern as 3.0/3.1. Completes the `Banner` wiring that
> phase 3.1's `banner_text` spec left open ("sshd_config drop-in that points
> `Banner` at `/etc/ssh/sshd-banner` … that's `ssh_config_apply`'s
> responsibility and will land with that rule's ubuntu2404 port in a later
> phase").

> **Merge-order assumption (added post-review):** The Architecture section's
> topo trace assumes phase 3.1 (`banner_text`, PR #101) merges first. If 3.2
> ships solo, the topo order is `[admin_user_and_keys, ssh_keep_open,
> ssh_config_apply]` (no banner_text yet), and the predicted snapshot count
> bump is `2 → 3` instead of `3 → 4`. Either merge order produces a valid
> install — the rule code itself is independent.

## Goal

Port the `ssh_config_apply` rule to `ubuntu2404` so an ubuntu autoinstall
bundle drops the sshd config knobs `ks-gen` controls — `Port`,
`PermitRootLogin`, `PasswordAuthentication`, `ClientAliveInterval`,
`ClientAliveCountMax`, `MaxAuthTries`, `UsePAM` — into a config-drop file at
install time, and validate it before subiquity reboots. Completes the
banner-text → sshd wiring by adding the `Banner` directive (conditional on
banner_text's `motd` target).

## Locked decisions (from brainstorming)

| Decision | Choice | Reason |
| -------- | ------ | ------ |
| PR scope | `emit_post` only; `emit_tailoring` / `exception_entry` / `emit_packages` return empty / `None` / empty | Mirrors phase 3.0/3.1 lock. Audit-story PR will populate tailoring + exception across all ported rules after surveying `ssg-ubuntu2404-ds.xml`. |
| Drop-in path + mode | `/etc/ssh/sshd_config.d/00-ks-gen.conf` at mode `600` | Same as alma9; subiquity-installed openssh-server reads the same include directory. Lexical prefix `00-` makes this the first override loaded (and the last to win for STIG knobs we control). Mode 600 is the conservative + STIG-compliant choice; sshd parses 600 fine because it runs as root. |
| Field set | Same seven as alma9 | `Port`, `PermitRootLogin`, `PasswordAuthentication`, `ClientAliveInterval`, `ClientAliveCountMax`, `MaxAuthTries`, `UsePAM`. All read from `cfg.ssh`; no schema changes. |
| Banner directive | Conditional: emit `Banner /etc/ssh/sshd-banner` only when `"motd" in cfg.banner.apply_to` | Phase 3.1's banner_text writes `/etc/ssh/sshd-banner` only when `motd` is in `apply_to` (the motd → sshd-banner remap). Gating Banner here on the same condition keeps the two rules consistent: if an operator drops the motd target, the directive isn't set, and sshd doesn't try to read a missing file. |
| Heredoc style | `<<'__KS_GEN_EOF__'` matching alma | Single-quoted delimiter, identical to phase 3.1. Same shlex.quote round-trip behavior in `_format_late_commands`. |
| Validation | `sshd -t` as the final command in the late-command body | Same as alma9. Fails the install if the rendered config is malformed — catches typos at build/install time, not after a reboot loop. |
| Service-state change | None | Late-commands run in `curtin in-target` chroot before subiquity finishes; sshd isn't running, so `restart` / `reload` would either error or be a no-op. The active config takes effect on first boot. |
| Meta sharing | Reuse `src/ks_gen/rules/_meta/ssh_config_apply.py` unchanged | `ID`, `SUMMARY`, `DEPENDS_ON = ["admin_user_and_keys", "ssh_keep_open"]` are distro-agnostic by design. |

## Architecture

### Rule module

`src/ks_gen/rules/ubuntu2404/ssh_config_apply.py` mirrors the shape of
`src/ks_gen/rules/alma9/ssh_config_apply.py`:

```python
def _emit(cfg: HostConfig) -> str:
    s = cfg.ssh
    pwd = "yes" if s.password_authentication else "no"
    pam = "yes" if s.use_pam else "no"
    banner_line = (
        "Banner /etc/ssh/sshd-banner\n" if "motd" in cfg.banner.apply_to else ""
    )
    return f"""\
# Drop-in SSH server config (active on first boot)
install -d -m 755 /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/00-ks-gen.conf <<'__KS_GEN_EOF__'
Port {s.port}
PermitRootLogin {s.permit_root_login}
PasswordAuthentication {pwd}
ClientAliveInterval {s.client_alive_interval}
ClientAliveCountMax {s.client_alive_count_max}
MaxAuthTries {s.max_auth_tries}
UsePAM {pam}
{banner_line}__KS_GEN_EOF__
chmod 600 /etc/ssh/sshd_config.d/00-ks-gen.conf
sshd -t
"""

class _Rule:
    # id, summary, depends_on from shared _meta
    # stig_rules_affected: []
    def applies(self, cfg) -> bool: return True
    def emit_tailoring(self, cfg) -> list[TailoringOp]: return []
    def emit_post(self, cfg) -> str: return _emit(cfg)
    def emit_packages(self, cfg) -> list[str]: return []
    def exception_entry(self, cfg) -> ExceptionEntry | None: return None
```

`stig_rules_affected` is `[]` for this PR (informational field for
`exceptions.md`; populated by the audit-story PR alongside the real tailoring
entry).

### Topological position

After this PR, `topo_sort` returns:
`[admin_user_and_keys, banner_text, ssh_keep_open, ssh_config_apply]`.

Trace: `pkgutil.iter_modules` returns alphabetically discovered modules
(`admin_user_and_keys, banner_text, ssh_config_apply, ssh_keep_open`).
`topo_sort` walks them in insertion order, recursing into deps first. When it
visits `ssh_config_apply`, it first visits its deps `admin_user_and_keys`
(already done) and `ssh_keep_open` (not yet — visits + appends), then
appends `ssh_config_apply` itself. The new entry lands at the END of
`late-commands` in the snapshot.

### Banner gating semantics

The conditional adds exactly one line to the drop-in when active:

```
Banner /etc/ssh/sshd-banner
```

If `motd` is removed from `cfg.banner.apply_to`, the line is absent, and the
drop-in falls through to whatever default `Banner` setting the base
`/etc/ssh/sshd_config` carries (subiquity default: none / commented). This
makes the two rules independently composable while keeping the common path
(default `apply_to` includes `motd`) wire up sshd banner correctly.

### Out of scope (later PRs)

- **Datastream survey + tailoring + exception backfill.** Coordinated PR
  after `ssg-ubuntu2404-ds.xml` rule IDs are enumerated. Will retroactively
  populate `emit_tailoring` and `exception_entry` for all ported ubuntu
  rules together (admin_user_and_keys, ssh_keep_open, banner_text,
  ssh_config_apply).
- **Package contributions.** openssh-server is installed by default on
  Ubuntu Server 24.04; the bundle doesn't need to declare it.
- **Additional sshd directives** beyond the seven `cfg.ssh` already exposes.
  `MaxSessions`, `LoginGraceTime`, `KexAlgorithms`/`Ciphers`/`MACs`, etc.
  are STIG-relevant but stay out — the `crypto_policy` rule port (phase 3.x)
  will own crypto directives; `cfg.ssh` schema growth is a separate change.

## Test plan

### New unit tests

`tests/rules/test_ubuntu2404_ssh_config_apply.py` mirrors
`tests/rules/test_ssh_config_apply.py`:

- `test_depends_on_admin_and_keep_open` — `RULE.depends_on` contains both
- `test_post_writes_drop_in_config` — output contains
  `/etc/ssh/sshd_config.d/00-ks-gen.conf`, all seven sshd directives
  with default values (Port 22, PermitRootLogin no, etc.)
- `test_post_validates_with_sshd_t` — output contains `sshd -t`
- `test_post_does_not_restart_sshd_during_install` — no `systemctl restart sshd`
  / `systemctl reload sshd`
- `test_emit_tailoring_returns_empty_deferred` — `RULE.emit_tailoring(cfg) == []`
- `test_exception_entry_returns_none_deferred` — `RULE.exception_entry(cfg) is None`
- `test_emit_packages_is_empty` — no apt deps
- `test_id_and_summary_come_from_shared_meta` — `RULE.id == meta.ID`, etc.

Ubuntu-specific Banner-gating tests:

- `test_post_emits_banner_directive_when_motd_in_apply_to` — default ubuntu
  cfg (apply_to includes `motd`) renders `Banner /etc/ssh/sshd-banner`
- `test_post_omits_banner_directive_when_motd_excluded` — with
  `cfg.banner.apply_to` set to `[issue, issue_net, gdm]`, the output does
  NOT contain `Banner /etc/ssh/sshd-banner`

### Snapshot update

`tests/golden/__snapshots__/test_ubuntu_minimal.ambr` gains:
- A new `ssh_config_apply` late-command entry at the end of `late-commands`
- Applied rules count `3 → 4`, new bullet `- ssh_config_apply — Write sshd drop-in config for Port/PermitRootLogin/PasswordAuthentication.`

No changes expected to `tailoring.xml`, `meta-data`, or `host.yaml`.

### Cross-distro guard

`tests/rules/test_ssh_config_apply.py` (alma9) untouched.

## Acceptance bar

- New ubuntu2404 ssh_config_apply module discoverable by
  `registry.load_rules("ubuntu2404")`.
- `pytest -q` green; new unit-test file passes; snapshot regen shows only
  the predicted additions.
- `alma9` goldens byte-identical.
- Local CI parity chain (`ruff check && ruff format --check && mypy && pytest -q`) passes.
- Signed commit, PR opened against main, linked to #81 phase 3.2.
