# Design: `unifi` host kickstart config

**Date:** 2026-06-14
**Type:** Usage artifact (not a ks-gen feature) — produces a single
consumer YAML config that drives `ks-gen gen` / `ks-gen iso`.

## Goal

Author a ks-gen YAML config for a new STIG-hardened AlmaLinux 9 host
named `unifi`, intended to run UniFi OS Server. Save it to
`build/unifi/unifi.yaml` (gitignored, machine-local — sits next to the
existing `build/unifi/UNIFI_INSTALL.md` recipe).

## Background

This host follows the same shape as `mgmt1` (192.168.160.2), the first
proven UniFi-on-STIG deployment recorded in
`reference_unifi_install_on_stig_host.md`. The prior host used the
`container_host` rule, but that memory documents a finding: UniFi's
installer writes its own per-user `storage.conf` that overrides the
system-wide `/srv/containers/$USER/storage` pin from `container_host`.
The `container_host` rule therefore adds no real value for UniFi, and
this config drops it.

UniFi OS Server still runs containers — its installer pulls the podman
stack itself at install time, so we do not need to pre-stage podman in
`packages.extra`. The post-install setup remains the recipe in
`build/unifi/UNIFI_INSTALL.md` (pre-create `uosserver` with 0700 home
subdirs, then run the installer).

## Config

All fields not listed below inherit defaults from
`src/ks_gen/config.py:HostConfig`.

```yaml
system:
  hostname: unifi

network:
  interfaces:
    - device: eth0
      bootproto: dhcp
      onboot: true

user:
  admin:
    name: yizshachuck-admin
    gecos: "yizshachuck-admin"
    authorized_keys:
      - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIE4lYlqPDyt+c2YsS54ML0gS0eADwa/AswXmszzTUbdv pat@krypte.me"
    sudo: nopasswd_yes

packages:
  preset: lean
```

## Inherited defaults of note

- **Disk:** `stig_server` preset — LVM with the seven STIG-required
  mountpoints (`/`, `/home`, `/tmp`, `/var`, `/var/log`,
  `/var/log/audit`, `/var/tmp`), `wipe=true`, no LUKS, no
  `bootloader_password`, target disk auto-selected.
- **Crypto:** policy `MODERN` (FIPS off). Important: UniFi's container
  network and any modern SSH client will use ed25519/x25519; FIPS would
  block those at the kernel layer.
- **SSH:** port 22, key-only (`password_authentication: false`), no root
  login, `client_alive_interval=600`, `max_auth_tries=4`.
- **Packages:** `lean` preset — drops `@standard`, adds the lean
  compensating set (`logrotate`, `postfix`, `cronie`, `crontabs`,
  `parted`) on top of the STIG-required base
  (`scap-security-guide`, `openscap-scanner`, `aide`, `audit`,
  `rsyslog`, `chrony`, `firewalld`, `sudo`,
  `policycoreutils-python-utils`, `dnf-automatic`, `dnf-utils`).
- **Time:** chrony peers `pool.ntp.org`, timezone `UTC`.
- **Banner:** default STIG warning applied to issue, issue_net, motd,
  gdm.
- **Overrides:** unattended-updates enabled (nightly security, monthly
  full, weekly Sun 03:00 reboot window); kernel-module blacklist
  enabled; auditd disk-full action `SUSPEND`.
- **Admin credential mutex:** `yizshachuck-admin` has no password, so
  `sudo: nopasswd_yes` is mandatory (and is set).

## Sizing note

The `stig_server` preset reserves ~44 GiB across the fixed LVs plus
swap + EFI + /boot, putting minimum disk at ~50 GiB. UniFi's data lives
under `/var/lib/uosserver` which sits on the `/var` LV (~10 GiB
headroom). If the prior host ran into space pressure on `/var`, we may
need to either (a) switch from `packages.preset: lean` to a `disk.layout`
that enlarges `/var`, or (b) accept the limitation. The memory flags
this as a known quirk — surface it if growth becomes an issue, but the
default config is fine to start.

## Out of scope

- No LUKS (host sits in a physically secure rack; passphrase prompt
  would block remote reboot).
- No custom `disk.layout` (default `stig_server` is sufficient).
- No `containers.enabled` (UniFi installer handles podman itself).
- No `custom_post` UniFi pre-staging (the install recipe in
  `build/unifi/UNIFI_INSTALL.md` runs *after* install completes, by
  hand; encoding it in `custom_post` would couple ks-gen output to
  UniFi's installer behaviour, which has historically drifted).
- No FIPS, no DoD root CA, no usbguard (defaults).

## Deliverables

1. `build/unifi/unifi.yaml` — the config file described above.
2. Nothing else committed to the ks-gen repo; the config lives under
   gitignored `build/` and is consumed by the operator running
   `ks-gen gen --config build/unifi/unifi.yaml --out build/unifi/bundle/`
   (and optionally `ks-gen iso ...`).
