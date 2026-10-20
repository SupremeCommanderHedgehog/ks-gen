#!/usr/bin/env bash
# Runs on the installed VM via SSH. Asserts the post-install state matches
# what the kickstart promised.
set -euo pipefail

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "ok:   $*"; }

# Init files in $1 looser than the STIG's 0740, as "path=mode " pairs: regular
# files directly in it matching var_user_initialization_files_regex (#49).
loose_init_files() {
  LC_ALL=C find "$1/" -maxdepth 1 -type f -regextype posix-extended \
    -regex '.*/\.[[:alnum:]_ -]+' -perm /0037 -printf '%p=%m ' 2>/dev/null || true
}

# --- Core services kickstart says it enables (#57 acceptance: "install
#     completed and reachable"; sshd is implicit since we got here).
for svc in sshd chronyd firewalld auditd rsyslog; do
  systemctl is-active --quiet "$svc" || fail "$svc not active"
  ok "$svc active"
done

# --- #50: chrony.conf carries the STIG chronyd directives, and with
#     `cmdport 0` root's chronyc must still reach chronyd over the local
#     Unix socket. chrony-wait must be the override without `-h`, or it
#     could never connect.
grep -qx 'port 0' /etc/chrony.conf || fail "chrony.conf lacks 'port 0' (#50)"
grep -qx 'cmdport 0' /etc/chrony.conf || fail "chrony.conf lacks 'cmdport 0' (#50)"
grep -Eq '^server .* maxpoll 16' /etc/chrony.conf || fail "chrony.conf server lines lack maxpoll 16 (#50)"
# waitsync, not just `sources`: `sources` exits 0 with nothing reachable.
# Passing proves root's chronyc reaches chronyd over the local socket with
# cmdport 0 AND that a source actually synced (up to 30 x 5s).
chronyc waitsync 30 0 0 5 >/dev/null 2>&1 \
  || fail "chrony never synced, or root's chronyc cannot reach chronyd over the local socket (#50): $(chronyc -n sources 2>&1 | tail -n +3 | tr '\n' ';')"
ok "chrony.conf STIG directives present; chronyc answers over the local socket and synced"
# #125: with time.nts every source is `nts`, so the sync above was NTS-authenticated.
if grep -Eq '^server .* nts$' /etc/chrony.conf; then
  # Captured, not piped into grep -q: an early grep exit can SIGPIPE chronyc
  # and pipefail would report a failure that didn't happen.
  authdata=$(chronyc -n authdata 2>/dev/null || true)
  [[ "$authdata" == *" NTS "* ]] \
    || fail "chrony.conf asks for NTS but chronyc authdata shows no NTS source (#125)"
  ok "time is NTS-authenticated (#125)"
fi
if [[ -f /usr/lib/systemd/system/chrony-wait.service ]]; then
  grep -Eq '^ExecStart=/usr/bin/chronyc waitsync ' /etc/systemd/system/chrony-wait.service \
    || fail "chrony-wait.service override missing or still uses -h (#50)"
  ok "chrony-wait.service override uses the local socket"
fi

# --- #118: on AL8, oscap's sshd_use_strong_rng makes sshd read the blocking
#     /dev/random, and SSG never installs rngd on AlmaLinux, so the
#     rngd_entropy rule does. sshd being up is not proof: this VM may simply
#     have had entropy.
if [[ "$(rpm -E %rhel 2>/dev/null || echo 0)" == 8 ]]; then
  rpm -q rng-tools >/dev/null || fail "rng-tools not installed (#118: sshd can hang at boot)"
  systemctl is-active --quiet rngd || fail "rngd not active (#118: sshd can hang at boot)"
  ok "rngd active (#118)"
fi

# --- #53 regression: unattended_updates rule MUST cause dnf-automatic.timer
#     to be enabled even when host.yaml's packages.required omitted
#     dnf-automatic. Pre-#56, this timer doesn't exist and install dies
#     in %post.
systemctl is-active --quiet dnf-automatic.timer \
  || fail "dnf-automatic.timer not active (PR #56 regression — emit_packages didn't contribute dnf-automatic)"
ok "dnf-automatic.timer active"

# reboot-window timer from unattended_updates
systemctl is-enabled --quiet ks-gen-reboot-if-needed.timer \
  || fail "ks-gen-reboot-if-needed.timer not enabled"
ok "ks-gen-reboot-if-needed.timer enabled"

