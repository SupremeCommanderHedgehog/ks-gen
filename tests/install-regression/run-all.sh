#!/usr/bin/env bash
# Run the install-regression harness in both media modes, CD then USB (#26).
#
# CD alone is not enough: it boots the ISO as /dev/sr0, where anaconda
# auto-detects its install source, so it never exercises the USB-disk path
# operators hit with a `dd`/Rufus-DD stick. PR #73's two bugs (no
# inst.repo=hd:LABEL=..., no top-level `user` directive) passed CD and broke
# USB. A fix to the install pipeline is validated only when both pass.
#
# Both modes run even if the first fails — each is a 13-90 min install, so
# one invocation reports both results. Exit status is non-zero if either
# failed. The USB run reuses the CD run's installer.iso (SKIP_ISO_BUILD=1),
# so both test the identical image — but only if the CD run finished building
# it (run.sh's installer.iso.ok marker); otherwise it rebuilds rather than
# boot a stale or half-written ISO. FORCE_ISO_REBUILD=1 rebuilds for both
# modes and overrides any SKIP_ISO_BUILD.
#
# Per mode, $BUILD/run-all/ keeps that run's serial/qemu logs and the
# installed disk's `qemu-img info` (README trap 2: a ~196 KiB disk means
# nothing was installed, whatever the output says).
#
# Same traps as run.sh: run in the foreground and never pipe it (a pipeline's
# exit status is the last command's). Every run.sh variable passes through.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
BUILD="${BUILD:-$HOME/.cache/ks-gen-install-regression}"
export BUILD
LOGS="$BUILD/run-all"
ISO_OK="$BUILD/installer.iso.ok"
mkdir -p "$LOGS"

# The USB run's own preflight would only fire after a full CD install.
qemu_devices="$(qemu-system-x86_64 -device help 2>/dev/null)" || qemu_devices=""
for dev in qemu-xhci usb-storage; do
  [[ "$qemu_devices" == *"\"$dev\""* ]] || {
    echo "missing: QEMU device $dev (needed for the USB run)" >&2; exit 1; }
done

declare -A result
for media in cd usb; do
  echo
  echo "=================== install-regression: MEDIA=$media ==================="
  rm -f "$LOGS/$media"-*
  if [[ -n "${FORCE_ISO_REBUILD:-}" ]]; then
    skip=""
  elif [[ "$media" == usb && "$ISO_OK" -nt "$started_cd" ]]; then
    skip=1    # the CD run just built it
  elif [[ "$media" == usb && -n "${SKIP_ISO_BUILD:-}" && -f "$ISO_OK" ]]; then
    skip=1    # caller asked to reuse, and the existing ISO finished building
  elif [[ "$media" == usb ]]; then
    skip=""
  else
    skip="${SKIP_ISO_BUILD:-}"
  fi
  # Stamp before the run, so only files it writes compare newer below.
  stamp="$LOGS/.started-$media"
  touch "$stamp"
  [[ "$media" == cd ]] && started_cd="$stamp"
  MEDIA="$media" SKIP_ISO_BUILD="$skip" bash "$HERE/run.sh"
  rc=$?
  result[$media]=$rc
  # run.sh deletes serial.log/qemu.log only once it gets past preflight, so a
  # run that died early leaves the previous run's logs behind. Keep only what
  # this run wrote.
  for f in serial.log qemu.log; do
    [[ "$BUILD/$f" -nt "$stamp" ]] && cp "$BUILD/$f" "$LOGS/$media-$f"
  done
  if [[ "$BUILD/disk.qcow2" -nt "$stamp" ]]; then
    qemu-img info "$BUILD/disk.qcow2" > "$LOGS/$media-disk.txt" 2>&1
  fi
done

echo
echo "=================== install-regression summary ==================="
failed=0
for media in cd usb; do
  used="$(sed -n 's/^disk size: //p' "$LOGS/$media-disk.txt" 2>/dev/null)"
  if (( result[$media] == 0 )); then
    echo "  $media: PASS  (installed disk size: ${used:-unknown})"
  else
    echo "  $media: FAIL  (run.sh exit ${result[$media]}; logs: $LOGS/$media-*)"
    failed=1
  fi
done
exit "$failed"
