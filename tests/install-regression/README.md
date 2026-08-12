# ks-gen install-regression harness (manual, on-demand)

On-demand end-to-end install regression test. Drives the full
`ks-gen gen` → `ks-gen iso` → QEMU EFI boot → anaconda install →
SSH-in → smoke-check pipeline against a real AlmaLinux install in QEMU.

**Not run by CI and not collected by pytest** (no `test_*.py` here). A TCG
install is 30-90 min, which would burn workflow minutes for a check that is
only useful when changes touch the install pipeline. Issue #57 has the
original rationale; the harness lived under `.scratch/` until 2026-08-12,
when it was tracked so its fixes stop being per-machine.

When to run: see project `CLAUDE.md` → "Install-regression harness".
Short version: when `src/ks_gen/{iso,rules,writer,config}.py`,
`src/ks_gen/templates/**`, or anything else that affects what
anaconda actually does has changed.

Requires WSL (or Linux) with `qemu-system-x86_64`, `xorriso`, OVMF, and
KVM. Everything it writes goes to `$BUILD`
(default `~/.cache/ks-gen-install-regression`), never into the repo.

## How to run

```bash
wsl -- bash -c "cd \"$(git rev-parse --show-toplevel)\" && tests/install-regression/run.sh"
```

`SKIP_ISO_BUILD=1` skips the ~3 min ISO rebuild when iterating on
QEMU/kickstart changes that don't affect ISO contents.

Override `SRC_ISO` and `FIXTURE_TEMPLATE` to drive a distro other than the
AL9 default — e.g. AlmaLinux 10 (network install; AL10 boot media carries no
package payload):

```bash
FIXTURE_TEMPLATE=tests/install-regression/fixtures/al10-omit-dnf-automatic.host.yaml.tmpl \
SRC_ISO=/path/to/AlmaLinux-10.2-x86_64-boot.iso \
STAGNATION_BUDGET=3600 \
  tests/install-regression/run.sh
```

## Two traps when driving this from an automated session

1. **Never background the launch** (a detached shell SIGHUPs QEMU) and
   **never pipe the run through `tail`** — a pipeline's exit status is the
   last command's, so a failed run reports success.
2. **`qemu-img info $BUILD/disk.qcow2` showing `disk size: ~196 KiB` means
   nothing was installed**, whatever the output says. `run.sh` now deletes
   `serial.log` at start so a dead run can no longer print the *previous*
   run's successful boot, but check the disk before believing a pass.

## Files

- `run.sh` — orchestrator. Generates an SSH keypair, renders the
  fixture with the public key inlined, runs `ks-gen gen`, runs
  `ks-gen iso` twice (locks in PR #55's idempotency fix), boots
  QEMU, polls SSH, runs the smoke check.
- `smoke-check.sh` — 14 assertions over SSH on the installed VM.
- `build-debug-iso.py` — wrapper around `ks_gen.iso.builder.build_iso`
  that monkey-patches the menu-entry constants in
  `ks_gen.iso.bootloader` to inject `inst.text inst.notmux
  inst.console=ttyS0,115200n8 console=ttyS0,115200n8`. No source edit.
- `fixtures/omit-dnf-automatic.host.yaml.tmpl` — fixture template
  with `__SSH_PUBKEY__` placeholder. `packages.required` explicitly
  omits `dnf-automatic` and `dnf-utils` so the harness exercises the
  #53 regression scenario every run — the load-bearing
  `dnf-automatic.timer active` assertion proves PR #56's
  `Rule.emit_packages` still works on real hardware.
- `keys/` — generated ed25519 keypair (runtime; on WSL ext4 because
  OpenSSH refuses the 0777 perms that /mnt/c forces).
- `build/` — symlink to `~/.cache/ks-gen-install-regression/` (on
  WSL ext4 for I/O performance and Unix-socket support).
- `issue-57-comment.md` — the public closing-comment posted to #57.
  Treat as the canonical recipe doc — if you change the recipe, sync
  this file and consider editing the issue comment.

## Last green run

2026-06-12. All 14 smoke-check assertions pass:

```
ok:   sshd active
ok:   chronyd active
ok:   firewalld active
ok:   auditd active
ok:   rsyslog active
ok:   dnf-automatic.timer active          ← #53 regression check
ok:   ks-gen-reboot-if-needed.timer enabled
ok:   ks-gen-dnf-automatic-full.timer enabled
ok:   faillock.conf has deny=3
ok:   /root/oscap-remediation-results.xml present
ok:   /root/oscap-remediation-report.html present
ok:   root password locked
ok:   aide installed
ok:   ks-post.log present and traced
```

## Six traps documented for future maintainers

(Full detail in issue #57's closing comment — see `issue-57-comment.md`.)

1. **`console=` argument order matters.** Trailing `console=tty0`
   sends anaconda's TUI to the invisible VGA framebuffer and the
   install hangs. Use `inst.text inst.notmux
   inst.console=ttyS0,115200n8 console=ttyS0,115200n8`.
2. **Disk size.** Default STIG layout needs ≥ 50G. Harness uses 60G
   qcow2 (sparse — costs ~the install footprint, not 60G).
3. **WSL `/mnt/c` (DrvFs).** Kills qcow2 perf (~10x slower than
   ext4), ignores `chmod` (breaks SSH key perms), rejects Unix
   sockets (breaks QEMU `-monitor unix:`). Keep runtime artifacts
   on ext4.
4. **`/dev/kvm` group membership.** Stock WSL Ubuntu has `/dev/kvm`
   as `crw-rw---- root:kvm 660`. Non-kvm-group users get no `-r` and
   the harness falls back to TCG.
5. **`passwd -S` on AlmaLinux 9 emits `LK`**, not the ` L ` some
   other distros use.
6. **WSL backgrounding kills xorriso.** `nohup ... &` inside
   `wsl -- bash -c '...'` dies on SIGHUP when the parent wsl.exe
   exits. Run interactively or keep the WSL session alive.
