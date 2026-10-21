#!/usr/bin/env bash
# On-demand end-to-end install regression harness (closed issue #57).
#
# Runs inside WSL Ubuntu (or any Linux with QEMU + OVMF). Drives the full
# pipeline:
#   1. ks-gen gen + ks-gen iso (twice — exercises #52 idempotency)
#   2. boot the ISO in QEMU/OVMF (KVM if available, else TCG), as a CD or
#      as a USB stick, or as an emulated Rufus ISO-mode stick
#      (MEDIA=cd|usb|usb-iso), or as a CD under SeaBIOS (FIRMWARE=bios);
#      run-all.sh runs all four
#   3. wait for anaconda to install + reboot + sshd to come up
#   4. SSH in and run smoke-check.sh
#
# Local-only by design (not in GitHub Actions — full run is 30-90 min on
# TCG, which would burn workflow minutes for a check that's only useful
# when changes touch the install pipeline). When to recommend running:
# see project CLAUDE.md → "Install-regression harness".
set -euo pipefail

# ---- paths ----------------------------------------------------------------
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
# Keys must live on ext4 — OpenSSH refuses 0777 private keys, and
# /mnt/c (DrvFs) ignores chmod, so a key written under .scratch/ stays
# world-readable. Park them next to the runtime build dir.
KEYS="${KEYS:-$HOME/.cache/ks-gen-install-regression/keys}"
FIXTURES="$HERE/fixtures"
# QEMU on the WSL 9p mount (/mnt/c) crawls — anaconda's many-small-writes
# DNF transaction is the worst-case workload. Put everything QEMU touches
# on the WSL ext4 disk. Mirror the path back to the Windows-side build/
# via a symlink so artifacts stay browseable from PowerShell.
BUILD="${BUILD:-$HOME/.cache/ks-gen-install-regression}"
mkdir -p "$BUILD"
# Rebuild the link when it is missing, is not a symlink, or DANGLES. Testing
# only for -L left a dangling link untouched forever: a checkout migrated
# between machines kept a link into the old host's home directory silently,
# because a broken symlink is still a symlink. `-e` follows the link, so
# `! -e` is exactly the dangling case ($BUILD already exists by now, via the
# mkdir above).
#
# Deliberately NOT "repoint whenever the target differs from $BUILD": with
# BUILD set to somewhere at or under $HERE/build, that aims the link inside
# itself and every subsequent write dies with ELOOP. The link is cosmetic —
# nothing in this script reads through it, $BUILD is used directly — so
# leaving a valid link alone is the safe behaviour.
#
# rm -rf first because `ln -sfn` does NOT replace a real directory: it creates
# the link *inside* it and still exits 0.
if [[ ! -L "$HERE/build" || ! -e "$HERE/build" ]]; then
  rm -rf "$HERE/build"
  ln -sfn "$BUILD" "$HERE/build"
fi

KS_GEN="${KS_GEN:-$HOME/.venvs/ks-gen/bin/ks-gen}"
KS_GEN_PY="${KS_GEN_PY:-$HOME/.venvs/ks-gen/bin/python}"

SRC_ISO="${SRC_ISO:-$REPO/AlmaLinux-9-latest-x86_64-dvd.iso}"

# Default fixture is the AL9 STIG one. Override with FIXTURE_TEMPLATE
# (absolute or harness-relative) to run a different cfg — e.g., the AL8
# fixture at fixtures/al8-omit-dnf-automatic.host.yaml.tmpl.
#
# Defined here rather than at step 2 because step 1 greps it to pick KEY_TYPE,
# and the admin defaults below are derived from it too. Under `set -u` the
# earlier reference aborted the run outright unless the caller happened to
# export FIXTURE_TEMPLATE, which is why only overridden invocations worked.
FIXTURE_TEMPLATE="${FIXTURE_TEMPLATE:-$FIXTURES/omit-dnf-automatic.host.yaml.tmpl}"
[[ -r "$FIXTURE_TEMPLATE" ]] || { echo "missing fixture template: $FIXTURE_TEMPLATE" >&2; exit 1; }

# Read one scalar out of the fixture's user.admin block. Indentation-scoped so
# a `name:` or `sudo:` elsewhere in the cfg cannot be picked up by accident.
fixture_admin_field() {
  awk -v want="$1:" '
    /^user:/                          { in_user = 1; next }
    in_user && /^[^[:space:]]/        { in_user = 0; in_admin = 0 }
    in_user && /^[[:space:]]+admin:/  { in_admin = 1; next }
    in_admin && /^[[:space:]]{1,2}[^[:space:]]/ { in_admin = 0 }
    in_admin && $1 == want            { print $2; exit }
  ' "$FIXTURE_TEMPLATE"
}

# The admin account the fixture creates — this is who we SSH in as. DERIVED
# from the fixture for the same reason KEY_TYPE is (see step 1): getting it
# wrong does not fail fast, it burns the whole DEADLINE_SECONDS budget and then
# reports "SSH never came up", which reads as a product failure rather than a
# harness misconfiguration. An explicit ADMIN_USER still wins.
ADMIN_USER="${ADMIN_USER:-$(fixture_admin_field name)}"
ADMIN_USER="${ADMIN_USER:-opsadmin}"