# monthly-full timer
systemctl is-enabled --quiet ks-gen-dnf-automatic-full.timer \
  || fail "ks-gen-dnf-automatic-full.timer not enabled"
ok "ks-gen-dnf-automatic-full.timer enabled"

# --- faillock applied (one of the highest-risk silent install failures)
[[ -f /etc/security/faillock.conf ]] || fail "faillock.conf missing"
grep -q '^deny *= *3' /etc/security/faillock.conf \
  || fail "faillock.conf: deny=3 not applied"
ok "faillock.conf has deny=3"

# --- oscap remediation actually ran
[[ -s /root/oscap-remediation-results.xml ]] \
  || fail "/root/oscap-remediation-results.xml missing or empty (oscap didn't run)"
ok "/root/oscap-remediation-results.xml present"

[[ -s /root/oscap-remediation-report.html ]] \
  || fail "/root/oscap-remediation-report.html missing or empty"
ok "/root/oscap-remediation-report.html present"

# --- #65: oscap must have evaluated ks-gen's TAILORED profile, not the base
#     STIG profile. Passing the base id loads the tailoring and ignores it,
#     with no error anywhere — every exception becomes decorative. Confirmed
#     on AL10 2026-08-12, which is why this assertion exists.
grep -aq 'TestResult[^>]*ks-gen_profile_tailored' /root/oscap-remediation-results.xml \
  || fail "ARF TestResult is not the ks-gen tailored profile — oscap ignored tailoring.xml (#65)"
ok "ARF confirms oscap evaluated xccdf_ks-gen_profile_tailored"

# A ks-gen-disabled rule must carry result=notselected. Note oscap emits a
# <rule-result> for EVERY benchmark rule including unselected ones, so the
# presence of the element proves nothing — only the <result> value does.
banner_result=$(grep -aA 5 'rule-result idref="xccdf_org.ssgproject.content_rule_banner_etc_issue"' \
  /root/oscap-remediation-results.xml | grep -ao '<result>[a-z]*</result>' | head -1)
[[ "$banner_result" == "<result>notselected</result>" ]] \
  || fail "banner_etc_issue result is ${banner_result:-missing}, expected notselected — tailoring not honoured (#65)"
ok "ks-gen-disabled rule banner_etc_issue is notselected in the ARF"

# ...and the converse: configure_crypto_policy is deliberately NOT disabled
# under MODERN/FUTURE, because crypto_policy retunes its Value instead. It
# must therefore be evaluated and pass (#61).
# --- the LIVE crypto policy (#66) -----------------------------------------
# This is the assertion that can actually catch #66. The ARF cannot: it is
# written by the oscap %post, which runs BEFORE ks-gen's rule %post, so it
# records what oscap remediated to and looks identical whether %post then
# applies FIPS:STIG or downgrades the host to FIPS.
# The RHS is deliberately unquoted: under STIG the kickstart carries the glob
# `FIPS*`, because which FIPS target applies belongs to the SSG content the host
# ended up with, not to ks-gen (#90). MODERN/FUTURE still carry exact literals,
# which match themselves.
if [[ -n "${EXPECTED_CRYPTO_POLICY:-}" ]]; then
  live_policy=$(update-crypto-policies --show 2>/dev/null || cat /etc/crypto-policies/config)
  # shellcheck disable=SC2053
  [[ "$live_policy" == $EXPECTED_CRYPTO_POLICY ]] \
    || fail "live crypto policy is '$live_policy', kickstart intended '$EXPECTED_CRYPTO_POLICY' (#66)"
  ok "live crypto policy is $live_policy (as the kickstart intended)"
fi

