# Design: `unifi` host kickstart rebuild

**Date:** 2026-06-17
**Type:** Usage artifact (not a ks-gen feature) — produces a single
consumer YAML config that drives `ks-gen gen` / `ks-gen iso`.

## Goal

Rebuild the `build/unifi/unifi.yaml` consumer config from scratch for
**new dedicated hardware** that will run UniFi OS Server as a
single-purpose controller. Replaces the previous `unifi.yaml` (spec
`2026-06-14-unifi-host-config-design.md`), which targeted unspecified
hardware and used minimal defaults throughout.

## Background

`mgmt1` (192.168.160.2) was the proof-of-concept UniFi-on-STIG
deployment (`reference_unifi_install_on_stig_host.md`,
`build/unifi/UNIFI_INSTALL.md`). That deployment surfaced two host-level
issues worth baking into a real, dedicated controller config:

1. **`/var` is the bottleneck.** UniFi installs its binary tree to
   `/var/lib/uosserver` and its container runtime data path is
   *overridden* by UniFi's own per-user `storage.conf` to point at
   `~/.local/share/containers`. So /var carries the install + image
   layer staging; /home carries the persistent container storage.
   The default `stig_server` preset gives /var only 10 G — already
   flagged in UNIFI_INSTALL.md ("if /var ever fills up the install
   will get wedged").

2. **The `container_host` rule does nothing for UniFi.** It pins
   `/etc/containers/storage.conf` to `/srv/containers/$USER/storage`,
   but UniFi overrides this immediately. Keep `containers.enabled=false`.

This rebuild solves (1) with a custom `disk.layout` and uses v0.13's
`disk.target` by-id pinning so the install can't be redirected to the
wrong device on a multi-disk box. It carries (2) forward unchanged.

## Hardware

- **System disk:** 256 GB Samsung SSD 850 EVO, by-id
  `ata-Samsung_SSD_850_EVO_250GB_S2R5NX0HB19888W` (~232 GiB usable)
- **RAM:** 8 GB
- **NIC:** `eno1`
- **No secondary data disk.** (Unlike cougar — no `disk.data_disks`.)

## Config decisions

All fields not listed below inherit defaults from
`src/ks_gen/config.py:HostConfig`.

### Identity & network

| Field | Value | Notes |
|---|---|---|
| `system.hostname` | `unifi` | unchanged |
| `system.timezone` | `America/New_York` | matches cougar |
| `network.interfaces[0]` | `{device: eno1, bootproto: dhcp, onboot: true}` | DHCP with router-side MAC→IP reservation; stable inform URL lives on the router, not in the kickstart |

### Admin user

Locked admin with NOPASSWD sudo and key-only SSH. Console login is
intentionally impossible — offline recovery is GRUB emergency shell
(`rd.break=switch_root`) only. This matches the project default
(`reference_ks_gen_vm_testing` and the broader unifi pattern), not
cougar's console-password break-glass model.

| Field | Value |
|---|---|
| `user.admin.name` | `yizshachuck-admin` |
| `user.admin.gecos` | `"yizshachuck-admin"` |
| `user.admin.authorized_keys` | `["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIE4lYlqPDyt+c2YsS54ML0gS0eADwa/AswXmszzTUbdv pat@krypte.me"]` |
| `user.admin.password` | `null` (account is `passwd -l`-locked in `%post`) |
| `user.admin.sudo` | `nopasswd_yes` (sudoers fragment: `NOPASSWD: ALL`) |

The `HostConfig._admin_credential_mutex` validator enforces that
`password=null` implies `sudo=nopasswd_yes` — otherwise a locked
account could never escalate. `AdminUser._keys_or_password` enforces
at least one authorized key when the password is null.

### Packages

| Field | Value | Notes |
|---|---|---|
| `packages.preset` | `lean` | single-purpose controller; lean adds `logrotate`, `postfix`, `cronie`, `crontabs`, `parted` which UniFi's systemd timers + log rotation depend on |
| `packages.base_groups` | default (`@^minimal-environment` + `@standard`; lean strips `@standard`) | no GUI |
| `packages.extra` | `[]` | UniFi installer pulls its own podman stack |

### Disk layout

```yaml
disk:
  target: disk/by-id/ata-Samsung_SSD_850_EVO_250GB_S2R5NX0HB19888W
  wipe: true
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
```

**Sizing math on ~232 GiB usable:**
- EFI 1G + /boot 1G = 2G fixed partitions
- System LVs: 15+3+50+5+3+2 = 78G
- swap: anaconda `recommended` on 8 GB RAM ≈ 8G
- /home: 140G
- Total: 2 + 78 + 8 + 140 = 228G; ~4G VG slack

**Why /var = 50G** (vs. 10G default): UniFi binaries + image staging.
Five-fold headroom over the install-doc-flagged bottleneck. /var won't
grow much during steady-state but image rebuilds and dnf cache surges
need slack.

**Why /home = 140G**: UniFi's storage.conf override makes
`/home/uosserver/.local/share/containers` the real container storage
location. Backup history, device metadata, and the embedded MongoDB
all land there.

### Overrides

All `overrides.*` left at default. Specifically:

| Setting | Value | Why default is correct |
|---|---|---|
| `kernel_module_blacklist` | enabled, full list including `usb-storage` | server, no thumbdrive use case |
| `usbguard.enable` | false | server, no transient USB devices |
| `unattended_updates.reboot_window` | Sun 03:00 (default) | controller can take a weekly reboot |
| `fips_mode` | false | MODERN crypto policy requires non-FIPS |
| `dod_root_ca.install` | false | non-DoD |

### Containers, custom_post, exceptions

| Field | Value | Why |
|---|---|---|
| `containers.enabled` | false | `container_host` rule has no effect on UniFi (storage.conf override); enabling it just adds a useless `/srv/containers` LV |
| `custom_post` | `[]` | UniFi install is a post-deploy procedure (`UNIFI_INSTALL.md`) — pre-creating `uosserver` and home subdirs in `%post` would tangle with the recipe |
| `exceptions` | `[]` | no STIG waivers needed |

## File location

`build/unifi/unifi.yaml` — gitignored, machine-local. Same directory as
`build/unifi/UNIFI_INSTALL.md` so config and post-install recipe live
together.

## Build pipeline

```bash
# WSL on Windows (xorriso only available there)
cd /mnt/c/Users/yizshachuck/source/alma-linux-security
~/.venvs/ks-gen/bin/ks-gen gen -c build/unifi/unifi.yaml -o build/unifi/
~/.venvs/ks-gen/bin/ks-gen iso \
  --src AlmaLinux-9-latest-x86_64-dvd.iso \
  --ks build/unifi/ks.cfg \
  --tailoring build/unifi/tailoring.xml \
  --out build/unifi/unifi.iso
```

Post-install: follow `build/unifi/UNIFI_INSTALL.md` (pre-create
`uosserver` with 0700 home subdirs, run the UniFi installer, open
firewall rich rules per LAN subnet).

## Validation

The generated `ks.cfg` should show:

- `ignoredisk --only-use=disk/by-id/ata-Samsung_SSD_850_EVO_250GB_S2R5NX0HB19888W`
- `bootloader --boot-drive=disk/by-id/ata-Samsung_SSD_850_EVO_250GB_S2R5NX0HB19888W ...`
- `clearpart --all --initlabel --drives=disk/by-id/ata-Samsung_SSD_850_EVO_250GB_S2R5NX0HB19888W`
- `logvol /var --vgname=vg_root --name=lv_var --fstype=xfs --size=51200 --fsoptions="nodev"` (50 G = 51200 MiB)
- `logvol /home --vgname=vg_root --name=lv_home --fstype=xfs --size=143360 --fsoptions="nodev,nosuid"` (140 G)
- `network --device=eno1 --bootproto=dhcp --hostname=unifi --onboot=yes`
- `user --name=yizshachuck-admin --lock --groups=wheel --gecos="yizshachuck-admin" --shell=/bin/bash`
- `passwd -l yizshachuck-admin` in `%post` (admin account locked)
- `yizshachuck-admin ALL=(ALL) NOPASSWD: ALL` in
  `/etc/sudoers.d/00-ks-gen-admin`

## Out of scope

- Static IP migration (deferred to a router-reservation-aware future
  decision; the kickstart stays DHCP)
- A reusable `assets/install-unifi-os.sh` wrapper (UNIFI_INSTALL.md
  strategic-note item); manual recipe is fine for one machine
- The mgmt1 host's role going forward — that's a separate decision
- A static inform-URL DNS name for adoption — that's a router/DNS
  decision, not a kickstart concern