# Likewise for the sudo mode. A nopasswd_no fixture needs ADMIN_SUDO_PASSWORD
# or the smoke check dies on "sudo: no tty present" at the very end of the run;
# a nopasswd_yes fixture must NOT be handed one, because sudo then never reads
# stdin and the password stays on the pipe for the smoke check to inherit.
ADMIN_SUDO_MODE="${ADMIN_SUDO_MODE:-$(fixture_admin_field sudo)}"
ADMIN_SUDO_MODE="${ADMIN_SUDO_MODE:-nopasswd_yes}"
# Fed over ssh stdin, never as a command argument, so it stays out of the
# guest's process list.
ADMIN_SUDO_PASSWORD="${ADMIN_SUDO_PASSWORD:-}"

# Virtual disk size. Raise it for a fixture whose layout allocates more than
# the 60G default.
DISK_SIZE="${DISK_SIZE:-60G}"

# How the installer reaches the VM (#26). `cd` attaches the ISO as a SATA
# CD-ROM (/dev/sr0), where anaconda auto-detects its install source. `usb`
# writes the ISO byte-for-byte to a raw image and attaches it as USB mass
# storage (/dev/sda) — what an operator gets from `dd` or Rufus's DD mode.
# That path has no CD auto-detection, so it needs inst.repo=hd:LABEL=... and
# a top-level `user` directive; both shipped broken in v0.11.0 (PR #73) and
# only the USB path shows it. `usb-iso` emulates Rufus's *ISO* Image mode,
# which MANUAL §8.6 recommends: an MBR stick with one FAT32 partition, the
# ISO tree copied onto it with Rufus's config rewrites, so UEFI boots the
# tree's /EFI/BOOT/grub.cfg rather than the EFI image's (#134). See
# rufus-iso-stick.py for what it does and doesn't reproduce.
MEDIA="${MEDIA:-cd}"
[[ "$MEDIA" == cd || "$MEDIA" == usb || "$MEDIA" == usb-iso ]] || {
  echo "MEDIA must be cd, usb or usb-iso (got: $MEDIA)" >&2; exit 1; }
echo "install media: $MEDIA"

# Firmware the VM boots (#140). `uefi` is OVMF on q35. `bios` is SeaBIOS on
# the i440fx `pc` machine, what BIOS-only hypervisors (many cloud VPSes)
# present. AL10's installer labels the disk GPT either way, which BIOS can
# only boot from a biosboot partition. CD only: anaconda's `reboot --eject`
# is what moves SeaBIOS on to the installed disk, and a stick is never
# ejected.
FIRMWARE="${FIRMWARE:-uefi}"
[[ "$FIRMWARE" == uefi || "$FIRMWARE" == bios ]] || {
  echo "FIRMWARE must be uefi or bios (got: $FIRMWARE)" >&2; exit 1; }
[[ "$FIRMWARE" == uefi || "$MEDIA" == cd ]] || {
  echo "FIRMWARE=bios needs MEDIA=cd (got: $MEDIA)" >&2; exit 1; }
echo "firmware: $FIRMWARE"

# Ubuntu's ovmf package. As of 26.04 the legacy plain-name files
# (OVMF_CODE.fd) are gone; only the 4M variants ship. SecureBoot off
# variant — kickstart has no secure-boot signing story.
OVMF_CODE="${OVMF_CODE:-/usr/share/OVMF/OVMF_CODE_4M.fd}"
OVMF_VARS_TEMPLATE="${OVMF_VARS_TEMPLATE:-/usr/share/OVMF/OVMF_VARS_4M.fd}"

INSTALLER_ISO="$BUILD/installer.iso"
USB_IMG="$BUILD/usb-stick.qcow2"
USB_ISO_IMG="$BUILD/usb-iso-stick.raw"
# Written only after both ISO builds succeed, so a reuser can tell a finished
# image from one a failed build left half-written (run-all.sh keys on it).
ISO_OK="$INSTALLER_ISO.ok"
BUNDLE_DIR="$BUILD/bundle"
DISK="$BUILD/disk.qcow2"
# Second virtio disk for disk.target validation (#59). Pre-filled with a
# magic marker; smoke-check.sh asserts the marker survives the install. If
# ignoredisk/clearpart/bootloader/--ondisk aren't honoring cfg.disk.target,
# anaconda will reformat this disk and the marker bytes disappear.
DATA_DISK="$BUILD/data-disk.raw"
DATA_DISK_MARKER="KS_GEN_DISK_TARGET_REGRESSION_MARKER_2026_06_12"
NVRAM="$BUILD/OVMF_VARS.fd"
SERIAL_LOG="$BUILD/serial.log"
QEMU_LOG="$BUILD/qemu.log"
# Override to run beside another VM that already forwards 2222.
SSH_HOST_PORT="${SSH_HOST_PORT:-2222}"
[[ "$SSH_HOST_PORT" =~ ^[1-9][0-9]{0,4}$ ]] && (( SSH_HOST_PORT <= 65535 )) \
  || { echo "SSH_HOST_PORT must be a port number, 1-65535 (got: $SSH_HOST_PORT)" >&2; exit 1; }
