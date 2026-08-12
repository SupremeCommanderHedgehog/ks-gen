## Outcome — validated locally, staying local-only

Built and validated an end-to-end install-regression harness on this
machine (`.scratch/install-regression/`, WSL Ubuntu + QEMU + OVMF).
**All 14 smoke-check assertions pass** against the load-bearing
fixture: a `host.yaml` whose `packages.required` explicitly omits
`dnf-automatic`. The `dnf-automatic.timer active` assertion proves
PR #56's `Rule.emit_packages` works against a real anaconda install.

**Decision: keep this local-only, not in GitHub Actions.** A full
TCG run takes ~30-90 min — that would burn workflow minutes for a
check that's only useful when changes touch the install pipeline.
Run it on demand locally when the diff warrants. Closing this issue
as complete — reopen if scope changes (e.g. team grows past one
hardware-attached maintainer).

## Smoke check (final run, 2026-06-12)

```
ok:   sshd active
ok:   chronyd active
ok:   firewalld active
ok:   auditd active
ok:   rsyslog active
ok:   dnf-automatic.timer active          ← #53 regression check passes
ok:   ks-gen-reboot-if-needed.timer enabled
ok:   ks-gen-dnf-automatic-full.timer enabled
ok:   faillock.conf has deny=3
ok:   /root/oscap-remediation-results.xml present
ok:   /root/oscap-remediation-report.html present
ok:   root password locked
ok:   aide installed
ok:   ks-post.log present and traced

ALL SMOKE CHECKS PASSED
```

## The recipe (for anyone reconstructing locally)

### Environment
- WSL Ubuntu 26.04 (or any Linux with QEMU + OVMF)
- `apt install -y qemu-system-x86 ovmf xorriso`
- The AlmaLinux DVD ISO (`AlmaLinux-9-latest-x86_64-dvd.iso`)
  available locally
- ks-gen installed in a venv

### OVMF firmware paths (Ubuntu 26.04+)
The legacy plain-name files are gone in 26.04; only the 4M variants
ship. Use these (SecureBoot off — the kickstart has no signing story):
```
OVMF_CODE=/usr/share/OVMF/OVMF_CODE_4M.fd          # read-only
OVMF_VARS=/usr/share/OVMF/OVMF_VARS_4M.fd          # template; cp per-VM
```

### Kernel-args injection (debug console)
`ks-gen iso` ships `quiet` on both the isolinux and grub menu
entries — the right default for a real human installer. For the
regression harness we need anaconda's UI on the serial port.

Wrap `ks_gen.iso.builder.build_iso` from Python and monkey-patch the
already-imported constants on `ks_gen.iso.bootloader` BEFORE invoking
`build_iso`. Replace ` quiet\n` with:

```
inst.text inst.notmux inst.console=ttyS0,115200n8 console=ttyS0,115200n8
```

`bootloader.py` does `from ._menu import GRUB_UNATTENDED_ENTRY, ...`
so the constants are read at function-call time — namespace
assignment on `bootloader.GRUB_UNATTENDED_ENTRY` takes effect without
touching `_menu.py`. No source edit, no revert.

### QEMU invocation

```
qemu-system-x86_64 \
  -accel tcg -cpu max \                            # or -enable-kvm -cpu host where /dev/kvm is accessible
  -smp 2 -m 4096 \
  -machine q35,smm=on \
  -drive if=pflash,format=raw,readonly=on,file=$OVMF_CODE \
  -drive if=pflash,format=raw,file=$NVRAM \        # per-VM copy of OVMF_VARS_4M.fd
  -drive file=$DISK,if=virtio,format=qcow2 \       # 60G sparse qcow2
  -cdrom $INSTALLER_ISO \
  -netdev user,id=n0,hostfwd=tcp:127.0.0.1:2222-:22 \
  -device virtio-net-pci,netdev=n0 \
  -nographic \
  -serial file:$SERIAL_LOG \
  -monitor unix:/tmp/qmp.sock,server,nowait
```

