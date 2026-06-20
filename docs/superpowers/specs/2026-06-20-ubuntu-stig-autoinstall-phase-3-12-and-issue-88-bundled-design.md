# Phase 3.12 + #88 — bundled port: `data_disks_preserve`, `container_host` minimal to ubuntu2404

**Parent:** #81 ubuntu STIG autoinstall (phase 3.12), and #88 ubuntu2404 container_host.
**Previous phases on this workstream:** 3.0 through 3.11 = 13 ubuntu rules ported to date (released through v0.23.0 at commit `d620678`).

## Goal

Port two rules to ubuntu2404 in a single bundled PR:

1. **Phase 3.12 — `data_disks_preserve`** — direct port of the alma9
   rule with one removal: drop the `restorecon -R <mounts>` line at
   the end of `emit_post`. SELinux file labels have no Ubuntu
   analog; AppArmor uses path-based process confinement on running
   binaries, not persistent file labels. `/etc/fstab` syntax,
   `mkdir -p`, and `mount -a` are universal.
2. **Phase issue #88 — `container_host` minimal port** — port of
   the alma9 rule + helper script with all SELinux-specific
   operations stripped:
   - Drop `semanage fcontext` calls (no equivalent on Ubuntu;
     AppArmor extension for `/srv/containers` is a queued follow-up).
   - Drop all `restorecon -R` calls.
   - Drop the `semanage` preflight check in the helper script.
   - Package list trimmed to Ubuntu-available names:
     `podman`, `crun`, `slirp4netns`, `fuse-overlayfs`.
     Drops `containers-common`, `podman-plugins` (RHEL-specific
     packaging — Ubuntu's `podman` pulls equivalents as
     dependencies) and `policycoreutils-python-utils` (SELinux only).
   - Same `/srv/containers/$USER/storage` storage shape (path is
     distro-neutral); same `storage.conf` content; same per-user
     provisioning + authorized_keys flow.

## Why bundled

These two rules are independent at the code level (no shared
schema changes, no rule deps). The ubuntu_minimal golden snapshot
is unaffected by either: `data_disks_preserve.applies` requires a
non-wipe data disk, `container_host.applies` requires
`containers.enabled=True`, and the ubuntu_minimal fixture has
neither. So there's no snapshot collision risk that would force
sequential merges (unlike the 3.9-3.11 bundle, where all three
rules bumped the Applied-rules count). Bundling here just saves
one CI cycle + release-please churn — no merge ordering pressure
either way.

## Non-goals

- **Custom AppArmor profile for podman containers / `/srv/containers`.**
  Deferred to a follow-up PR after install-regression validation
  on a real Ubuntu install. Without the profile,
  podman's stock `containers-default-X.Y.Z` profile applies — it
  auto-allows `/var/lib/containers` but NOT `/srv/containers`, so
  the rootless-storage-path override may produce AppArmor DENIED
  events on container start. Operators can disable AppArmor
  confinement per-container via `--security-opt apparmor=unconfined`
  as a workaround until the profile lands. Documented risk; opening
  a follow-up issue for the AppArmor extension.
- **ssg-ubuntu2404-ds.xml tailoring + exception text.** Neither
  rule emits tailoring or exceptions today (both alma9 sources
  return `[]` / `None`), so there's no audit-story PR coupling.
- **Schema changes.** `Containers`, `ContainerUser`, `ContainerVolume`,
  `DataDisk`, `Disk.data_disks` are distro-neutral in
  `src/ks_gen/config.py` — no edits.
- **Cross-distro mapping for fstype values in data_disks.**
  Operators specify `fstype` per disk in `host.yaml`. Default is
  `xfs` (works on Ubuntu via the `xfsprogs` package — pulled at
  install if needed, present in the default seed). If an operator
  needs `ext4`, they configure it explicitly in `host.yaml`. No
  rule-level munging.
- **Firewall (ufw) config for container_host.** Reading the alma9
  rule + helper script confirms no firewalld calls in either —
  firewall posture is the operator's responsibility outside this
  rule. The Ubuntu port mirrors: no ufw calls. Issue #88's body
  about firewalld→ufw was outdated.