# Keyed to the port, so two runs side by side don't share a monitor socket.
QMP_SOCK="/tmp/ks-gen-install-regression-qmp-$SSH_HOST_PORT.sock"

# ---- preflight ------------------------------------------------------------
for bin in qemu-system-x86_64 qemu-img xorriso mcopy ssh-keygen ssh "$KS_GEN" "$KS_GEN_PY"; do
  command -v "$bin" >/dev/null 2>&1 || { echo "missing: $bin" >&2; exit 1; }
done
if [[ "$FIRMWARE" == uefi ]]; then
  [[ -r "$OVMF_CODE"          ]] || { echo "missing: $OVMF_CODE (apt install ovmf)"      >&2; exit 1; }
  [[ -r "$OVMF_VARS_TEMPLATE" ]] || { echo "missing: $OVMF_VARS_TEMPLATE (apt install ovmf)" >&2; exit 1; }
fi
[[ -r "$SRC_ISO"            ]] || { echo "missing: $SRC_ISO"                              >&2; exit 1; }
if [[ "$MEDIA" == usb-iso ]]; then
  command -v mkfs.fat >/dev/null 2>&1 \
    || { echo "missing: mkfs.fat (dosfstools; needed for MEDIA=usb-iso)" >&2; exit 1; }
fi
if [[ "$MEDIA" == usb* ]]; then
  # Captured, not piped into `grep -q`: grep exits on the first match, qemu
  # takes SIGPIPE, and pipefail would report a device that is there as missing.
  qemu_devices="$(qemu-system-x86_64 -device help 2>/dev/null)"
  for dev in qemu-xhci usb-storage; do
    [[ "$qemu_devices" == *"\"$dev\""* ]] \
      || { echo "missing: QEMU device $dev (needed for MEDIA=$MEDIA)" >&2; exit 1; }
  done
fi

# qemu-img takes a bare integer as BYTES, so a well-meant DISK_SIZE=800 creates
# an 800-byte image, succeeds, and surfaces an hour later as an opaque anaconda
# partitioning failure. Demand an explicit unit.
[[ "$DISK_SIZE" =~ ^[0-9]+([.][0-9]+)?[kKmMgGtT]$ ]] || {
  echo "DISK_SIZE must carry a unit suffix, e.g. 60G (got: $DISK_SIZE)" >&2; exit 1; }

# Fail fast on a sudo-mode/password mismatch rather than at the smoke check,
# which is 13-90 min in.
if [[ "$ADMIN_SUDO_MODE" == "nopasswd_no" && -z "$ADMIN_SUDO_PASSWORD" ]]; then
  echo "fixture $(basename "$FIXTURE_TEMPLATE") sets sudo: nopasswd_no —" >&2
  echo "set ADMIN_SUDO_PASSWORD to the admin's password or the smoke check" >&2
  echo "will fail with 'sudo: no tty present' after the full install." >&2
  exit 1
fi
if [[ "$ADMIN_SUDO_MODE" != "nopasswd_no" && -n "$ADMIN_SUDO_PASSWORD" ]]; then
  echo "[fixture is sudo: $ADMIN_SUDO_MODE] ignoring ADMIN_SUDO_PASSWORD — sudo"
  echo "would not consume it and it would leak onto the smoke check's stdin."
  ADMIN_SUDO_PASSWORD=""
fi

# ---- step 1: SSH key ------------------------------------------------------
# KEY_TYPE must suit the fixture's crypto policy. A FIPS/STIG host removes
# ssh-ed25519 from PubkeyAcceptedAlgorithms, so an ed25519 key cannot log in
# at all and the run times out at the SSH wait even on a perfect install
# (#73). Use KEY_TYPE=rsa for any crypto.policy: STIG fixture.
# Derived from the fixture rather than left to the caller: getting it wrong
# costs a full 13-90 min cycle and reports a spurious SSH timeout that looks
# like a product failure.
if [[ -z "${KEY_TYPE:-}" ]] && grep -qE '^[[:space:]]*policy:[[:space:]]*STIG' "$FIXTURE_TEMPLATE"; then
  KEY_TYPE=rsa
  echo "[fixture is crypto.policy: STIG] defaulting KEY_TYPE=rsa (ed25519 cannot log in under FIPS)"
fi
KEY_TYPE="${KEY_TYPE:-ed25519}"
if [[ "$KEY_TYPE" == "ed25519" ]] && grep -qE '^[[:space:]]*policy:[[:space:]]*STIG' "$FIXTURE_TEMPLATE"; then
  echo "refusing to run a crypto.policy: STIG fixture with an ed25519 key — it cannot authenticate (#73)" >&2
  exit 1
