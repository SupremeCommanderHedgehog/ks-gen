# `unifi` host kickstart rebuild — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `build/unifi/unifi.yaml` and regenerated artifacts with the new dedicated-hardware config defined in `docs/superpowers/specs/2026-06-17-unifi-rebuild-design.md`, producing a bootable installer ISO.

**Architecture:** Single consumer-config artifact (YAML) that feeds `ks-gen gen` (renders kickstart bundle) and `ks-gen iso` (repackages the AlmaLinux DVD). All output lives in the gitignored `build/unifi/` directory — there are no commits, no tests, no production code touched. The "test" for correctness is that `ks-gen gen` accepts the YAML and the generated `ks.cfg` contains the exact strings the spec's Validation section calls out.

**Tech Stack:** YAML config consumed by `ks-gen` 0.13.0 (Python/pydantic schema). Build runs in WSL Ubuntu (xorriso dependency). All paths below assume the repo at `/mnt/c/Users/yizshachuck/source/alma-linux-security` from inside WSL.

**Pre-flight check before starting:**

- `~/.venvs/ks-gen/bin/python -c "import ks_gen; print(ks_gen.__version__)"` must return `0.13.0` or higher. If it returns `0.12.x`, run `cd /mnt/c/Users/yizshachuck/source/alma-linux-security && ~/.venvs/ks-gen/bin/pip install -e .` before continuing.
- `AlmaLinux-9-latest-x86_64-dvd.iso` must exist at the repo root (used in Task 3).

---

### Task 1: Replace `build/unifi/unifi.yaml` with the new config

**Files:**
- Modify (replace): `build/unifi/unifi.yaml`

The existing file is the minimal 2026-06-14 config; we overwrite it with the new spec. The directory itself already exists (UNIFI_INSTALL.md, the old unifi.iso, etc. stay where they are).

- [ ] **Step 1: Write the new YAML**

Overwrite `build/unifi/unifi.yaml` with exactly this content:

```yaml
# UniFi OS Server host (see build/unifi/UNIFI_INSTALL.md for post-install recipe).
#
# Dedicated hardware:
#   - System disk: 256 GB Samsung SSD 850 EVO (~232 GiB usable)
#   - RAM:         8 GB
#   - NIC:         eno1
#
# Custom disk.layout enlarges /var to 50 G for /var/lib/uosserver
# (UNIFI_INSTALL.md flags /var as the bottleneck). UniFi drops its own
# storage.conf pointing container storage at ~/.local/share/containers,
# so /home (140 G) carries the real persistent container data.
#
# Container_host preset (containers.enabled) is deliberately NOT set:
# UniFi overrides /etc/containers/storage.conf at install time, so the
# /srv/containers/$USER/storage pin from container_host is useless here.

system:
  hostname: unifi
  timezone: America/New_York

network:
  interfaces:
    - device: eno1
      bootproto: dhcp
      onboot: true

user:
  admin:
    name: yizshachuck-admin
    gecos: "yizshachuck-admin"
    # Console login is required for break-glass, so we set a password
    # and keep sudo=nopasswd_no. Generate the hash locally with:
    #   openssl passwd -6
    # and replace the placeholder below BEFORE running `ks-gen gen`.
    password: "REPLACE_WITH_OPENSSL_PASSWD_-6_OUTPUT"
    sudo: nopasswd_no
    authorized_keys:
      - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIE4lYlqPDyt+c2YsS54ML0gS0eADwa/AswXmszzTUbdv pat@krypte.me"

disk:
  # Pin to the SSD by stable id so kernel name reordering can't redirect
  # the install. Single-disk box, but the by-id convention is the standard
  # since v0.13.
  target: disk/by-id/ata-Samsung_SSD_850_EVO_250GB_S2R5NX0HB19888W
  wipe: true
  # Custom layout: STIG mountpoints plus /var bumped to 50 G (UniFi
  # binaries + image staging) and /home generous (UniFi's storage.conf
  # override puts container storage in /home, not /var).
  # Sizing on ~232 GiB usable:
  #   EFI 1G + /boot 1G + system LVs (15+3+50+5+3+2 = 78G)
  #   + swap ~8G (recommended for 8 GB RAM)
  #   + /home 140G + ~4G VG slack => ~232G.
  layout:
    lvs:
      - {name: lv_root,          mount: /,              size: 15G}
      - {name: lv_tmp,           mount: /tmp,           size: 3G}
      - {name: lv_var,           mount: /var,           size: 50G}
      - {name: lv_var_log,       mount: /var/log,       size: 5G}
      - {name: lv_var_log_audit, mount: /var/log/audit, size: 3G}
      - {name: lv_var_tmp,       mount: /var/tmp,       size: 2G}
      - {name: lv_home,          mount: /home,          size: 140G}
      - {name: lv_swap,          fstype: swap,          size: recommended}

packages:
  preset: lean
```

- [ ] **Step 2: Confirm the file landed correctly**

Run (from WSL or PowerShell):

```bash
head -3 build/unifi/unifi.yaml
```

Expected first line: `# UniFi OS Server host (see build/unifi/UNIFI_INSTALL.md for post-install recipe).`

(No commit — `build/` is gitignored.)

---