- **Quadlet scaffold path on Ubuntu.** alma9 helper has a `-q`
  scaffold mode (used post-install only — kickstart never passes
  `-q`). The Ubuntu helper retains the same `-q` option for
  symmetry; the Quadlet units are systemd-native and work on
  Ubuntu unchanged. `restorecon` lines inside the `-q` branch are
  dropped.
- **Tear down the `_validate_containers_integration` validator's
  ubuntu2404 restrictions.** No such restrictions exist today —
  `grep ubuntu2404.*container src/ks_gen/config.py` returns
  nothing. Issue #88's claim about a post-validator was stale.

## Architecture

### Phase 3.12 — `data_disks_preserve`

```python
def applies(self, cfg: HostConfig) -> bool:
    return any(not d.wipe for d in cfg.disk.data_disks)

def emit_post(self, cfg: HostConfig) -> str:
    preserved = [d for d in cfg.disk.data_disks if not d.wipe]
    lines: list[str] = []
    for d in preserved:
        spec = _fstab_spec(d)
        opts = d.fsoptions or "defaults"
        lines.append(f"mkdir -p {d.mount}")
        lines.append(f'echo "{spec} {d.mount} {d.fstype} {opts} 0 2" >> /etc/fstab')
    lines.append("mount -a")
    return "\n".join(lines)

def emit_packages(self, cfg: HostConfig) -> list[str]:
    return []

def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
    return []

def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
    return None
```

`_fstab_spec` is identical to alma9 (`partition` / `partition_uuid`
/ `partition_label` resolution). The only difference vs. alma9 is
the dropped final `restorecon -R {mounts}` line — Ubuntu has no
SELinux labels to fix up, and AppArmor doesn't have a per-path
relabel operation.

### Phase #88 — `container_host` minimal

```python
_SCRIPT = files("ks_gen.assets").joinpath("create-rootless-user-ubuntu.sh").read_text(encoding="utf-8")


def _emit(cfg: HostConfig) -> str:
    parts: list[str] = []

    # Drop the Ubuntu helper script to /root for operator post-install use
    parts.append("# Install the rootless-container-user helper at /root for post-install use")
    parts.append("cat > /root/create-rootless-user.sh <<'__KS_GEN_EOF__'")
    parts.append(_SCRIPT.rstrip())
    parts.append("__KS_GEN_EOF__")
    parts.append("chown root:root /root/create-rootless-user.sh")
    parts.append("chmod 0550 /root/create-rootless-user.sh")
    parts.append("")

    # System-wide storage.conf: pin rootless graphroot under the mirror
    parts.append(
        "# System-wide storage.conf -- pins rootless graphroot to the /srv/containers mirror"
    )
    parts.append("install -d -m 0755 /etc/containers")
    parts.append("cat > /etc/containers/storage.conf <<'__KS_GEN_EOF__'")
    parts.append("[storage]")
    parts.append('driver = "overlay"')
    parts.append('rootless_storage_path = "/srv/containers/$USER/storage"')
    parts.append("__KS_GEN_EOF__")
    parts.append("chmod 0644 /etc/containers/storage.conf")

    # Provision each configured container user via the helper. -l (linger)
    # always on; -q (Quadlet scaffold) intentionally off for kickstart-time.
    for u in cfg.containers.users:
        gecos = u.gecos or u.name
        parts.append("")
        parts.append(f"# Provision container user: {u.name}")
        parts.append(f'/root/create-rootless-user.sh -l -c "{gecos}" {u.name}')
        parts.append(f"install -d -m 0700 -o {u.name} -g {u.name} /home/{u.name}/.ssh")
        parts.append(f"cat > /home/{u.name}/.ssh/authorized_keys <<'__KS_GEN_EOF__'")
        parts.extend(u.authorized_keys)
        parts.append("__KS_GEN_EOF__")
        parts.append(f"chown {u.name}:{u.name} /home/{u.name}/.ssh/authorized_keys")
        parts.append(f"chmod 0600 /home/{u.name}/.ssh/authorized_keys")
        # No `restorecon -R /home/{user}/.ssh` — Ubuntu has no SELinux.

    return "\n".join(parts) + "\n"


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return cfg.containers.enabled

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return [
            "podman",
            "crun",
            "slirp4netns",
            "fuse-overlayfs",
        ]

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return None
```