fi
KEY="$KEYS/id_$KEY_TYPE"
mkdir -p "$KEYS"
chmod 700 "$KEYS"
if [[ ! -f "$KEY" ]]; then
  keygen_args=(-t "$KEY_TYPE" -N '' -C 'ks-gen-install-regression' -f "$KEY")
  # RSA defaults to 2048; FIPS/STIG wants >= 3072.
  [[ "$KEY_TYPE" == "rsa" ]] && keygen_args+=(-b 3072)
  ssh-keygen "${keygen_args[@]}" >/dev/null
fi
chmod 600 "$KEY"
PUBKEY="$(cat "$KEY.pub")"

# ---- step 2: render host.yaml ---------------------------------------------
HOST_YAML="$BUILD/host.yaml"
# FIXTURE_TEMPLATE is resolved and checked up in the config block, because
# step 1 needs it to derive KEY_TYPE.
# sed substitution rather than envsubst so the public key (which contains '+'
# and '/') passes through unmangled. The placeholder is fixed and unique.
awk -v pk="$PUBKEY" '{ gsub(/__SSH_PUBKEY__/, pk); print }' \
  "$FIXTURE_TEMPLATE" > "$HOST_YAML"

# ---- step 3: ks-gen gen ---------------------------------------------------
rm -rf "$BUNDLE_DIR"
"$KS_GEN" gen --config "$HOST_YAML" --out "$BUNDLE_DIR"


# ---- step 4: ks-gen iso (twice; locks in PR #55 / issue #52) --------------
# Uses build-debug-iso.py instead of the CLI so we can inject the debug
# console args into the menu entries — anaconda's text-mode log lands on
# the serial port that QEMU captures.
# Set SKIP_ISO_BUILD=1 to skip rebuilding when iterating on QEMU/kickstart
# changes that don't affect the ISO contents (saves ~3 min/run).
if [[ -z "${SKIP_ISO_BUILD:-}" ]] || [[ ! -f "$INSTALLER_ISO" ]]; then
  rm -f "$ISO_OK"
  "$KS_GEN_PY" "$HERE/build-debug-iso.py" "$SRC_ISO" "$BUNDLE_DIR" "$INSTALLER_ISO"
  "$KS_GEN_PY" "$HERE/build-debug-iso.py" "$SRC_ISO" "$BUNDLE_DIR" "$INSTALLER_ISO"
  touch "$ISO_OK"
else
  echo "[SKIP_ISO_BUILD] reusing $INSTALLER_ISO"
  # The guest installs the ks.cfg baked into that ISO, not the one step 3 just
  # regenerated. Take the expectation from what actually ships.
  xorriso -osirrox on -indev "$INSTALLER_ISO" -extract /ks.cfg "$BUNDLE_DIR/ks.cfg" \
    >/dev/null 2>&1 || { echo "cannot read /ks.cfg back out of $INSTALLER_ISO" >&2; exit 1; }
fi

# The crypto policy the kickstart intends to leave the host in, taken from the
# rule's own header comment ("... policy: STIG (FIPS:STIG)"). The ARF cannot
# show whether %post achieved it — oscap runs BEFORE the rule %post — so the
# smoke check asserts the live state against this instead (#66). Read after
# step 4 so a reused ISO's own ks.cfg is what it is taken from.
EXPECTED_CRYPTO_POLICY="$(sed -n 's/^# Apply system-wide crypto policy: .*(\(.*\))$/\1/p' \
  "$BUNDLE_DIR/ks.cfg" | head -1)"
echo "expected crypto policy: ${EXPECTED_CRYPTO_POLICY:-<none found>}"

# The containers.users[] the kickstart provisions, from container_host's
# per-user header comment. Empty means the fixture's users list is empty, and
# smoke-check asserts no container user was created (#49).
EXPECTED_CONTAINER_USERS="$(sed -n 's/^# Provision container user: \([a-z_][a-z0-9_-]*\)$/\1/p' \
  "$BUNDLE_DIR/ks.cfg" | tr '\n' ' ')"
EXPECTED_CONTAINER_USERS="${EXPECTED_CONTAINER_USERS% }"
echo "expected container users: ${EXPECTED_CONTAINER_USERS:-<none>}"

# Whether the boot entry should carry inst.repo=hd:LABEL=: only for a media
# install. A network one drops it so anaconda takes packages from the
# kickstart's `url` (#136). The same detector build_iso uses (its cases are
# unit-tested); what the checks below catch is a built or booted entry that
# doesn't follow it.
INSTALL_KIND="$("$KS_GEN_PY" -c 'import sys
from pathlib import Path
from ks_gen.iso import kickstart_file_is_network
print("network" if kickstart_file_is_network(Path(sys.argv[1])) else "media")' \
  "$BUNDLE_DIR/ks.cfg")"
