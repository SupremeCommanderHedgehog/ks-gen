#!/usr/bin/env bash
# On-demand end-to-end install regression harness (closed issue #57).
#
# Runs inside WSL Ubuntu (or any Linux with QEMU + OVMF). Drives the full
# pipeline:
#   1. ks-gen gen + ks-gen iso (twice — exercises #52 idempotency)
#   2. boot the ISO in QEMU/OVMF (KVM if available, else TCG)
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

# Ubuntu's ovmf package. As of 26.04 the legacy plain-name files
# (OVMF_CODE.fd) are gone; only the 4M variants ship. SecureBoot off
# variant — kickstart has no secure-boot signing story.
OVMF_CODE="${OVMF_CODE:-/usr/share/OVMF/OVMF_CODE_4M.fd}"
OVMF_VARS_TEMPLATE="${OVMF_VARS_TEMPLATE:-/usr/share/OVMF/OVMF_VARS_4M.fd}"

INSTALLER_ISO="$BUILD/installer.iso"
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
SSH_HOST_PORT=2222

# ---- preflight ------------------------------------------------------------
for bin in qemu-system-x86_64 qemu-img xorriso ssh-keygen ssh "$KS_GEN" "$KS_GEN_PY"; do
  command -v "$bin" >/dev/null 2>&1 || { echo "missing: $bin" >&2; exit 1; }
done
[[ -r "$OVMF_CODE"          ]] || { echo "missing: $OVMF_CODE (apt install ovmf)"      >&2; exit 1; }
[[ -r "$OVMF_VARS_TEMPLATE" ]] || { echo "missing: $OVMF_VARS_TEMPLATE (apt install ovmf)" >&2; exit 1; }
[[ -r "$SRC_ISO"            ]] || { echo "missing: $SRC_ISO"                              >&2; exit 1; }

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

# The crypto policy the kickstart intends to leave the host in, taken from the
# rule's own header comment ("... policy: STIG (FIPS:STIG)"). The ARF cannot
# show whether %post achieved it — oscap runs BEFORE the rule %post — so the
# smoke check asserts the live state against this instead (#66).
EXPECTED_CRYPTO_POLICY="$(sed -n 's/^# Apply system-wide crypto policy: .*(\(.*\))$/\1/p' \
  "$BUNDLE_DIR/ks.cfg" | head -1)"
echo "expected crypto policy: ${EXPECTED_CRYPTO_POLICY:-<none found>}"

# ---- step 4: ks-gen iso (twice; locks in PR #55 / issue #52) --------------
# Uses build-debug-iso.py instead of the CLI so we can inject the debug
# console args into the menu entries — anaconda's text-mode log lands on
# the serial port that QEMU captures.
# Set SKIP_ISO_BUILD=1 to skip rebuilding when iterating on QEMU/kickstart
# changes that don't affect the ISO contents (saves ~3 min/run).
if [[ -z "${SKIP_ISO_BUILD:-}" ]] || [[ ! -f "$INSTALLER_ISO" ]]; then
  "$KS_GEN_PY" "$HERE/build-debug-iso.py" "$SRC_ISO" "$BUNDLE_DIR" "$INSTALLER_ISO"
  "$KS_GEN_PY" "$HERE/build-debug-iso.py" "$SRC_ISO" "$BUNDLE_DIR" "$INSTALLER_ISO"
else
  echo "[SKIP_ISO_BUILD] reusing $INSTALLER_ISO"
fi

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
cp "$OVMF_VARS_TEMPLATE" "$NVRAM"

# ---- step 6: boot QEMU ----------------------------------------------------
# Use KVM where /dev/kvm is readable; fall back to TCG (~3x slower).
ACCEL=()
[[ -r /dev/kvm ]] && ACCEL=(-enable-kvm -cpu host) || ACCEL=(-accel tcg -cpu max)

# Memory + cores: 4G/2 is enough for anaconda + oscap.
# Networking: SLIRP user net forwards host:2222 → guest:22. DHCP is built in.
# Boot: leave EFI to decide. anaconda's `reboot --eject` will eject the CD on
#       success; OVMF's BootOrder gets written by anaconda's efibootmgr to
#       prefer the installed HD, so the second boot picks up the new system.
qemu-system-x86_64 \
  "${ACCEL[@]}" \
  -smp 2 -m 4096 \
  -machine q35,smm=on \
  -drive if=pflash,format=raw,readonly=on,file="$OVMF_CODE" \
  -drive if=pflash,format=raw,file="$NVRAM" \
  -drive file="$DISK",if=virtio,format=qcow2 \
  -drive file="$DATA_DISK",if=virtio,format=raw \
  -cdrom "$INSTALLER_ISO" \
  -netdev user,id=n0,hostfwd=tcp:127.0.0.1:$SSH_HOST_PORT-:22 \
  -device virtio-net-pci,netdev=n0 \
  -nographic \
  -serial file:"$SERIAL_LOG" \
  -monitor unix:/tmp/ks-gen-install-regression-qmp.sock,server,nowait \
  > "$QEMU_LOG" 2>&1 &
QEMU_PID=$!
echo "qemu pid=$QEMU_PID  serial=$SERIAL_LOG"

cleanup() {
  if kill -0 "$QEMU_PID" 2>/dev/null; then
    kill "$QEMU_PID" 2>/dev/null || true
    sleep 1
    kill -9 "$QEMU_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# ---- step 7: wait for SSH on host:2222 -----------------------------------
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
SSH_OPTS=(-i "$KEY"
          -o StrictHostKeyChecking=no
          -o UserKnownHostsFile=/dev/null
          -o ConnectTimeout=5
          -o LogLevel=ERROR
          -p "$SSH_HOST_PORT")

while (( $(date +%s) < DEADLINE )); do
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
  if ssh "${SSH_OPTS[@]}" "$ADMIN_USER"@127.0.0.1 true 2>/dev/null; then
    break
  fi
  sleep 20
done

if ! ssh "${SSH_OPTS[@]}" "$ADMIN_USER"@127.0.0.1 true 2>/dev/null; then
  echo "SSH never came up within ${DEADLINE_SECONDS:-5400}s as $ADMIN_USER" >&2
  echo "(if the fixture's admin is not '$ADMIN_USER', set ADMIN_USER)" >&2
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

scp -P "$SSH_HOST_PORT" \
    -i "$KEY" \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    "$HERE/smoke-check.sh" "$ADMIN_USER"@127.0.0.1:/tmp/smoke-check.sh

SMOKE_ENV="DATA_DISK_MARKER='$DATA_DISK_MARKER' EXPECTED_CRYPTO_POLICY='$EXPECTED_CRYPTO_POLICY'"
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
echo "install-regression PASS — install completed end-to-end + smoke check green"