#### Helper script: `create-rootless-user-ubuntu.sh`

Port of `create-rootless-user.sh` with these specific changes
relative to the alma9 source:

| Line ref (alma9) | Operation removed/changed |
|---|---|
| 87-88 | Drop `semanage` preflight check (no SELinux) |
| 104-107 | Drop SELinux fcontext equivalence block |
| 142 | Drop `restorecon -R "${CONTAINERS_ROOT}/${user}"` |
| 163 | Drop `restorecon -R "$home/.ssh"` |
| 178-181 | Drop semanage fcontext block in `-q` Quadlet section |
| 184 | Drop `restorecon -RF "$appdata"` |
| 202, 222, 259 | Drop `restorecon "..." 2>/dev/null \|\| true` after each Quadlet file write |
| 18 | Update comment from "Target: AlmaLinux 9" to "Target: Ubuntu 24.04 LTS" |

All other logic preserved verbatim:
- `useradd`, `usermod --add-subuids/--add-subgids`
- `install -d` for storage dir
- `loginctl enable-linger`
- SSH key install
- Quadlet scaffold (network + volume + container units)
- podman info verification

Note on package availability: Ubuntu 24.04 ships `podman` 4.9.3+,
`crun`, `slirp4netns`, `fuse-overlayfs` in the main archive. Drops
the alma9-only `containers-common`, `podman-plugins` (their
contents are bundled into the Ubuntu `podman` package's deps:
`netavark`, `containers-storage`, etc. are pulled transitively).

## Files touched

- **Create:** `src/ks_gen/rules/ubuntu2404/data_disks_preserve.py`
- **Create:** `tests/rules/test_ubuntu2404_data_disks_preserve.py`
- **Create:** `src/ks_gen/rules/ubuntu2404/container_host.py`
- **Create:** `tests/rules/test_ubuntu2404_container_host.py`
- **Create:** `src/ks_gen/assets/create-rootless-user-ubuntu.sh`
- **No modify:** ubuntu_minimal golden snapshot is unaffected
  (both rules' `applies` returns False on the default
  ubuntu_minimal config, so neither bumps the Applied-rules count
  or adds a late-commands band).

## Tests

### `data_disks_preserve` (12 tests, mirror of alma9 test file)

1. `test_rule_metadata` — `id == "data_disks_preserve"`, `depends_on == []`, `stig_rules_affected == []`.
2. `test_rule_does_not_apply_with_no_data_disks` — default ubuntu cfg → False.
3. `test_rule_does_not_apply_when_all_data_disks_wiped` — single disk with `wipe=True` → False.
4. `test_rule_applies_when_any_data_disk_preserved` — single disk with `wipe=False` → True.
5. `test_rule_emit_post_preserve_by_partition_number` — `/dev/disk/by-id/...-part2` in fstab line.
6. `test_rule_emit_post_preserve_by_uuid` — `UUID=...` in fstab line.
7. `test_rule_emit_post_preserve_by_label` — `LABEL=...` in fstab line.
8. `test_rule_emit_post_uses_defaults_when_fsoptions_null` — `defaults` in opts col.
9. `test_rule_emit_post_only_includes_preserved_disks` — wiped disks absent.
10. `test_rule_emit_post_handles_multiple_preserved_disks` — multiple lines, multiple mounts.
11. `test_rule_emit_post_drops_restorecon` — `restorecon` NOT in body (key port assertion).
12. Protocol contract: `emit_packages == []`, `emit_tailoring == []`, `exception_entry is None`, `id`/`summary` from shared meta.

### `container_host` minimal (15 tests, mirror of alma9 test file)