if [[ "$INSTALL_KIND" == network ]]; then EXPECT_INST_REPO=no; else EXPECT_INST_REPO=yes; fi
echo "install source: $INSTALL_KIND (boot entry inst.repo=: $EXPECT_INST_REPO)"

# Check one unattended boot line ($2, from $1) against EXPECT_INST_REPO: a
# harness ISO must carry what `ks-gen iso` ships for the same bundle. It once
# kept inst.repo=hd:LABEL= on every network fixture, so the entry network-
# install operators get was never booted (#136). Present, it must name the
# same label as inst.ks=.
check_boot_entry() {
  local where="$1" line="$2" label has
  label="$(sed -n 's/.*inst\.ks=hd:LABEL=\([^: ]*\):.*/\1/p' <<<"$line")"
  if [[ "$line" == *" inst.repo="* ]]; then has=yes; else has=no; fi
  if [[ "$has" != "$EXPECT_INST_REPO" ]]; then
    echo "boot entry mismatch in $where: $INSTALL_KIND install, expected inst.repo= $EXPECT_INST_REPO, got $has (#136):" >&2
    echo "  $line" >&2
    return 1
  fi
  if [[ "$has" == yes && "$line" != *" inst.repo=hd:LABEL=$label "* ]]; then
    echo "boot entry in $where: inst.repo= doesn't name inst.ks='s label ${label:-<none>}:" >&2
    echo "  $line" >&2
    return 1
  fi
}

# The built ISO's own entry, before anything boots: a wrong one (say a
# SKIP_ISO_BUILD reuse of an ISO from before #136) fails in seconds, not after
# an install. Only the tree's grub.cfg: the EFI image's copy, which the cd
# and usb modes boot, is covered by the booted check in step 7b.
iso_grub="$BUILD/installer-grub.cfg"
xorriso -osirrox on -indev "$INSTALLER_ISO" -extract /EFI/BOOT/grub.cfg "$iso_grub" \
  >/dev/null 2>&1 || { echo "cannot read /EFI/BOOT/grub.cfg out of $INSTALLER_ISO" >&2; exit 1; }
iso_entry="$(grep -m1 'inst\.ks=' "$iso_grub" || true)"
[[ -n "$iso_entry" ]] || { echo "no inst.ks= entry in $INSTALLER_ISO's grub.cfg" >&2; exit 1; }
check_boot_entry "installer.iso /EFI/BOOT/grub.cfg" "$iso_entry" || exit 1
# SeaBIOS boots the BIOS menu instead: EL10's i386-pc grub.cfg, or EL8/9's
# isolinux.cfg. Same check, so a BIOS-only menu regression fails here rather
# than as an interactive installer that never brings SSH up.
if [[ "$FIRMWARE" == bios ]]; then
  bios_cfg="$BUILD/installer-bios.cfg" bios_src=""
  for f in /boot/grub2/grub.cfg /isolinux/isolinux.cfg; do
    if xorriso -osirrox on -indev "$INSTALLER_ISO" -extract "$f" "$bios_cfg" >/dev/null 2>&1; then
      bios_src="$f"; break
    fi
  done
  [[ -n "$bios_src" ]] || { echo "no BIOS boot menu in $INSTALLER_ISO" >&2; exit 1; }
  bios_entry="$(grep -m1 'inst\.ks=' "$bios_cfg" || true)"
  [[ -n "$bios_entry" ]] || { echo "no inst.ks= entry in $INSTALLER_ISO's $bios_src" >&2; exit 1; }
  check_boot_entry "installer.iso $bios_src" "$bios_entry" || exit 1
fi
echo "ok: installer.iso boot entry matches a $INSTALL_KIND install"

# ---- step 5: disk + EFI nvram --------------------------------------------
[[ -f "$DISK" ]]      && rm "$DISK"
[[ -f "$DATA_DISK" ]] && rm "$DATA_DISK"
[[ -f "$NVRAM" ]]     && rm "$NVRAM"
# 60G covers the default STIG layout (15+5+3+10+5+3+2 = 43G of LVs + 1G boot
# + 1G EFI + recommended-size swap). qcow2 is sparse, so a bigger DISK_SIZE
# costs only what anaconda actually writes — but size the HOST's free space to
# the install, not to DISK_SIZE: a workstation fixture with ~700G of thick LVs
# consumed ~11 GiB of a 800G virtual disk, and a guest that really did fill it
# would fill the host too.
# Remove the previous run's serial log. If QEMU dies before writing one, the
# failure branches below would otherwise tail a stale log — which replays an
# EARLIER successful boot and reads as a passing run. That cost three
# misdiagnosed runs on 2026-08-12.
rm -f "$SERIAL_LOG" "$QEMU_LOG"

qemu-img create -f qcow2 "$DISK" "$DISK_SIZE" >/dev/null
# Data disk: 1G raw, pre-filled with the marker at offset 0. Small + raw
# so smoke-check can dd-read the first sector directly without parsing
# qcow2. The marker is the regression signal — if it survives, anaconda
# honored disk.target=vda and left vdb alone.
qemu-img create -f raw "$DATA_DISK" 1G >/dev/null
printf '%s' "$DATA_DISK_MARKER" \
  | dd of="$DATA_DISK" bs=1 conv=notrunc status=none