### Task 2: Regenerate the kickstart bundle and verify it matches spec validation

**Files:**
- Replace (regenerated): `build/unifi/ks.cfg`, `build/unifi/tailoring.xml`, `build/unifi/host.yaml`, `build/unifi/exceptions.md`

The user MUST replace the password placeholder before this task runs. If the placeholder is still in place, anaconda will silently create an unusable console login.

- [ ] **Step 1: Verify the password placeholder has been replaced**

Run from WSL:

```bash
cd /mnt/c/Users/yizshachuck/source/alma-linux-security
if grep -q "REPLACE_WITH_OPENSSL_PASSWD_-6_OUTPUT" build/unifi/unifi.yaml; then
  echo "STOP: password placeholder still present in build/unifi/unifi.yaml — generate a hash with 'openssl passwd -6' and paste it in before continuing"
  exit 1
fi
```

Expected: no output (placeholder is gone).

- [ ] **Step 2: Run `ks-gen gen`**

Run from WSL:

```bash
cd /mnt/c/Users/yizshachuck/source/alma-linux-security
~/.venvs/ks-gen/bin/ks-gen gen -c build/unifi/unifi.yaml -o build/unifi/
```

Expected output ends with: `Wrote bundle to build/unifi`

If pydantic emits validation errors instead, the YAML diverges from what the schema expects — fix the YAML and re-run.

- [ ] **Step 3: Verify the generated `ks.cfg` matches the spec's validation strings**

Run from WSL:

```bash
cd /mnt/c/Users/yizshachuck/source/alma-linux-security
grep -nE "^(ignoredisk|bootloader|clearpart) " build/unifi/ks.cfg
grep -n "logvol /var "  build/unifi/ks.cfg
grep -n "logvol /home " build/unifi/ks.cfg
grep -n "^network "     build/unifi/ks.cfg
grep -n "^user "        build/unifi/ks.cfg
```

Expected exact lines (line numbers may vary):

```
ignoredisk --only-use=disk/by-id/ata-Samsung_SSD_850_EVO_250GB_S2R5NX0HB19888W
bootloader --location=mbr --boot-drive=disk/by-id/ata-Samsung_SSD_850_EVO_250GB_S2R5NX0HB19888W --append="audit=1 audit_backlog_limit=8192"
clearpart --all --initlabel --drives=disk/by-id/ata-Samsung_SSD_850_EVO_250GB_S2R5NX0HB19888W
logvol /var --vgname=vg_root --name=lv_var --fstype=xfs --size=51200 --fsoptions="nodev"
logvol /home --vgname=vg_root --name=lv_home --fstype=xfs --size=143360 --fsoptions="nodev,nosuid"
network --device=eno1 --bootproto=dhcp --hostname=unifi --onboot=yes
user --name=yizshachuck-admin --password=<your hash> --iscrypted --groups=wheel --gecos="yizshachuck-admin" --shell=/bin/bash
```

Any mismatch (wrong size, wrong device, missing by-id, missing flags) → the YAML doesn't match the spec; fix the YAML and re-run Task 2 Step 2.

(No commit — `build/` is gitignored.)

---

### Task 3: Rebuild the installer ISO

**Files:**
- Replace (regenerated): `build/unifi/unifi.iso`

The repackaged ISO is what gets written to a USB or attached to a VM.

- [ ] **Step 1: Run `ks-gen iso`**

Run from WSL:

```bash
cd /mnt/c/Users/yizshachuck/source/alma-linux-security
~/.venvs/ks-gen/bin/ks-gen iso \
  --src AlmaLinux-9-latest-x86_64-dvd.iso \
  --ks build/unifi/ks.cfg \
  --tailoring build/unifi/tailoring.xml \
  --out build/unifi/unifi.iso
```

Expected: xorriso runs for ~30-60 seconds, exit 0, with a final line confirming the ISO was written.

- [ ] **Step 2: Sanity-check the ISO size**

Run from WSL:

```bash
ls -lh build/unifi/unifi.iso
```

Expected: file size within ~50 MB of `AlmaLinux-9-latest-x86_64-dvd.iso` (kickstart + tailoring add only a few KB; nothing should be missing). A wildly small ISO (e.g. < 1 GB) means xorriso pulled in the wrong source.

(No commit — `build/` is gitignored.)

---

## Self-review notes (already reconciled)

- **Spec coverage:** every field in the spec's "Config decisions" section is set in the YAML in Task 1; every string in the spec's "Validation" section is checked in Task 2 Step 3. The "Build pipeline" section of the spec maps 1:1 onto Tasks 2 and 3.
- **No placeholders:** the only placeholder string in this plan is the YAML `password:` field, which is intentional (the user pastes the openssl hash locally). Task 2 Step 1 explicitly guards against it leaking through.
- **Type consistency:** all YAML field names match `src/ks_gen/config.py:HostConfig`; LV names + sizes match the spec's "Disk layout" block exactly.
- **Out of scope (per spec):** static IP migration, an `assets/install-unifi-os.sh` wrapper, mgmt1's future role, and a static inform DNS name are explicitly deferred. The post-install UniFi installer recipe lives in `build/unifi/UNIFI_INSTALL.md` and is not duplicated here.
