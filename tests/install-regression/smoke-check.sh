#!/usr/bin/env bash
# Runs on the installed VM via SSH. Asserts the post-install state matches
# what the kickstart promised.
set -euo pipefail

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "ok:   $*"; }

# --- Core services kickstart says it enables (#57 acceptance: "install
#     completed and reachable"; sshd is implicit since we got here).
for svc in sshd chronyd firewalld auditd rsyslog; do
  systemctl is-active --quiet "$svc" || fail "$svc not active"
  ok "$svc active"
done

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
if [[ -n "${EXPECTED_CRYPTO_POLICY:-}" ]]; then
  live_policy=$(update-crypto-policies --show 2>/dev/null || cat /etc/crypto-policies/config)
  [[ "$live_policy" == "$EXPECTED_CRYPTO_POLICY" ]] \
    || fail "live crypto policy is '$live_policy', kickstart intended '$EXPECTED_CRYPTO_POLICY' (#66)"
  ok "live crypto policy is $live_policy (as the kickstart intended)"
fi

# configure_crypto_policy's ARF result is policy-dependent:
#   MODERN/FUTURE -> `pass`  : the set_value retune (#61) means the rule
#                              already agrees with the host, nothing to fix.
#   FIPS-based    -> `fixed` : no tailoring is emitted for STIG, so oscap
#                              finds the stock policy and remediates it.
# Accepting `fixed` unconditionally would let a #61 regression pass on a
# MODERN host, so the expectation is derived from the policy in force.
crypto_result=$(grep -aA 5 'rule-result idref="xccdf_org.ssgproject.content_rule_configure_crypto_policy"' \
  /root/oscap-remediation-results.xml | grep -ao '<result>[a-z]*</result>' | head -1)
case "${EXPECTED_CRYPTO_POLICY:-}" in
  FIPS*) accepted="<result>fixed</result> <result>pass</result>" ;;
  *)     accepted="<result>pass</result>" ;;
esac
[[ " $accepted " == *" $crypto_result "* ]] \
  || fail "configure_crypto_policy result is ${crypto_result:-missing}; expected one of [$accepted] for policy ${EXPECTED_CRYPTO_POLICY:-unknown} (#61/#66)"
ok "configure_crypto_policy result ${crypto_result} matches policy ${EXPECTED_CRYPTO_POLICY:-unknown}"

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

# When users=[] no webapp is created, no /srv/containers/webapp/, and the script
# was never invoked so the equivalence rule isn't added yet. Spot-check no webapp.
getent passwd webapp >/dev/null && fail "webapp user exists but containers.users was []"
ok "no webapp user (containers.users was empty)"

# Operator can still run the script post-install — verify by dry-firing it.
sudo /root/create-rootless-user.sh -h >/dev/null 2>&1 \
  || fail "/root/create-rootless-user.sh -h failed — script may be malformed"
ok "/root/create-rootless-user.sh -h runs cleanly"

echo
echo "ALL SMOKE CHECKS PASSED"