[[ "$FIRMWARE" == uefi ]] && cp "$OVMF_VARS_TEMPLATE" "$NVRAM"
# A fresh stick per run. The guest sees the ISO's bytes exactly as `dd` would
# write them, and the image is hybrid (MBR/GPT + EFI System partition, kept by
# xorriso's `-boot_image any replay`), so OVMF boots it as a removable disk.
# A qcow2 overlay rather than a copy: a DVD ISO is ~10 GiB, and any guest
# writes land in the overlay, leaving installer.iso untouched.
rm -f "$USB_IMG" "$BUILD/usb-stick.raw" "$USB_ISO_IMG"
if [[ "$MEDIA" == usb ]]; then
  qemu-img create -q -f qcow2 -F raw -b "$INSTALLER_ISO" "$USB_IMG"
elif [[ "$MEDIA" == usb-iso ]]; then
  # A real copy, not an overlay: the files are rewritten onto a new FAT32
  # filesystem, the way Rufus does. ~ISO size; a DVD stick is ~11 GiB.
  # Through tee, so a DVD-sized write streams and a failure keeps its output
  # (pipefail carries the script's status).
  "$KS_GEN_PY" -u "$HERE/rufus-iso-stick.py" "$INSTALLER_ISO" "$USB_ISO_IMG" \
    | tee "$BUILD/rufus-iso.log"
  # Rufus's RH8+ rewrite turns inst.stage2= into inst.repo=, so that stick
  # boots with one whatever the ISO's entry says.
  if grep -qx 'rufus-iso: rh8_stage2_rewrite=yes' "$BUILD/rufus-iso.log"; then
    EXPECT_INST_REPO=yes
  elif ! grep -qx 'rufus-iso: rh8_stage2_rewrite=no' "$BUILD/rufus-iso.log"; then
    echo "rufus-iso-stick.py printed no rh8_stage2_rewrite= line" >&2; exit 1
  fi
fi

# ---- step 6: boot QEMU ----------------------------------------------------
# Use KVM where /dev/kvm is readable; fall back to TCG (~3x slower).
ACCEL=()
[[ -r /dev/kvm ]] && ACCEL=(-enable-kvm -cpu host) || ACCEL=(-accel tcg -cpu max)

# Memory + cores: 4G/2 is enough for anaconda + oscap.
# Networking: SLIRP user net forwards host:$SSH_HOST_PORT → guest:22. DHCP is built in.
# Boot: leave EFI to decide. anaconda's `reboot --eject` will eject the CD on
#       success; OVMF's BootOrder gets written by anaconda's efibootmgr to
#       prefer the installed HD, so the second boot picks up the new system.
#       The USB stick gets no bootindex for the same reason: a bootindex is
#       re-applied by QEMU on every boot and would put the stick back in front
#       of the installed system, reinstalling forever. The stick is never
#       ejected, so that preference is all that stops the loop.
if [[ "$MEDIA" == usb ]]; then
  # shellcheck disable=SC2054  # commas separate QEMU sub-options, not elements
  MEDIA_ARGS=(-device qemu-xhci,id=xhci
              -drive if=none,id=usbstick,format=qcow2,file="$USB_IMG"
              -device usb-storage,bus=xhci.0,drive=usbstick,removable=on)
elif [[ "$MEDIA" == usb-iso ]]; then
  # shellcheck disable=SC2054
  MEDIA_ARGS=(-device qemu-xhci,id=xhci
              -drive if=none,id=usbstick,format=raw,file="$USB_ISO_IMG"
              -device usb-storage,bus=xhci.0,drive=usbstick,removable=on)
else
  MEDIA_ARGS=(-cdrom "$INSTALLER_ISO")
fi
if [[ "$FIRMWARE" == uefi ]]; then
  # shellcheck disable=SC2054
  FIRMWARE_ARGS=(-machine q35,smm=on
                 -drive if=pflash,format=raw,readonly=on,file="$OVMF_CODE"
                 -drive if=pflash,format=raw,file="$NVRAM")
else
  # SeaBIOS, disk before CD: the blank disk falls through to the CD on the
  # first boot, the installed one boots once the CD is ejected.
  FIRMWARE_ARGS=(-machine pc -boot order=cd)
fi
qemu-system-x86_64 \
  "${ACCEL[@]}" \
  -smp 2 -m 4096 \
  "${FIRMWARE_ARGS[@]}" \
  -drive file="$DISK",if=virtio,format=qcow2 \
  -drive file="$DATA_DISK",if=virtio,format=raw \
  "${MEDIA_ARGS[@]}" \
  -netdev user,id=n0,hostfwd=tcp:127.0.0.1:"$SSH_HOST_PORT"-:22 \
  -device virtio-net-pci,netdev=n0 \
  -nographic \
  -serial file:"$SERIAL_LOG" \
  -monitor unix:"$QMP_SOCK",server,nowait \
  > "$QEMU_LOG" 2>&1 &