# configure_crypto_policy, re-scanned live rather than read from the ARF.
#
# The ARF records what oscap saw mid-install, before ks-gen's rule %post ran,
# and on AL10 that is transiently wrong: the rule has a third criterion that
# /etc/crypto-policies/state/current be *newer* than .../config, so when the
# remediation sets the policy and re-verifies inside the same second, oscap
# records `error` ("Failed to verify applied fix"). The installed host is
# correct — a live scan returns `pass` — so asserting on the ARF made AL10
# STIG a permanent false alarm (observed 2026-08-14).
#
# A live re-scan is also the stronger assertion: it is what `ks-gen verify`
# and an auditor would run, and the expectation is the same under every
# policy. MODERN/FUTURE pass via the set_value retune (#61); STIG passes
# because %post applied the per-distro FIPS target (#66).
CRYPTO_RULE=xccdf_org.ssgproject.content_rule_configure_crypto_policy
ds=$(find /usr/share/xml/scap/ssg/content -name 'ssg-*-ds.xml' 2>/dev/null | head -1)
[[ -n "$ds" ]] || fail "no SSG datastream installed — cannot re-scan $CRYPTO_RULE"
[[ -r /root/tailoring.xml ]] || fail "/root/tailoring.xml missing — the bundle did not land"
# `|| true`: oscap exits 2 when any rule fails, which pipefail would turn
# into a script abort before this assertion could report anything.
crypto_live=$(oscap xccdf eval --profile xccdf_ks-gen_profile_tailored \
  --tailoring-file /root/tailoring.xml --rule "$CRYPTO_RULE" "$ds" 2>/dev/null \
  | awk '/^Result/{print $2; exit}' || true)
[[ "$crypto_live" == "pass" ]] \
  || fail "live scan of configure_crypto_policy is '${crypto_live:-no result}', expected pass for policy ${EXPECTED_CRYPTO_POLICY:-unknown} (#61/#66)"
ok "configure_crypto_policy passes a live re-scan under policy ${EXPECTED_CRYPTO_POLICY:-unknown}"

# --- #67: a host that opted out of FIPS must not be remediated INTO it.
# AL8's enable_dracut_fips_module fix runs `fips-mode-setup --enable`, which
# writes 40-fips.conf and puts fips=1 on the kernel command line. ks-gen's
# %post only corrects the crypto policy, never the kernel args, so nothing
# else here would notice. The ARF check is the converse: the FIPS-only rules
# must read notselected, proving the tailoring reached them.
case "${EXPECTED_CRYPTO_POLICY:-}" in
  "") ;;
  FIPS*)
    # --- #84: a STIG host must really be in FIPS mode, not merely running the
    # FIPS crypto policy. Everything here needs the post-install reboot, so it
    # cannot be read from the ARF (written mid-install, pre-reboot).
    grep -qw 'fips=1' /proc/cmdline \
      || fail "kernel command line has no fips=1 on a ${EXPECTED_CRYPTO_POLICY} host (#84): $(cat /proc/cmdline)"
    ok "kernel booted with fips=1"

    # ks-gen always creates a separate /boot, so dracut needs boot= to find it.
    # -E not -w: `boot=UUID=[^ ]*` matches an EMPTY uuid, so -w would pass a
    # bare `boot=UUID=`. `[^ ]+` between word boundaries is the real assertion.
    grep -qE '(^| )boot=UUID=[^ ]+( |$)' /proc/cmdline \
      || fail "kernel command line has fips=1 but no boot=UUID= — separate /boot will not be found (#84)"
    ok "kernel command line carries boot=UUID="

    fips_enabled=$(cat /proc/sys/crypto/fips_enabled 2>/dev/null || echo 0)
    [[ "$fips_enabled" == "1" ]] \
      || fail "/proc/sys/crypto/fips_enabled is ${fips_enabled} on a ${EXPECTED_CRYPTO_POLICY} host (#84)"
    ok "/proc/sys/crypto/fips_enabled is 1"

    [[ -e /etc/dracut.conf.d/40-fips.conf ]] \
      || fail "/etc/dracut.conf.d/40-fips.conf missing — %post did not enable the dracut FIPS module (#84)"
    ok "/etc/dracut.conf.d/40-fips.conf present"

    # Live re-scan, not the ARF: the ARF is written pre-reboot, when
    # fips_enabled is still 0 and every one of these legitimately fails.
    # $ds / /root/tailoring.xml were discovered and checked above.
    #
    # notselected/empty must NOT read as ok here: a tailoring bug that
    # disables a FIPS rule on a STIG host yields exactly notselected, and a
    # broken oscap invocation (bad $ds, missing tailoring) yields empty for
    # every rule. So presence is checked directly against $ds — the rule's
    # own id string in the datastream content — rather than inferred from
    # an empty scan result, which can't tell "absent" from "broken".
    evaluated=0
    for rid in enable_fips_mode sysctl_crypto_fips_enabled fips_crypto_subpolicy \
               system_booted_in_fips_mode enable_dracut_fips_module; do
      full_rid="xccdf_org.ssgproject.content_rule_${rid}"
      if ! grep -q "\"${full_rid}\"" "$ds"; then
        ok "${rid}: absent from this datastream"
        continue
      fi
      # `|| true`: oscap exits 2 on a failing rule; pipefail would abort here.
      live=$(oscap xccdf eval --profile xccdf_ks-gen_profile_tailored \
        --tailoring-file /root/tailoring.xml \
        --rule "$full_rid" "$ds" 2>/dev/null \
        | awk '/^Result/{print $2; exit}' || true)
      [[ "$live" == "pass" ]] \
        || fail "${rid} is '${live:-no result}' on a ${EXPECTED_CRYPTO_POLICY} host — the kernel is not in FIPS mode (#84)"
      ok "${rid}: pass"
      evaluated=$((evaluated + 1))
    done
    [[ "$evaluated" -gt 0 ]] \
      || fail "no FIPS rule was evaluated on a ${EXPECTED_CRYPTO_POLICY} host — broken scan, not a clean host (#84)"
    ;;
  *)
    if grep -qw 'fips=1' /proc/cmdline; then
      fail "kernel booted with fips=1 on a ${EXPECTED_CRYPTO_POLICY} host — oscap remediated it into FIPS (#67)"
    fi
    ok "kernel command line carries no fips=1"

    fips_enabled=$(cat /proc/sys/crypto/fips_enabled 2>/dev/null || echo 0)
    [[ "$fips_enabled" == "0" ]] \
      || fail "/proc/sys/crypto/fips_enabled is ${fips_enabled} on a ${EXPECTED_CRYPTO_POLICY} host (#67)"
    ok "/proc/sys/crypto/fips_enabled is 0"

    [[ ! -e /etc/dracut.conf.d/40-fips.conf ]] \
      || fail "/etc/dracut.conf.d/40-fips.conf exists — enable_dracut_fips_module remediated a non-FIPS host (#67)"
    ok "no /etc/dracut.conf.d/40-fips.conf"

    # Absent is legitimate: each distro's stig profile selects a different
    # subset, and a rule its datastream doesn't ship has no rule-result.
    for rid in enable_dracut_fips_module sysctl_crypto_fips_enabled \
               fips_crypto_subpolicy system_booted_in_fips_mode; do
      # `|| true`: absent rules make the pipeline exit non-zero, and under
      # `set -euo pipefail` that assignment would kill the script.
      fips_result=$(grep -aA 5 "rule-result idref=\"xccdf_org.ssgproject.content_rule_${rid}\"" \
        /root/oscap-remediation-results.xml | grep -ao '<result>[a-z]*</result>' | head -1 || true)
      [[ -z "$fips_result" || "$fips_result" == "<result>notselected</result>" ]] \
        || fail "${rid} result is ${fips_result}, expected notselected on a ${EXPECTED_CRYPTO_POLICY} host (#67)"
      ok "${rid}: ${fips_result:-absent from this datastream}"
    done
    ;;
