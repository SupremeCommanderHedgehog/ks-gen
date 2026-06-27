# Phase 3.8 — `kernel_module_blacklist` port to ubuntu2404

**Parent:** #81 ubuntu STIG autoinstall.
**Previous phases on this workstream:** 3.0 admin_user_and_keys +
ssh_keep_open (#94), 3.1 banner_text (#101), 3.2 ssh_config_apply
(#102), 3.3 time_servers (#104), 3.4 crypto_policy (#106), 3.5
faillock_safety (#108), 3.6 unattended_updates (#110), 3.7
auditd_actions (#112).

## Goal

Port the `kernel_module_blacklist` rule to ubuntu2404 so the
generated autoinstall writes a modprobe blacklist file that disables
the operator-configured list of kernel modules at module-load time.
Defaults match the alma9 rule: `usb-storage`, `cramfs`, `freevxfs`,
`jffs2`, `hfs`, `hfsplus`, `squashfs`, `udf` — filesystems and
removable-media drivers the STIG profile requires disabled.

## Non-goals

- **ssg-ubuntu2404-ds.xml tailoring + exception text.** Deferred to
  the coordinated audit-story PR per the established phase-3.x
  pattern. The STIG rule IDs for individual kernel-module
  disablement (`xccdf_org.ssgproject.content_rule_kernel_module_<m>_disabled`)
  are SSG-shared and likely carry over verbatim to ubuntu2404, but
  the audit-story PR will systematically verify all 9 ported rules
  at once.
- **Schema changes.** `KernelModuleBlacklistCfg` is already
  distro-neutral in `src/ks_gen/config.py:590-603` — no edits.
- **Active unloading of already-loaded modules.** The install-trick
  prevents future loads; live modules require `rmmod` and a reboot
  to guarantee they stay gone. The autoinstall reboots immediately
  after `late-commands` complete, so any modules transiently loaded
  during install vanish at first real boot.
- **Driver vs. filesystem distinction.** Same default list as
  alma9 — both removable-media drivers (`usb-storage`) and obscure
  filesystem modules (`cramfs`, etc.). No distro-specific list
  divergence.
- **GRUB cmdline `module_blacklist=` parameter.** modprobe.d
  install-trick is the SSG-canonical approach; the cmdline knob is
  an alternative the STIG doesn't require. YAGNI.
- **DKMS or kernel-modules-extra interaction.** None of the eight
  default modules are DKMS-managed. If an operator adds a
  DKMS-built module to the override list, the install-trick still
  prevents auto-load — DKMS only handles build/install, not
  runtime loading.

## Architecture

One new rule module + one new test file. Shared
`src/ks_gen/rules/_meta/kernel_module_blacklist.py` (ID, SUMMARY,
DEPENDS_ON) is untouched.

`emit_post` writes a single modprobe drop-in via heredoc, mirroring
the alma9 implementation almost verbatim (the path lives outside
distro-specific config layout — `/etc/modprobe.d/` is the canonical
location for both Debian-family and RHEL-family systems):

```python
def _emit(cfg: HostConfig) -> str:
    modules = cfg.overrides.kernel_module_blacklist.modules
    body = "\n".join(f"install {m} /bin/true" for m in modules)
    return f"""\
# Disable specific kernel modules via modprobe install-trick
cat > /etc/modprobe.d/ks-gen-blacklist.conf <<'__KS_GEN_EOF__'
{body}
__KS_GEN_EOF__
chmod 644 /etc/modprobe.d/ks-gen-blacklist.conf
"""
```

The rule plugs into the existing ubuntu2404 bundle pipeline:
- `emit_post` contributes a `# rule:kernel_module_blacklist` band
  to `late-commands`. The single-quoted heredoc marker
  (`<<'__KS_GEN_EOF__'`) survives `shlex.quote` wrapping in
  `skeleton._format_late_commands` (precedent: banner_text,
  ssh_config_apply, crypto_policy, faillock_safety,
  unattended_updates, time_servers all use the same heredoc shape).
- `emit_packages` returns `[]` — `modprobe` lives in `kmod`
  (`Essential: yes` on Ubuntu Server), so the install-trick is
  always parseable. No apt deps.
- `applies(cfg)` returns
  `cfg.overrides.kernel_module_blacklist.enable` — operator can
  opt out by setting `enable: false` in `host.yaml`. Default is
  `True` (rule applies by default).

No changes to `writer.py`, `skeleton.py`, the user-data template, or
the config schema.

## Files touched

- **Create:** `src/ks_gen/rules/ubuntu2404/kernel_module_blacklist.py`
- **Create:** `tests/rules/test_ubuntu2404_kernel_module_blacklist.py`
- **Modify:** `tests/golden/__snapshots__/test_ubuntu_minimal.ambr`
  (snapshot regen)

## `emit_post` behavior

### Single block: `/etc/modprobe.d/ks-gen-blacklist.conf`

The modprobe **install-trick** redefines the module's load command
to a no-op binary (`/bin/true`). When anything (udev, kmod, an
operator's `modprobe`) tries to load the module, modprobe runs
`/bin/true` instead and the actual driver code never reaches the
kernel:

```bash
# Disable specific kernel modules via modprobe install-trick
cat > /etc/modprobe.d/ks-gen-blacklist.conf <<'__KS_GEN_EOF__'
install usb-storage /bin/true
install cramfs /bin/true
install freevxfs /bin/true
install jffs2 /bin/true
install hfs /bin/true
install hfsplus /bin/true
install squashfs /bin/true
install udf /bin/true
__KS_GEN_EOF__
chmod 644 /etc/modprobe.d/ks-gen-blacklist.conf
```

Design notes:
- **Install-trick over `blacklist <module>`.** `blacklist` only
  affects automatic loading by udev/systemd-modules-load; a manual
  `modprobe usb-storage` (or another module's softdep) would still
  load it. `install <m> /bin/true` is strictly stronger — modprobe
  itself refuses to perform the load. SSG and the alma9 rule both
  use install-trick.
- **`/bin/true` over `/sbin/modprobe --ignore-install`.** The
  alma9 rule uses `/bin/true`; this port mirrors. Either works;
  `/bin/true` is universally present and harder to typo.
- **Single-quoted heredoc marker.** `<<'__KS_GEN_EOF__'` prevents
  shell expansion of the body (the body has no `$` or backticks
  today, but defensive against future module names containing
  shell metacharacters).
- **`chmod 644` line.** Mirrors alma9 — modprobe reads the file
  world-readable. Matches Debian's default for `/etc/modprobe.d/`
  files (`umask 022` at install means the heredoc-written file
  inherits `644`, so the explicit chmod is defensive but consistent
  with alma9).
- **Filename `ks-gen-blacklist.conf`.** Unique prefix so the file
  doesn't collide with Debian-shipped `/etc/modprobe.d/blacklist*.conf`
  files (e.g. `blacklist-firewire.conf`, `blacklist-rare-network.conf`).

## Rule scaffolding

```python
"""ubuntu2404 kernel_module_blacklist rule.

Writes /etc/modprobe.d/ks-gen-blacklist.conf with modprobe
install-trick entries (install <module> /bin/true) for each
operator-configured kernel module. Prevents the kernel from loading
disallowed/unused modules at boot or on hot-plug.

`modprobe` ships in the `kmod` package (Essential: yes on Ubuntu
Server), so no apt deps are required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import kernel_module_blacklist as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


def _emit(cfg: HostConfig) -> str:
    modules = cfg.overrides.kernel_module_blacklist.modules
    body = "\n".join(f"install {m} /bin/true" for m in modules)
    return f"""\
# Disable specific kernel modules via modprobe install-trick
cat > /etc/modprobe.d/ks-gen-blacklist.conf <<'__KS_GEN_EOF__'
{body}
__KS_GEN_EOF__
chmod 644 /etc/modprobe.d/ks-gen-blacklist.conf
"""


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return cfg.overrides.kernel_module_blacklist.enable

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        # Deferred: ssg-ubuntu2404-ds.xml kernel-module-disablement rule
        # IDs land in the audit-story PR.
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        # `modprobe` ships in `kmod` (Essential: yes on Ubuntu).
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        # Deferred: paired with emit_tailoring above; see audit-story PR.
        return None


RULE: Rule = cast(Rule, _Rule())
```

## Tests (13)

All use the `ubuntu_cfg_factory` fixture. Module-level import of
`RULE`; local imports of `KernelModuleBlacklistCfg, Overrides`
inside per-test override functions (matches phases 3.3/3.4/3.5/3.6/3.7).

### `applies` semantics
1. `test_applies_when_enabled` — default cfg → True
2. `test_applies_short_circuits_when_disabled` — `enable=False` → False

### `emit_post` path + content shape
3. `test_post_writes_modprobe_blacklist_conf_path` —
   `/etc/modprobe.d/ks-gen-blacklist.conf` present (heredoc target)
4. `test_post_chmods_blacklist_conf_644` — `chmod 644 /etc/modprobe.d/ks-gen-blacklist.conf`
   present
5. `test_post_uses_install_trick_with_bin_true` — `install ` and
   ` /bin/true` both present in output (defensive shape pin)

### Default-module coverage
6. `test_post_includes_all_eight_default_modules` — each of the
   eight defaults (`usb-storage`, `cramfs`, `freevxfs`, `jffs2`,
   `hfs`, `hfsplus`, `squashfs`, `udf`) appears as
   `install <m> /bin/true`

### Cfg-override responsiveness
7. `test_post_reflects_modules_override_replaces_default_list` —
   override `modules=["dccp", "rds"]` → body has both new lines
   AND none of the default modules (`usb-storage` absent)
8. `test_post_reflects_empty_modules_override` —
   `modules=[]` → file still created (so the post-install state is
   deterministic), with NO `install ` line present

### Packages
9. `test_emit_packages_returns_empty` — `[]` (kmod is essential)

### Protocol contract
10. `test_emit_tailoring_returns_empty_deferred`
11. `test_exception_entry_returns_none_deferred`
12. `test_depends_on_is_empty`
13. `test_id_and_summary_come_from_shared_meta`

## Snapshot regen

After tests pass, run `pytest tests/golden/ --snapshot-update -k ubuntu_minimal`.

Expected diff (and ONLY these changes):

1. `- Applied rules: 9` → `+ Applied rules: 10` in the Summary
   section.
2. `+ - \`kernel_module_blacklist\` — Write modprobe blacklist for
   unused/disallowed kernel modules.` inserted at its sorted
   position in the Applied-rules list (alphabetical between
   `faillock_safety` and `ssh_*`).
3. A new `# rule:kernel_module_blacklist ──────────...` band
   inside `late-commands` containing the heredoc, eight
   `install <m> /bin/true` lines, the EOF marker, and the chmod
   line.
4. **No** addition to `autoinstall.packages:` (`emit_packages`
   returns `[]`).

No alma9 snapshots affected.

### Merge-order assumption

The 9 → 10 count assumes this branch sits on main at `d362e47`
(release 0.21.0, includes phases 3.0/3.1/3.2/3.3/3.4/3.5/3.6/3.7 =
9 ubuntu rules). If unrelated work landed first, regenerate the
snapshot and confirm the diff is "+1 your rule, nothing else."

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| `kmod` package missing in subiquity chroot | `kmod` is `Priority: required` on Ubuntu — present in every Subiquity install, including `ubuntu-server-minimal`. The `modprobe` binary is at `/usr/sbin/modprobe`, available even before any packages we install. |
| `usb-storage` blacklist blocks the install medium itself | The install is already complete by the time `late-commands` runs — Subiquity has copied the base system to `/target` and only post-install tasks remain. The modprobe.d file lands in `/target/etc/modprobe.d/`, so it only takes effect on first real boot. The installer continues to use the live ISO's modprobe state. |
| User adds a module name with a hyphen or underscore mismatch | modprobe normalizes hyphens vs. underscores in module names internally (`install usb-storage` matches `usb_storage` requests). No special handling needed. |
| Operator adds a module that doesn't exist on this kernel | The install-trick is purely a redefinition — it has no effect until something tries to load the named module. A nonexistent module name is a harmless line in the file; `lsmod` and `modinfo` are unaffected. |
| User configures `modules: []` | `_emit` produces an empty body (`body = ""`), heredoc writes an empty file. Defensive: no `install ` line, but the conf file still exists so audit checks that look for it pass. Tested explicitly. |
| Default list overlaps with already-loaded modules in the installer's live environment | Installer runs from a different rootfs (the live ISO). Late-commands write to `/target/etc/modprobe.d/`. The live environment is unaffected; the target system boots with the install-trick in place. |

## CI parity check before push

Per `CLAUDE.md`:

```bash
ruff check src tests \
  && ruff format --check src tests \
  && mypy \
  && pytest -q
```

If `ruff format --check` fails, fix with `ruff format src tests`.

## Out of scope (deferred)

- ssg-ubuntu2404-ds.xml `kernel_module_<m>_disabled` rule IDs +
  `TailoringOp` entries (audit-story PR).
- `exception_entry` runtime-computed English (audit-story PR — if
  there's no operator-facing exception story for this rule, may
  remain `None` permanently).
- GRUB `module_blacklist=` cmdline approach — alternative method
  not required by STIG.
- Per-module justification text in the modprobe.d file (alma9
  doesn't include comments per-module; mirror).