QEMU_PID=$!
echo "qemu pid=$QEMU_PID  serial=$SERIAL_LOG"

cleanup() {
  if kill -0 "$QEMU_PID" 2>/dev/null; then
    kill "$QEMU_PID" 2>/dev/null || true
    sleep 1
    kill -9 "$QEMU_PID" 2>/dev/null || true
  fi
  # A usb-iso stick is a full copy of the ISO (~11 GiB for a DVD); nothing
  # reads it after the run. KEEP_USB_ISO=1 keeps it for inspection.
  [[ -n "${KEEP_USB_ISO:-}" ]] || rm -f "$USB_ISO_IMG"
}
trap cleanup EXIT

# ---- step 7: wait for SSH on host:$SSH_HOST_PORT --------------------------
# Generous-but-not-stupid: TCG anaconda install ~ 60-90 min. KVM ~ 8-15 min.
# Bound the outer wait at 90 min. Also abort if serial.log goes silent for
# 10 minutes — a hung anaconda emits nothing, and the first end-to-end
# attempt burnt 2h on exactly that failure mode (anaconda UI on tty0
# instead of ttyS0).
# DEADLINE_SECONDS + STAGNATION_BUDGET overridable via env. On TCG, the
# post-install rpm scriptlet phase (e.g., "Configuring nss" → cracklib-dicts)
# can go silent for many minutes while anaconda runs scriptlets without
# logging to console; bump STAGNATION_BUDGET=1800 to absorb that.
DEADLINE=$(( $(date +%s) + ${DEADLINE_SECONDS:-5400} ))
STAGNATION_BUDGET="${STAGNATION_BUDGET:-600}"
# Isolate the harness key. Without IdentitiesOnly, ssh offers every ssh-agent
# key before -i; -F /dev/null does the same for IdentityFile lines (and any
# User/ProxyJump/ControlMaster) in ~/.ssh/config. The STIG sshd disconnects
# after ssh.max_auth_tries failures (config.py default 4) with "Too many
# authentication failures", before the harness key is ever tried, and the run
# then waits out DEADLINE against a host that installed fine.
# Shared by ssh and scp; only the port flag differs (-p vs -P).
COMMON_SSH_OPTS=(-F /dev/null
                 -i "$KEY"
                 -o IdentitiesOnly=yes
                 -o StrictHostKeyChecking=no
                 -o UserKnownHostsFile=/dev/null
                 -o ConnectTimeout=5
                 -o LogLevel=ERROR)
SSH_OPTS=("${COMMON_SSH_OPTS[@]}" -p "$SSH_HOST_PORT")
SSH_ERR="$BUILD/ssh-wait.err"

# ---- step 7b: the boot entry the installer ran ---------------------------
# The kernel logs its command line at boot; the installer's is the first one
# with inst.ks= (the installed system's comes later, without it). Booted
# rather than built, so it covers the usb-iso stick's rewritten grub.cfg too.
# Returns 0 without checking while the line hasn't appeared yet, or hasn't
# been written to its newline: a half-written one isn't the whole entry.
boot_checked=""
check_booted_entry() {
  local lines line
  # Count the finished lines first and search only those: counted after the
  # grep, a line still being written could finish in between and pass.
  lines="$( { wc -l < "$SERIAL_LOG"; } 2>/dev/null)" || return 0
  line="$(head -n "$lines" "$SERIAL_LOG" | grep -a -m1 'Command line: .*inst\.ks=' || true)"
  [[ -n "$line" ]] || return 0
  line="${line%$'\r'}"
  echo "installer kernel ${line#*] }"
  check_boot_entry "the booted kernel command line" "$line" || return 1
  boot_checked=1
}

while (( $(date +%s) < DEADLINE )); do
  # The entry the installer actually booted: checked as soon as the kernel
  # has logged it, and first, so a wrong one is named even when it is what
  # made QEMU exit.
  [[ -n "$boot_checked" ]] || check_booted_entry || exit 1
  if ! kill -0 "$QEMU_PID" 2>/dev/null; then
    echo "qemu exited before SSH came up — install likely failed" >&2
    if [[ -s "$SERIAL_LOG" ]]; then
      echo "--- last 80 lines of $SERIAL_LOG ---" >&2
      tail -n 80 "$SERIAL_LOG" >&2 || true
    else
      echo "NO SERIAL OUTPUT — qemu never started. Check $QEMU_LOG:" >&2
      cat "$QEMU_LOG" >&2 || true
      echo "(a backgrounded qemu is SIGHUP'd when its spawning shell exits)" >&2
    fi
    exit 1
  fi
  if [[ -f "$SERIAL_LOG" ]]; then
    last_mtime=$(stat -c %Y "$SERIAL_LOG")
    if (( $(date +%s) - last_mtime > STAGNATION_BUDGET )); then
      echo "serial.log silent for >${STAGNATION_BUDGET}s — anaconda hung" >&2
      echo "--- last 80 lines of $SERIAL_LOG ---" >&2
      tail -n 80 "$SERIAL_LOG" >&2 || true
      exit 1
    fi
  fi
  if ssh "${SSH_OPTS[@]}" "$ADMIN_USER"@127.0.0.1 true 2>"$SSH_ERR"; then
    break
  fi
  sleep 20