esac

# --- root + console login locked, per kickstart contract
# AlmaLinux 9 / shadow-utils prints "LK" in the status field, not " L ".
passwd -S root | awk '{print $2}' | grep -qE '^LK?$' \
  || fail "root password not locked (passwd -S: $(passwd -S root))"
ok "root password locked"

# --- aide installed (STIG baseline)
rpm -q aide >/dev/null || fail "aide not installed"
ok "aide installed"

# --- ks-post.log shows %post finished without unbound errors
tail -n 5 /root/ks-post.log | grep -q '+ ' \
  || fail "ks-post.log does not look like a clean trace"
ok "ks-post.log present and traced"

# --- #59 regression: disk.target=vda must confine install to vda.
#     vdb is a 1G raw data disk pre-filled with a magic marker at offset 0.
#     If ignoredisk/clearpart/bootloader/--ondisk are honoring disk.target,
#     anaconda left vdb alone and the marker is still readable.
if [[ -n "${DATA_DISK_MARKER:-}" ]]; then
  [[ -b /dev/vdb ]] || fail "/dev/vdb not present — second virtio disk missing"

  # vdb must have no partitions/children. If anaconda touched it,
  # lsblk would show vdb1, vdb2, etc.
  vdb_children=$(lsblk -no NAME /dev/vdb | tail -n +2 || true)
  [[ -z "$vdb_children" ]] \
    || fail "/dev/vdb has partitions after install: $vdb_children — disk.target did not confine clearpart"
  ok "/dev/vdb has no partitions (clearpart respected --drives=vda)"

  # Read the marker back from offset 0 and compare.
  marker_len=${#DATA_DISK_MARKER}
  actual=$(dd if=/dev/vdb bs=1 count="$marker_len" status=none 2>/dev/null)
  [[ "$actual" == "$DATA_DISK_MARKER" ]] \
    || fail "/dev/vdb marker corrupted (expected '$DATA_DISK_MARKER', got '$actual') — anaconda wrote to vdb despite disk.target=vda"
  ok "/dev/vdb marker intact (anaconda honored ignoredisk --only-use=vda)"

  # Bootloader must be on vda, not vdb. Check the EFI variable for the
  # installed boot entry's disk reference, or fall back to the BootCurrent
  # entry's device path.
  if command -v efibootmgr >/dev/null 2>&1; then
    boot_disk=$(efibootmgr -v 2>/dev/null | grep -i 'almalinux' | head -n1 || true)
    if [[ -n "$boot_disk" ]]; then
      # The device path of an EFI boot entry encodes the disk's GPT GUID
      # or PCI path. We don't parse it; we just confirm it doesn't
      # reference the vdb PCI slot. virtio-blk on QEMU is usually
      # Pci(0x4,0x0) for vda, Pci(0x5,0x0) for vdb on q35 machines.
      # Easier signal: efibootmgr reports the partition number; if vda
      # was the install disk, the GPT entry will live on vda.
      ok "EFI boot entry: $boot_disk"
    fi
  fi
fi

# --- #66 container-host preset, no-users mode: partition + script + storage.conf
#     The script is only INVOKED per containers.users[] entry; with users=[] the
#     fcontext equivalence rule isn't yet added (it runs on first script call).
findmnt -no FSTYPE /srv/containers 2>/dev/null | grep -q '^xfs$' \
  || fail "/srv/containers not mounted as XFS (containers.enabled was true)"
ok "/srv/containers mounted as XFS"

mnt_opts=$(findmnt -no OPTIONS /srv/containers 2>/dev/null || true)
[[ -n "$mnt_opts" ]] || fail "/srv/containers options unreadable"
[[ ",$mnt_opts," == *,nodev,* ]] || fail "/srv/containers missing nodev: $mnt_opts"
[[ ",$mnt_opts," == *,nosuid,* ]] || fail "/srv/containers missing nosuid: $mnt_opts"
[[ ",$mnt_opts," != *,noexec,* ]] || fail "/srv/containers has noexec — container layers cannot execute: $mnt_opts"
ok "/srv/containers options correct (nodev,nosuid; not noexec)"

[[ -f /root/create-rootless-user.sh ]] || fail "/root/create-rootless-user.sh missing"
script_mode=$(stat -c '%a %U:%G' /root/create-rootless-user.sh)
[[ "$script_mode" == "550 root:root" ]] \
  || fail "/root/create-rootless-user.sh wrong mode/owner: $script_mode (expected '550 root:root')"
ok "/root/create-rootless-user.sh exists (mode 0550, root:root)"

[[ -s /etc/containers/storage.conf ]] || fail "/etc/containers/storage.conf missing"
grep -q '^rootless_storage_path *= *"/srv/containers/\$USER/storage"' /etc/containers/storage.conf \
  || fail "/etc/containers/storage.conf missing rootless_storage_path under /srv/containers"
ok "/etc/containers/storage.conf pins rootless graphroot to /srv/containers"

# Podman stack from container_host.emit_packages.
# podman-plugins is EL8/EL9 only — not packaged for EL10, where podman 5.x
# uses netavark and container_host deliberately omits it (PR #62).
PODMAN_STACK=(podman crun slirp4netns fuse-overlayfs containers-common)
if [[ "$(rpm -E %rhel 2>/dev/null || echo 0)" -lt 10 ]]; then
  PODMAN_STACK+=(podman-plugins)
fi
rpm -q "${PODMAN_STACK[@]}" >/dev/null \
  || fail "podman stack not fully installed: ${PODMAN_STACK[*]}"
ok "podman stack installed (${PODMAN_STACK[*]})"

if [[ "$(rpm -E %rhel 2>/dev/null || echo 0)" -ge 10 ]]; then
  rpm -q podman-plugins >/dev/null 2>&1 \
    && fail "podman-plugins installed on EL10 — it is not packaged there"
  ok "podman-plugins correctly absent on EL10"
fi

# --- containers.users[]: EXPECTED_CONTAINER_USERS is what the kickstart
#     provisioned (run.sh reads it from ks.cfg). Empty: the script was never
#     invoked, so spot-check that no webapp user appeared.
if [[ -z "${EXPECTED_CONTAINER_USERS:-}" ]]; then
  getent passwd webapp >/dev/null && fail "webapp user exists but containers.users was []"
  ok "no webapp user (containers.users was empty)"
else
  for u in $EXPECTED_CONTAINER_USERS; do
    home=$(getent passwd "$u" | cut -d: -f6 || true)
    [[ -n "$home" && -d "$home" ]] || fail "container user $u missing or has no home dir"
    [[ "$(stat -c %U "/srv/containers/$u/storage" 2>/dev/null)" == "$u" ]] \
      || fail "/srv/containers/$u/storage missing or not owned by $u"
    [[ -f "/var/lib/systemd/linger/$u" ]] || fail "linger not enabled for $u"
    ok "container user $u provisioned (home, storage on /srv/containers, linger)"
    # #49: useradd's skel dotfiles land at 0644; the script must leave every
    # init file (STIG var_user_initialization_files_regex) at 0740 or stricter.
    loose=$(loose_init_files "$home")
    [[ -z "$loose" ]] || fail "$u has init files looser than 0740: $loose(#49)"
    [[ -f "$home/.bashrc" ]] || fail "$u has no .bashrc — skel was not copied, nothing was tested"
    ok "$u init files are 0740 or stricter ($(stat -c '%n=%a' "$home/.bashrc"))"
  done
fi

# --- #49: the STIG init-file rule, live. It checks every user's init files,
#     so this covers the admin user and root on every fixture, and any
#     container users above. AL8/AL9's stig selects the _root variant, AL10's
#     the plain one (same var_user_initialization_files_regex). Selection comes
#     from the ARF, where an unselected rule reads notselected: `--rule`
#     evaluates a rule whether or not the profile selects it, so a live scan
#     of the unselected variant would assert something the profile doesn't.
init_rules=()
for rid in file_permission_user_init_files_root file_permission_user_init_files; do
  full_rid="xccdf_org.ssgproject.content_rule_${rid}"
  sel=$(grep -aA 5 "rule-result idref=\"${full_rid}\"" /root/oscap-remediation-results.xml \
    | grep -ao '<result>[a-z]*</result>' | head -1 || true)
  if [[ -z "$sel" ]]; then
    ok "${rid}: absent from the ARF"; continue
  elif [[ "$sel" == "<result>notselected</result>" ]]; then
    ok "${rid}: not selected"; continue
  fi
  init_rules+=(--rule "$full_rid")
done
[[ ${#init_rules[@]} -gt 0 ]] \
  || fail "no init-file permission rule is selected — the stig profile always has one (#49)"
# `|| true`: oscap exits 2 when a rule fails. Output is "Rule <id>" then
# "Result <r>" per rule; pair them up.
init_live=$(oscap xccdf eval --profile xccdf_ks-gen_profile_tailored \
  --tailoring-file /root/tailoring.xml "${init_rules[@]}" "$ds" 2>/dev/null \
  | awk '/^Rule/{r=$2} /^Result/{sub(/^xccdf_org.ssgproject.content_rule_/, "", r); print r "=" $2}' \
  || true)
[[ $(grep -c . <<<"$init_live") -eq $(( ${#init_rules[@]} / 2 )) ]] \
  || fail "live init-file scan returned '${init_live:-nothing}' for ${#init_rules[@]}/2 rules — broken scan (#49)"
if grep -qv '=pass$' <<<"$init_live"; then
  offenders=$(getent passwd | awk -F: '$3 == 0 || $3 >= 1000 {print $6}' | sort -u \
    | while read -r d; do [[ -d "$d" ]] && loose_init_files "$d"; done || true)
  fail "live init-file scan: $(tr '\n' ' ' <<<"$init_live")— loose init files: ${offenders:-none found} (#49)"
fi
while read -r line; do ok "${line%=pass}: pass (live re-scan)"; done <<<"$init_live"

# Operator can still run the script post-install — verify by dry-firing it.
sudo /root/create-rootless-user.sh -h >/dev/null 2>&1 \
  || fail "/root/create-rootless-user.sh -h failed — script may be malformed"
ok "/root/create-rootless-user.sh -h runs cleanly"

echo
echo "ALL SMOKE CHECKS PASSED"
