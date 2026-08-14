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
   **never pipe the run through anything** — a pipeline's exit status is the
   last command's, so a failed run reports success. `tail` is the obvious
   offender, but `tr -d '\0'` to strip the NULs `wsl.exe` emits does it just
   as silently (hit 2026-08-13). Redirect to a log and read it separately.
2. **`qemu-img info $BUILD/disk.qcow2` showing `disk size: ~196 KiB` means
   nothing was installed**, whatever the output says. `run.sh` now deletes
   `serial.log` at start so a dead run can no longer print the *previous*
   run's successful boot, but check the disk before believing a pass.

## Files

- `run.sh` — orchestrator. Generates an SSH keypair, renders the
  fixture with the public key inlined, runs `ks-gen gen`, runs
  `ks-gen iso` twice (locks in PR #55's idempotency fix), boots
  QEMU, polls SSH, runs the smoke check.
- `smoke-check.sh` — the assertions run over SSH on the installed VM.
  Rule outcomes are re-scanned live with `oscap`; the ARF is only read for
  tailoring facts (see trap 7).
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
- `fixtures/al{8,9,10}-*.host.yaml.tmpl` — per-distro variants. The two
  `*-stig-crypto` ones cover the #66 split: AL9's stig profile refines the
  crypto policy to `FIPS:STIG`, AL10's to plain `FIPS`. `run.sh` reads
  `policy: STIG` out of the fixture and switches to an RSA key by itself,
  since ed25519 cannot authenticate to a FIPS host (#73).
- `keys/` — generated keypair (runtime; on WSL ext4 because
  OpenSSH refuses the 0777 perms that /mnt/c forces).
- `build/` — symlink to `~/.cache/ks-gen-install-regression/` (on
  WSL ext4 for I/O performance and Unix-socket support).
- `issue-57-comment.md` — the public closing-comment posted to #57.
  Treat as the canonical recipe doc — if you change the recipe, sync
  this file and consider editing the issue comment.

## Last green run

2026-08-13, **AlmaLinux 8.10 with `crypto.policy: MODERN`** (the #67 path,
`FIXTURE_TEMPLATE=fixtures/al8-omit-dnf-automatic.host.yaml.tmpl`). All 39
smoke-check assertions pass, `disk size: 7.22 GiB`. The #67 block:

```
ok:   live crypto policy is DEFAULT (as the kickstart intended)
ok:   configure_crypto_policy result <result>pass</result> matches policy DEFAULT
ok:   kernel command line carries no fips=1
ok:   /proc/sys/crypto/fips_enabled is 0
ok:   no /etc/dracut.conf.d/40-fips.conf
ok:   enable_dracut_fips_module: <result>notselected</result>
ok:   sysctl_crypto_fips_enabled: <result>notselected</result>
ok:   fips_crypto_subpolicy: absent from this datastream
ok:   system_booted_in_fips_mode: absent from this datastream
```

Note the `configure_crypto_policy` line above predates the live-re-scan change
(trap 7) and now reads `passes a live re-scan under policy DEFAULT`.

## Other runs

- **2026-08-14, AlmaLinux 10.2 / `MODERN`** (`al10-omit-dnf-automatic`,
  network install) — green end-to-end, `disk size: 4.24 GiB`. First AL10
  install this project has completed. The #67 block shows the per-distro
  split doing real work: `enable_dracut_fips_module` absent from the AL10
  datastream, while `fips_crypto_subpolicy` and `system_booted_in_fips_mode`
  — neither selected on AL8 — are `notselected`.
- **2026-08-14, AlmaLinux 10.2 / `STIG`** (`al10-stig-crypto`) — install
  green, `disk size: 4.26 GiB`, `%post` applied plain `FIPS` as AL10's
  profile expects. The smoke check initially failed on the ARF result for
  `configure_crypto_policy`; that assertion is what trap 7 replaced, and the
  updated script passes against the installed host. Not yet re-run
  end-to-end from a fresh install.
  This run also produced issue #84: a STIG host is not in FIPS *kernel*
  mode, so `sysctl_crypto_fips_enabled`, `system_booted_in_fips_mode` and
  `enable_fips_mode` fail on it permanently.
- **2026-06-12, AlmaLinux 9 default fixture** — 14 assertions.

## Eight traps documented for future maintainers

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
7. **The install-time ARF is not the installed host.** It is written by the
   oscap `%post`, which runs *before* ks-gen's rule `%post`. AL10's
   `configure_crypto_policy` additionally requires
   `/etc/crypto-policies/state/current` to be newer than `.../config`, so
   remediating and re-verifying inside the same second records `error`
   even though the finished host passes. Assert rule *outcomes* with a live
   `oscap` re-scan; the ARF is only good for tailoring facts like
   `notselected` (observed 2026-08-14, issue #84 came out of the same run).
8. **`smoke-check.sh` runs under `set -euo pipefail`.** An ARF grep for a
   rule the distro does not ship exits non-zero, and `x=$(...)` from a
   failing pipeline aborts the whole script — silently truncating the run
   after the assertions that already printed. End such substitutions with
   `|| true` and treat an empty result as "absent", not as failure.