done

if ! ssh "${SSH_OPTS[@]}" "$ADMIN_USER"@127.0.0.1 true 2>"$SSH_ERR"; then
  echo "SSH never came up within ${DEADLINE_SECONDS:-5400}s as $ADMIN_USER" >&2
  echo "(if the fixture's admin is not '$ADMIN_USER', set ADMIN_USER)" >&2
  # A refused or timed-out connect means sshd never started; an auth error
  # means the guest is up and the problem is the key, user or KEY_TYPE.
  echo "--- last ssh error ---" >&2
  cat "$SSH_ERR" >&2 || true
  exit 1
fi

[[ -n "$boot_checked" ]] || check_booted_entry || exit 1
if [[ -z "$boot_checked" ]]; then
  echo "no installer kernel command line in $SERIAL_LOG" >&2
  exit 1
fi

# ---- step 8: smoke check --------------------------------------------------
# Pre-flight the sudo password before the real call. These hosts run faillock
# with deny=3, and a wrong ADMIN_SUDO_PASSWORD otherwise burns all three tries
# and locks the admin out for unlock_time (900s), surfacing only as a bare
# "Sorry, try again" with no hint the account is now locked.
# Measured 2026-08-15: one failed pre-flight costs 2 of the 3 tallies (sudo
# retries internally and hits EOF on the exhausted stdin), so this fails
# *before* lockout but does not leave room for a second attempt.
#
# No faillock reset instructions here on purpose: `trap cleanup EXIT` SIGKILLs
# QEMU on the way out and step 5 recreates disk.qcow2 from scratch, so the
# lockout dies with the guest. Correct the password and re-run.
if [[ -n "$ADMIN_SUDO_PASSWORD" ]]; then
  preflight_err=""
  preflight_rc=0
  # Captured with `|| rc=$?` rather than `if ! ...`, because inside an
  # `if ! cmd` body $? is the *inverted* status (always 0) and the ssh-255
  # branch below would never be reachable.
  preflight_err="$(printf '%s\n' "$ADMIN_SUDO_PASSWORD" \
    | ssh "${SSH_OPTS[@]}" "$ADMIN_USER"@127.0.0.1 "sudo -S -p '' true" 2>&1 >/dev/null)" \
    || preflight_rc=$?
  if (( preflight_rc != 0 )); then
    # ssh reserves 255 for its own failures (connection dropped, host key
    # changed, sshd restarting during first-boot settling). Calling that a bad
    # password sends the operator to debug a password that was fine.
    if (( preflight_rc == 255 )); then
      echo "ssh transport failure during sudo pre-flight (rc=255), not an auth failure:" >&2
      echo "${preflight_err:-<no stderr>}" >&2
    else
      echo "ADMIN_SUDO_PASSWORD appears invalid for $ADMIN_USER (rc=$preflight_rc)." >&2
      echo "${preflight_err:-<no stderr>}" >&2
      echo "Not retrying — faillock deny=3 leaves no room for a second attempt." >&2
      echo "The guest is discarded on exit, so just fix the password and re-run." >&2
    fi
    exit 1
  fi
fi

scp "${COMMON_SSH_OPTS[@]}" -P "$SSH_HOST_PORT" \
    "$HERE/smoke-check.sh" "$ADMIN_USER"@127.0.0.1:/tmp/smoke-check.sh

SMOKE_ENV="DATA_DISK_MARKER='$DATA_DISK_MARKER' EXPECTED_CRYPTO_POLICY='$EXPECTED_CRYPTO_POLICY'"
SMOKE_ENV+=" EXPECTED_CONTAINER_USERS='$EXPECTED_CONTAINER_USERS' EXPECTED_FIRMWARE='$FIRMWARE'"
if [[ -n "$ADMIN_SUDO_PASSWORD" ]]; then
  # -S reads the password from stdin, -p '' drops the prompt. Fed over ssh
  # stdin so it never appears in the guest's process list.
  printf '%s\n' "$ADMIN_SUDO_PASSWORD" \
    | ssh "${SSH_OPTS[@]}" "$ADMIN_USER"@127.0.0.1 \
        "sudo -S -p '' $SMOKE_ENV bash /tmp/smoke-check.sh"
else
  ssh "${SSH_OPTS[@]}" "$ADMIN_USER"@127.0.0.1 \
    "sudo $SMOKE_ENV bash /tmp/smoke-check.sh"
fi

echo
echo "install-regression PASS (MEDIA=$MEDIA FIRMWARE=$FIRMWARE) — install completed end-to-end + smoke check green"