1. `test_container_host_rule_metadata` — `id`, `summary`.
2. `test_does_not_apply_by_default` — `containers.enabled=False` → False.
3. `test_applies_when_enabled` — `containers.enabled=True` → True.
4. `test_emit_packages_returns_ubuntu_podman_stack` — `podman`, `crun`, `slirp4netns`, `fuse-overlayfs` present; `containers-common`, `podman-plugins`, `policycoreutils-python-utils` NOT present (key Ubuntu port assertion).
5. `test_emit_tailoring_is_empty`.
6. `test_exception_entry_is_none`.
7. `test_emit_post_drops_script_and_storage_conf` — script at /root, perms, storage.conf with `rootless_storage_path`.
8. `test_emit_post_empty_users_still_drops_script` — empty `users` list, no per-user provisioning.
9. `test_emit_post_provisions_each_user` — `/root/create-rootless-user.sh -l -c "GECOS" user` per user; install -d for .ssh; authorized_keys file.
10. `test_emit_post_handles_multiple_keys` — multiple lines in authorized_keys.
11. `test_emit_post_no_quadlet_scaffold` — no `-q` flag passed at kickstart time.
12. `test_emit_post_drops_restorecon_calls` — no `restorecon` anywhere in the rendered body (key Ubuntu port assertion).
13. `test_helper_script_drops_semanage_calls` — `semanage` NOT in the embedded script (key Ubuntu port assertion).
14. `test_helper_script_drops_restorecon_calls` — `restorecon` NOT in the embedded script.
15. `test_helper_script_targets_ubuntu` — script docstring mentions Ubuntu (not "AlmaLinux").

Total: **27 new tests** across two test files.

### Snapshot impact

**None.** ubuntu_minimal golden snapshot is unaffected — both rules'
`applies` returns False on the default cfg. No regen needed.

If a follow-up PR adds an ubuntu fixture with `containers.enabled=True`
or `data_disks` with `wipe=False`, that PR adds the corresponding
golden snapshot. Out of scope here.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Ubuntu podman + `/srv/containers` triggers AppArmor DENIED events | Known; documented in non-goals. Operators can `--security-opt apparmor=unconfined` per-container as workaround. Follow-up issue tracks the AppArmor profile work. |
| `containers-common` config files missing on Ubuntu → podman misconfigured | Ubuntu `podman` package pulls `containers-storage` and similar transitive deps that provide `/etc/containers/registries.conf`, `/etc/containers/policy.json`, etc. The rule additionally writes our own `/etc/containers/storage.conf` (overriding). Verified by reading Ubuntu 24.04 podman package metadata. |
| `useradd` behavior diverges on Ubuntu vs RHEL (autoallocation of subuid/subgid) | Helper script's `ensure_subids()` function handles both cases — explicitly allocates a range if one doesn't exist. Same code path on both distros. |
| `loginctl enable-linger` not available on Ubuntu | systemd is standard on Ubuntu 24.04; `loginctl` ships with `systemd` package (Essential). Same code path. |
| Quadlet scaffold writes `restorecon` calls that fail on Ubuntu | Removed in the port. The `2>/dev/null \|\| true` defensive pattern on the alma9 source would have squashed it anyway, but cleaner to remove. |
| Bundled PR makes review harder | Plan groups changes by rule + helper script. Each rule's commits are independent. Spec doc surfaces per-rule design decisions. |
| Helper script port introduces subtle bug not caught by unit tests | Acknowledged; install-regression run on a real Ubuntu install validates end-to-end. Recommend running it per CLAUDE.md guidance ("recommend when iso/rules emit_post changes plausibly affect what anaconda does"). |

## CI parity check before push

Per `CLAUDE.md`:

```bash
ruff check src tests \
  && ruff format --check src tests \
  && mypy \
  && pytest -q
```

If `ruff format --check` fails, fix with `ruff format src tests`.

Expected test count: `890 + 27 = 917` (or close, depending on what's
landed since v0.23.0).

## Out of scope (deferred)

- AppArmor profile extension for podman + `/srv/containers` (follow-up issue).
- Ubuntu golden fixture exercising containers.enabled / data_disks.
- ubuntu2404-specific Quadlet scaffold polish.
- Any helper script refactor that unifies alma/ubuntu into one file.