`reboot --eject` in the kickstart ejects the CD on success; OVMF's
nvram (which anaconda's `efibootmgr` wrote during install) prefers
the installed HD, so the post-install boot picks up the new system
without `-boot` order manipulation.

### Smoke-check assertions
After SSH'ing in as `opsadmin` (or whatever `cfg.user.admin.name` is):
- `systemctl is-active` on sshd, chronyd, firewalld, auditd, rsyslog
- `systemctl is-active dnf-automatic.timer` — the regression check
- `systemctl is-enabled ks-gen-reboot-if-needed.timer` and
  `ks-gen-dnf-automatic-full.timer`
- `/etc/security/faillock.conf` has `deny = 3`
- `/root/oscap-remediation-results.xml` non-empty
- `/root/oscap-remediation-report.html` non-empty
- `passwd -S root` field 2 matches `^LK?$` (AlmaLinux 9 prints `LK`,
  not the legacy ` L `)
- `aide` rpm installed
- `/root/ks-post.log` has bash xtrace lines

## Six traps that cost time

1. **`console=` argument order matters.** The kernel uses the **last**
   `console=` as `/dev/console`, and anaconda follows `/dev/console`
   for its UI when no `inst.console=` override is given. Trailing
   `console=tty0` makes anaconda's TUI invisible under `-nographic`
   and the install hangs waiting for input on a screen we can't see.
   First prototype run burnt 2h on this — `disk.qcow2` untouched.
   Fix: use `inst.console=ttyS0,115200n8` AND keep
   `console=ttyS0,115200n8` LAST; drop the `tty0` console entirely.
   `inst.notmux` is also necessary — anaconda's default tmux wrapper
   needs a TTY allocator that a `file:` serial sink doesn't provide.
2. **Disk size.** `DiskPreset.STIG_SERVER` allocates 15+5+3+10+5+3+2 =
   43G of LVs, plus 1G `/boot`, 1G EFI, plus recommended-size swap.
   25G fast-fails at ks.cfg line 10:
   `new lv is too large to fit in free space`. Use ≥ 50G. qcow2 is
   sparse so the cost is the install footprint (~3-4G), not 60G.
3. **WSL `/mnt/c` (DrvFs) kills QEMU runtime.**
   - qcow2 + many small writes: ~10x slower than ext4. Anaconda's
     package install crawls.
   - `chmod` is a no-op. OpenSSH refuses to use a 0777 private key,
     so any SSH key written under a `/mnt/c` path is rejected.
   - Unix sockets don't bind. QEMU's `-monitor unix:` fails with
     `Operation not supported`.
   Keep all QEMU-touched files on the WSL ext4 disk (e.g.
   `~/.cache/`) and the QMP socket in `/tmp/`.
4. **`/dev/kvm` may exist but be inaccessible.** On stock WSL Ubuntu
   the device is `crw-rw---- root:kvm 660` — non-kvm-group users get
   no `-r`. `usermod -aG kvm $USER` + re-login is the unblock. TCG
   still works; it just costs ~3x wall-clock.
5. **AlmaLinux 9 `passwd -S` format.** The status field is `LK` for a
   locked password, not the ` L ` you'd see on some other distros.
   Pattern: `awk '{print $2}' | grep -qE '^LK?$'`.
6. **xorriso writing to a partial output file fails fast on SIGHUP.**
   Background invocations via `nohup ... &` from inside `wsl --
   bash -c '...'` get killed when the parent `wsl.exe` exits. Keep
   the WSL session alive for the duration (or run interactively).

## How to run it

The full harness lives under `.scratch/install-regression/`
(gitignored — per-developer):

```
.scratch/install-regression/
├── run.sh                                    # the orchestrator
├── smoke-check.sh                            # runs over SSH on the installed VM
├── build-debug-iso.py                        # the monkey-patch wrapper
├── fixtures/omit-dnf-automatic.host.yaml.tmpl  # the #53 regression fixture
├── keys/                                     # generated ed25519 key (runtime)
├── build/                                    # symlink → ~/.cache/ks-gen-install-regression/
└── README.md                                 # full recipe + findings (local copy)
```

Invocation:
```bash
wsl -- bash -c "cd /mnt/c/Users/<you>/source/<repo> && .scratch/install-regression/run.sh"
```

Set `SKIP_ISO_BUILD=1` to skip the ~3 min ISO rebuild when iterating
on QEMU/kickstart changes that don't affect ISO contents.

## When this is worth running

Cost is ~30-90 min wall-clock on TCG. Run it when:

- `src/ks_gen/iso/` changed (builder, bootloader, _menu, the
  xorriso pipeline)
- `src/ks_gen/rules/*.py` gained a new `emit_packages`,
  `emit_post`, or `emit_tailoring` — anything that writes shell into
  `%post` or contributes to `%packages`
- `src/ks_gen/templates/ks.cfg.j2` or `templates/partials/*.j2`
  changed
- `src/ks_gen/writer.py` changed the bundle composition
- `src/ks_gen/config.py` changed defaults for fields the install
  consumes (network, disk, packages)

Don't run it for docs, CLI/typer changes that don't reach the
generated kickstart, test-only changes, or verify-command work.

## Issue status

Closing as complete. The end-to-end regression test exists; it's
local-only by design. If maintenance load grows or the team adds
contributors who need to run installs they can't observe locally,
re-open and revisit the CI question.
