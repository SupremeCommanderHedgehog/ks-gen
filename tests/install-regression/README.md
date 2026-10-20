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

Requires WSL (or Linux) with `qemu-system-x86_64`, `xorriso`, mtools, OVMF, and
KVM. Everything it writes goes to `$BUILD`
(default `~/.cache/ks-gen-install-regression`), never into the repo.

AlmaLinux 10's standard `x86_64` media is built for **x86-64-v3** (AVX2, BMI2,
FMA, MOVBE); the `x86_64_v2` ISO is the variant for older CPUs. Under KVM the
harness passes the host CPU through (`-cpu host`), so the host itself must be
v3: check with `/lib64/ld-linux-x86-64.so.2 --help | grep x86-64-v3`, which
should say `supported`. Under TCG the harness uses `-cpu max`. Whether that covers
v3 depends on the QEMU version, so a v3 ISO may not boot there. On such hosts,
or ones without v3, use the v2 ISO.
ks-gen's AL10 network-install mirrors point at the `x86_64` repo tree, so the
v3 ISO is the one that matches a real install (#127).

The VM needs outbound network through QEMU's user-mode NAT: network-install
fixtures fetch packages, and smoke-check waits for chrony to actually sync
(`chronyc waitsync`, up to 150s), so outbound UDP 123 must be open (#50). The
`al10-nts` fixture also needs outbound TCP 4460 for NTS key exchange (#125).
A "chrony never synced" failure on a host that blocks NTP is the environment,
not the install.

## How to run

To validate a change to the install pipeline, run **every media mode**:

```bash
wsl -- bash -c "cd \"$(git rev-parse --show-toplevel)\" && tests/install-regression/run-all.sh"
```

`run-all.sh` runs the CD variant, then the USB variant, then the emulated
Rufus ISO-mode variant (`usb-iso`, below) against the same `installer.iso`
(reused only if the CD run finished building it), and exits non-zero if any
failed. Per mode, `$BUILD/run-all/` keeps that run's `serial.log`/`qemu.log`
and the installed disk's `qemu-img info`, and the summary prints each disk's
size — trap 2 below applies to all of them. Expect roughly three times a
single run's wall-clock. `FORCE_ISO_REBUILD=1` rebuilds the
ISO even if `SKIP_ISO_BUILD` is set.

**CD-mode alone is no longer sufficient** (#26). `MEDIA=cd` (the default for
`run.sh`) attaches the ISO as `/dev/sr0`, where anaconda auto-detects its
install source. Operators boot a `dd`/Rufus-DD **USB stick**, which is a disk
(`/dev/sda`) with no such auto-detection — PR #73's two bugs (no
`inst.repo=hd:LABEL=...`, no top-level `user` directive) passed CD and failed
only there. `MEDIA=usb` reproduces that path:

```bash
MEDIA=usb tests/install-regression/run.sh
```

It attaches the ISO as xHCI USB mass storage through a fresh copy-on-write
overlay (`$BUILD/usb-stick.qcow2`), so the guest sees exactly the bytes `dd`
would write without a multi-GiB copy, with no `bootindex` (which QEMU re-applies every boot
and would reinstall forever, since a stick is never ejected).

### Rufus ISO Image mode (`MEDIA=usb-iso`, #134)

MANUAL §8.6 tells Windows operators to use Rufus's **ISO Image mode**, not DD.
That writes a different stick: an MBR disk with one FAT32-LBA partition, the
ISO9660 *tree* copied onto it file by file, and Rufus's own edits to the
boot configs. On UEFI that FAT32 partition is what firmware boots, so
`/EFI/BOOT/BOOTX64.EFI` reads the **tree's** `/EFI/BOOT/grub.cfg`. The EFI
image that the CD and `usb` modes boot from isn't involved. No Windows
machine is available to the project, so `rufus-iso-stick.py` rebuilds that
stick from Rufus's source:

```bash
MEDIA=usb-iso tests/install-regression/run.sh
```

What Rufus v4.15 does (github.com/pbatard/rufus, tag `v4.15`, `6d8fbf98`),
and what the emulation mirrors:

- **Label** (`format.c` `ToValidLabel`): the stick's FAT32 label is the ISO's
  volume ID with `*?,;:/\|+=<>[]"` dropped, non-ASCII, tab and `.` turned into
  `_`, upper-cased, and cut to 11 characters. A result that is mostly
  underscores becomes the disk size, e.g. `8_0 GB`. ks-gen's default
  `KS-AL<major>-<minor>` comes through unchanged
  (`tests/test_rufus_iso_emulation.py` pins it).
- **Label rewrite** (`iso.c` `fix_config`, `parser.c`
  `replace_in_token_data`): in every `*.cfg` (plus the syslinux names and
  `/loader/entries/*.conf`), on each line whose first word is `options`,
  `append`, `linux`, `linuxefi`, `$linux`, `search` or `for` followed by
  whitespace, it replaces the ISO label (spaces as `\x20`) with the stick's,
  up to 4 times per line. So a label Rufus shortens or upper-cases is
  patched to match, not broken. With ks-gen's default the two are equal and
  nothing is rewritten. To exercise the rewrite, build with a label Rufus
  must change: `VOLID=ks-al10-2x MEDIA=usb-iso run.sh` (`VOLID` is passed
  to `build-debug-iso.py`; the stick comes out `KS-AL10-2X`). Note that **`ks.cfg` is a `*.cfg`**, so a `%post`
  `for …` line that mentioned the label would be rewritten too. None does.
- **`inst.stage2` → `inst.repo`** (same function): for media whose *volume
  ID* matches `^AlmaLinux-[8-9].*` (or other RHEL 8/9 derivatives, `rufus.c`
  `redhat8_derivative`), and whose file name lacks `netinst`, Rufus rewrites
  `inst.stage2` to `inst.repo` on those lines. ks-gen's `KS-AL…` labels
  never match, and nor did the old `ALMA9`, so it doesn't fire. That matters
  for network installs: their entry deliberately has no `inst.repo`, and the
  rewrite would point the install source at a boot ISO with no packages.
- **Which `grub.cfg`**: Rufus copies the tree, and only unpacks the EFI image
  when the tree has no usable `BOOTX64.EFI` (`iso.c`, `DumpFatDir`). AlmaLinux
  media always have one.

Not reproduced: Rufus's **BIOS/legacy bootloader** (it installs its own
syslinux/GRUB for CSM boot). The harness boots OVMF, so no mode covers BIOS
boot. Also Rufus releases after v4.15: re-check `fix_config` and
`redhat8_derivative` when bumping the pinned version.

A full USB run needs the same install source as a CD run. A fixture that
installs from the ISO itself (the default `install.source`) needs a DVD
`SRC_ISO`; a network-install fixture such as `al10-omit-dnf-automatic` works
from a boot ISO. A boot ISO with an install-from-ISO fixture stops at
anaconda's "Installation source" error in either mode.

The harness ISO carries the boot entries `ks-gen iso` would build for the
same bundle (#136). `build_iso` decides `network_install` from `ks.cfg`
when it isn't given (`ks_gen.iso.kickstart_is_network`: a `url` command
outside any `%` section), so a network fixture's entry has no `inst.repo=hd:LABEL=`. `run.sh`
checks it twice: in the built ISO's `/EFI/BOOT/grub.cfg` before QEMU starts,
and in the installer kernel's command line in `serial.log` as soon as it is
logged. Either fails the run if `inst.repo=` is present for a network
install, missing for a media install, or names a different label from
`inst.ks=`. The usb-iso exception: when Rufus's RH8+
`inst.stage2` → `inst.repo` rewrite fires (above), `inst.repo=` is expected
either way. Every run recorded below from before #136 booted network
fixtures *with* `inst.repo=hd:LABEL=`, so none of them covers the entry
network-install operators get.

To run a single mode with `run.sh`:

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

### Admin identity and disk size

`ADMIN_USER` and `ADMIN_SUDO_MODE` are **derived from the fixture's
`user.admin` block**, the same way `KEY_TYPE` is derived from its crypto
policy — a mismatch does not fail fast, it burns the whole
`DEADLINE_SECONDS` budget and then reports "SSH never came up", which reads
as a product failure. Override only to contradict the fixture.

On that timeout the harness prints the last ssh error. "Connection refused"
or a timeout means sshd never started; an authentication error means the
guest is up and the problem is the key, user or `KEY_TYPE`. The harness
runs ssh with `-F /dev/null -o IdentitiesOnly=yes`. Do the same when you
SSH in by hand, or the keys in a loaded ssh-agent exhaust the STIG sshd's
`MaxAuthTries` (default 4) before `-i` is tried, and the guest refuses you
with "Too many authentication failures":

```bash
ssh -F /dev/null -o IdentitiesOnly=yes -i build/keys/id_ed25519 -p 2222 opsadmin@127.0.0.1
```

| Var | Default | Notes |
|---|---|---|
| `ADMIN_USER` | fixture's `user.admin.name` (else `opsadmin`) | who the harness SSHes in as |
| `ADMIN_SUDO_PASSWORD` | empty | **required** when the fixture is `sudo: nopasswd_no`; ignored (and cleared) otherwise, since sudo would not consume it and it would land on the smoke check's stdin |
| `DISK_SIZE` | `60G` | must carry a unit suffix — a bare `800` is 800 *bytes* to `qemu-img` and fails an hour later as an opaque anaconda partitioning error |

Sizing note: qcow2 is sparse, so a larger `DISK_SIZE` costs only what anaconda
actually writes — but size the **host's** free space to the install, not to
`DISK_SIZE`. A workstation fixture with ~700G of thick LVs consumed ~11 GiB of
an 800G virtual disk, and a guest that really did fill it would fill the host.

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

- `run-all.sh` — runs `run.sh` with `MEDIA=cd`, `MEDIA=usb` and
  `MEDIA=usb-iso`; the invocation to use when validating an install-pipeline
  change (#26, #134).
- `rufus-iso-stick.py` — builds the `MEDIA=usb-iso` stick: an emulated Rufus
  v4.15 ISO Image-mode write of `installer.iso` (see above).
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
  It leaves `network_install` to `build_iso`, which reads it off the
  bundle's `ks.cfg` (#136).
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
- `fixtures/al10-container-users.host.yaml.tmpl` — the only boot-ISO fixture
  with a non-empty `containers.users`, so the only one whose `%post` actually
  runs `create-rootless-user.sh` (`container-users` does too, but installs from
  an AL9 DVD). `run.sh` reads the provisioned users out of `ks.cfg`
  (`# Provision container user:`) into `EXPECTED_CONTAINER_USERS`.
  smoke-check then asserts each user's home, storage, linger, and init files
  at 0740 or stricter. The live scan of whichever STIG init-file rule the
  profile selects runs on every fixture (#49).
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

- **2026-10-20, the network-install boot entry, first booted** (#136, AL10.2
  x86_64 boot ISO, every AL10 network fixture). `run-all.sh` green on all
  three media for each, booting `inst.stage2=hd:LABEL=KS-AL10-2
  inst.ks=hd:LABEL=KS-AL10-2:/ks.cfg` with no `inst.repo=`, the entry
  `ks-gen iso` ships for a `url` kickstart. Both boot-entry checks passed
  in every mode, and Rufus's RH8 rewrite did not fire on the usb-iso sticks.
  Installed disk sizes (cd / usb / usb-iso, GiB):
  `al10-omit-dnf-automatic` 3.92 / 3.90 / 3.93 (re-run on the final code),
  `al10-stig-crypto` 3.95 / 3.86 / 4.06,
  `al10-nts` 3.83 / 3.90 / 3.92,
  `al10-container-users` 3.95 / 3.99 / 3.92.
- **2026-10-20, all three media incl. emulated Rufus ISO mode** (#134,
  `al10-omit-dnf-automatic`, AL10.2 x86_64 boot ISO, network install).
  `run-all.sh` green on `cd` (`3.89 GiB`), `usb` (`3.93 GiB`) and `usb-iso`
  (`3.96 GiB`), 40 smoke checks each. The `usb-iso` stick came out as FAT32
  label `KS-AL10-2`, identical to the volume ID, so Rufus's label rewrite was
  a no-op, and the RH8 `inst.stage2`→`inst.repo` rewrite did not fire. The
  kernel booted from the copied tree's `grub.cfg` with
  `inst.ks=hd:LABEL=KS-AL10-2:/ks.cfg`, found on `sda1`. First install from
  anything resembling the stick MANUAL §8.6 tells operators to write.
  Then `VOLID=ks-al10-2x MEDIA=usb-iso` to exercise Rufus's label rewrite:
  the stick came out `KS-AL10-2X`, 8 lines each in the EFI and BIOS
  `grub.cfg` were rewritten (6 `linux`/`linuxefi`, 2 `search`), and the
  install passed (40 checks, `3.93 GiB`). The kernel booted with
  `hd:LABEL=KS-AL10-2X`, and `ks.cfg`, which reads its label off the kernel
  command line, followed.
- **2026-10-20, AlmaLinux 10.2 / container user** (`al10-container-users`, x86_64
  boot ISO, network install). `run-all.sh` green on CD (`4.01 GiB`) and USB
  (`3.91 GiB`). The #49 run: `webapp`'s skel `.bashrc` came out `640`, and
  AL10's stig rule `file_permission_user_init_files` passes a live re-scan
  covering `webapp`, the admin user and root. So `create-rootless-user.sh`'s
  `setpriv`-dropped `find` works inside anaconda's `%post`. AL10 does not
  select the `_root` variant (AL8/AL9 do). Note that `oscap --rule` evaluates a
  rule whether or not the profile selects it, so smoke-check reads selection
  from the ARF instead. The same invocation was also checked by hand
  in `almalinux:8` and `almalinux:9` containers (util-linux 2.32 / 2.37), from
  `/root` as `%post` runs it.
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
  This run also produced issue #84: a STIG host was not in FIPS *kernel*
  mode, so `sysctl_crypto_fips_enabled`, `system_booted_in_fips_mode` and
  `enable_fips_mode` failed on it on every scan. Fixed on
  `feat/84-stig-kernel-fips` — `%post` now enables kernel FIPS natively
  (`/etc/system-fips`, `40-fips.conf`, `dracut -f --regenerate-all`,
  `grubby`), and the `FIPS*` arm of `smoke-check.sh` asserts the installed
  host really boots in FIPS mode. An intermediate run that day aborted in
  `%post` on `fips-mode-setup: command not found` — AL10 ships no such
  command — which is why the mechanism is native.
- **2026-08-14, AlmaLinux 10.2 / `STIG` with kernel FIPS** (`al10-stig-crypto`,
  network install) — green end-to-end, `disk size: 4.36 GiB`. First ks-gen host
  of any distro that actually boots in FIPS mode, and the run that closes #84.
  The whole `FIPS*` arm on its first real exercise:

```
ok:   kernel booted with fips=1
ok:   kernel command line carries boot=UUID=
ok:   /proc/sys/crypto/fips_enabled is 1
ok:   /etc/dracut.conf.d/40-fips.conf present
ok:   enable_fips_mode: pass
ok:   sysctl_crypto_fips_enabled: pass
ok:   fips_crypto_subpolicy: pass
ok:   system_booted_in_fips_mode: pass
ok:   enable_dracut_fips_module: absent from this datastream
```

  That the host booted at all is the load-bearing result: it confirms
  `01fips-crypto-policies` self-enables via its own `check()`, so naming only
  `fips` in `40-fips.conf` yields a correct initramfs. Until this run that was
  read out of dracut's `module-setup.sh`, not observed. SSH-with-RSA also
  authenticated under FIPS (#73), since the smoke check ran at all.
- **2026-08-14, AlmaLinux 9.8 / `STIG` with kernel FIPS** (`al9-stig-crypto`,
  network install) — green end-to-end, `disk size: 5.02 GiB`. The second half
  of #84's merge gate, and the run that proves the shared mechanism did not
  cost AL9 its sub-policy:

```
ok:   live crypto policy is FIPS:STIG (as the kickstart intended)
ok:   /proc/sys/crypto/fips_enabled is 1
ok:   enable_fips_mode: pass
ok:   sysctl_crypto_fips_enabled: pass
ok:   fips_crypto_subpolicy: pass
ok:   enable_dracut_fips_module: pass
ok:   system_booted_in_fips_mode: absent from this datastream
```

  `enable_dracut_fips_module: pass` is the notable one. It is stig-selected on
  AL9 with **no remediation shipped** in ssg-almalinux9 0.1.80, so it failed on
  every AL9 STIG host — a fourth permanently-failing rule #84 never listed.
  Writing `40-fips.conf` ourselves is what the missing remediation would have
  done, so it now passes rather than needing an `exceptions.md` entry.
  Note the mirror-image datastream split against AL10: `system_booted_in_fips_mode`
  is absent here and present there, `enable_dracut_fips_module` the reverse.
- **2026-10-20, AlmaLinux 10.2 on the x86-64-v3 `x86_64` boot ISO** (#127) —
  all three AL10 fixtures green end-to-end through `run-all.sh`, CD **and**
  USB, under KVM with `-cpu host`. Every earlier AL10 run above booted the
  `x86_64_v2` ISO; this is the first on the media that matches the `x86_64`
  repo tree the network install pulls from:

  | Fixture | Smoke checks | CD disk | USB disk |
  |---|---|---|---|
  | `al10-omit-dnf-automatic` (MODERN) | 38 | 4 GiB | 3.88 GiB |
  | `al10-stig-crypto` (STIG, kernel FIPS) | 40 | 4 GiB | 3.95 GiB |
  | `al10-nts` (MODERN + `time.nts`) | 39 | 3.94 GiB | 3.96 GiB |

  Coverage previously seen only on v2 now passes on v3: the chrony STIG
  directives and `chrony-wait` override (#124) on all three; `time is
  NTS-authenticated` on `al10-nts` (#125); kernel FIPS on `al10-stig-crypto`,
  whose bundle carries the `chrony_set_nts` exception with the FIPS / AES-SIV
  reason and deselects the rule in `tailoring.xml` (#126); and the USB runs boot
  through the ESP `grub.cfg` patching (#117). Nothing differed from the v2 runs
  apart from slightly smaller disks (4.24 → 3.88–4 GiB MODERN, 4.36 → 3.95–4 GiB
  STIG). The vendor ISO's volume ID (`AlmaLinux-10-2-x86_64-dvd`) and layout
  (ESP as appended GPT partition 2) match the v2 ISO's, and the built
  installer's El Torito and ESP `grub.cfg` both carry the ks-gen entry. Both still
  pointed at the then-hardcoded `ALMA9` label (#128; installers are now
  labelled `KS-AL<major>-<minor>`, e.g. `KS-AL10-2`).
- **2026-06-12, AlmaLinux 9 default fixture** — 14 assertions.

## Eight traps documented for future maintainers

(Full detail in issue #57's closing comment — see `issue-57-comment.md`.)

1. **`console=` argument order matters.** Trailing `console=tty0`
   sends anaconda's TUI to the invisible VGA framebuffer and the
   install hangs. Use `inst.text inst.notmux
   inst.console=ttyS0,115200n8 console=ttyS0,115200n8`.
2. **Disk size.** Default STIG layout needs ≥ 50G. Harness defaults to a 60G
   qcow2 (sparse — costs ~the install footprint, not 60G), overridable with
   `DISK_SIZE`.
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
