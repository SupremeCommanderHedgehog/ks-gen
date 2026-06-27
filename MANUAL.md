# ks-gen manual

This document is the operator's reference for `ks-gen` v0.1. The
[`README.md`](README.md) is a 30-second quickstart; this file is the
500-foot walkthrough. The design rationale lives in the
[design spec](docs/superpowers/specs/2026-06-01-alma-stig-kickstart-design.md).

## Contents

- [1. What ks-gen is](#1-what-ks-gen-is)
- [2. Installation](#2-installation)
- [3. Core concepts](#3-core-concepts)
- [4. The `host.yaml` file](#4-the-hostyaml-file)
- [5. Subcommands](#5-subcommands)
- [6. The override rule catalog](#6-the-override-rule-catalog)
- [7. The audit story — `exceptions.md`](#7-the-audit-story--exceptionsmd)
- [8. Building and using an installer](#8-building-and-using-an-installer) — includes [§8.5 Post-install verification](#85-post-install-verification-ks-gen-verify)
- [9. Common workflows](#9-common-workflows)
- [10. Troubleshooting](#10-troubleshooting)
- [11. Glossary](#11-glossary)
- [12. References](#12-references)

---

## 1. What ks-gen is

`ks-gen` is a Python 3.11+ CLI that turns one YAML file into a fully
configured AlmaLinux 9 Anaconda kickstart. The generated kickstart is:

- **DISA STIG compliant** — most rules are applied by the upstream
  `scap-security-guide` profile (`oscap xccdf eval --remediate`
  invoked from `%post` at install time), driven by a per-host
  `tailoring.xml`.
- **Remote-safe by default** — won't lock you out of a freshly-installed
  cloud or headless host. The admin user is created with
  `authorized_keys` in `%post` **before** any sshd config touch, the SSH
  port is opened in firewalld + SELinux **before** firewalld is enabled,
  and the kickstart leaves enough sshd attack surface intact for a key
  holder to log in on first boot.
- **Auditable** — every place the generator deviates from a literal
  STIG rule is logged in a generated `exceptions.md` with the XCCDF rule
  IDs it disabled and the reason why.
- **Reproducible** — the same `host.yaml` always produces the same
  bundle. CI re-renders, diffs against committed snapshots, ships.

### When to use ks-gen

- You're standing up a production AlmaLinux 9 server and want STIG
  baseline applied at install time, not bolted on afterward.
- The server is remote — a cloud VM, a colo'd bare-metal box, a
  hypervisor host — and you cannot afford a single missed key to lock
  you out.
- You want an audit trail of every STIG deviation, not a manual
  "we'll document the exceptions later" promise.

### When NOT to use ks-gen

- The server is a desktop / workstation (use the
  `scap-security-guide` `cis_workstation` profile instead, manually
  applied).
- You need RHEL 9 specifically, not AlmaLinux (the rule IDs match but
  the `meta.scap_content` filename differs — easily patched but not
  default).
- You need a profile other than DISA STIG (CIS Level 2, ANSSI, PCI-DSS,
  etc.). The hybrid model would work; the rule catalog and golden
  snapshots are STIG-specific in v0.1.

---

## 2. Installation

### Requirements

- Python 3.11, 3.12, or 3.13
- `pip` or `pipx`
- `xorriso` (only for `ks-gen iso`)

### Option A — `pipx` (recommended)

`pipx` keeps `ks-gen` in its own isolated virtualenv and drops a
single `ks-gen` binary on `PATH`:

```bash
pipx install .
ks-gen --help
```

To upgrade: `pipx upgrade ks-gen` (after a new tag).

### Option B — `pip` in a project venv

Useful when you're developing on the generator itself or want it
pinned alongside other dev tools:

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"     # Linux/macOS
# .venv\Scripts\pip install -e ".[dev]"  # Windows
.venv/bin/ks-gen --help
```

### Option C — module form

Works from a checked-out tree without installing:

```bash
python -m ks_gen --help
```

### Verifying the install

```bash
ks-gen rules
```

Should list 12 rules. If you see a Python `ImportError`, your venv is
missing one of `typer`, `pydantic`, `jinja2`, `pyyaml`, or `pykickstart`.

---

## 3. Core concepts

### 3.1 The four-file output bundle

Every successful run of `ks-gen new` or `ks-gen gen` writes a
`<hostname>/` directory containing four files. **None are optional**:

| File | What it is | Who reads it |
|---|---|---|
| `host.yaml` | The canonical, validated config. Re-runnable. | You, the next time you regenerate. Source-control it. |
| `ks.cfg` | The kickstart file. Lives at the ISO root or behind an HTTP URL referenced from `inst.ks=`. | Anaconda, at install time. |
| `tailoring.xml` | An XCCDF 1.2 tailoring document staged into the target rootfs by a `%post --nochroot` block at install time, then passed to `oscap --tailoring-file`. | `oscap` during the install-time `%post` remediation phase. |
| `exceptions.md` | Human-readable audit report listing every applied rule, every disabled XCCDF rule, and every declared exception. | You, your auditor, your future self. |

The bundle is self-contained. If you serve it from an HTTP root,
`ks.cfg` references `tailoring.xml` by the relative path
`/tailoring.xml` (both must live at the URL root the bootloader points
at). For ISO delivery, both files end up at the ISO's root via
`xorriso -map`.

### 3.2 Hybrid STIG application

DISA STIG for RHEL 9 has ~400 rules. `ks-gen` does **not**
reimplement them. It owns only the named conflict points between STIG
and remote safety, plus DoD-content neutralization — roughly 12 rules
in v0.1. Everything else is owned by `oscap` remediation via a
`%post` block that runs `oscap xccdf eval --remediate` directly.

Each ks-gen rule has up to two channels:

- **Tailoring channel** — XCCDF fragments merged into `tailoring.xml`.
  Runs *before* oscap remediation. Prevents oscap from doing something
  (disable a rule, set a variable's value).
- **Post channel** — shell injected into `%post`. Runs *after* oscap
  remediation. Used to add things oscap doesn't (admin authorized_keys,
  civilian banner) or re-assert values oscap may have over-tightened.

Execution timeline inside Anaconda:

```
%packages
  -> %post --nochroot [stages tailoring.xml]
  -> %post [oscap reads tailoring.xml, remediates]
  -> %post [ks-gen rule overrides]
  -> reboot
```

The chrooted `oscap` invocation passes `--fetch-remote-resources`; on
online installs it fetches the AlmaLinux OVAL CVE feed before
evaluating. On air-gapped installs (`hd:LABEL=`) the fetch fails
harmlessly — `|| true` swallows the non-zero exit, the install
completes, and OVAL-dependent rules skip. See §10 for the matching
troubleshooting entry.

### 3.3 The override rule contract

Every rule is a single file in `src/ks_gen/rules/`. The file exports
a module-level `RULE` binding satisfying the `Rule` protocol:

```python
class Rule(Protocol):
    id: str
    summary: str
    depends_on: list[str]
    stig_rules_affected: list[str]

    def applies(self, cfg: HostConfig) -> bool: ...
    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]: ...
    def emit_post(self, cfg: HostConfig) -> str: ...
    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None: ...
```

The catalog is filesystem-discovered. Rules are topologically sorted
by `depends_on` before their `emit_post` outputs are concatenated.

### 3.4 The three load-bearing safety invariants

These are enforced by tests, not just docs. They are why ks-gen is
"remote-safe by default":

1. **Lockout-resistance.** In every generated `ks.cfg`, the admin
   `authorized_keys` write occurs earlier in `%post` than any sshd
   config touch.
2. **Firewall sequencing.** No scenario enables firewalld before the
   configured SSH port has been added to it.
3. **No silent compliance drift.** Any rule whose `emit_tailoring`
   includes a `disable` op must produce a non-None `exception_entry`
   naming that XCCDF rule. Disabled rules show up in `exceptions.md`
   or the build fails.

### 3.5 Crypto policy

`crypto.policy` is the single most consequential knob. It sets the
system crypto-policy and decides whether `fips=1` lands in the
bootloader kernel cmdline:

| `crypto.policy` | System crypto-policy | FIPS kernel mode | Ed25519 / X25519 / ChaCha20 |
|---|---|---|---|
| `STIG`   | `FIPS`    | `fips=1` | blocked at kernel layer |
| `MODERN` | `DEFAULT` | off       | allowed |
| `FUTURE` | `FUTURE`  | off       | allowed (and SHA-1 banned everywhere) |

**Hard constraint:** `crypto.policy in {MODERN, FUTURE}` with
`overrides.fips_mode: true` is rejected at config load. FIPS kernel
mode would block Curve25519 below the application layer; the policies
would silently conflict at runtime. The generator refuses to produce
that combo.

`MODERN` is the default and the recommendation for most servers in
2026. It costs you FIPS 140-3 certification but earns you modern
post-quantum-adjacent curves and ciphers.

### 3.6 DoD-content neutralization

DISA STIG language is DoD/USG-specific. For a non-DoD server, several
controls assert things that aren't true ("U.S. Government Information
System"). `ks-gen` substitutes civilian-equivalent content and logs
the substitution:

| What | Default | Disabled XCCDF rule |
|---|---|---|
| Login banner | "WARNING: This is a private computer system…" | `banner_etc_issue`, `banner_etc_issue_net`, `dconf_gnome_banner_enabled` |
| Time servers | `pool.ntp.org` | (depends on STIG release; rule disabled when present) |
| DoD root CA bundle | not installed | `install_DoD_intermediate_certificates` |

Every substitution shows up in `exceptions.md`.

---

## 4. The `host.yaml` file

Strictly validated by pydantic 2 at load time. **Unknown keys are
errors**, not warnings — typos won't pass silently.

CLI `--set KEY=VALUE` (repeatable) applies dotted-path overrides on
top of the YAML *before* validation. Use it for one-off tweaks
without editing the file.

The full schema:

### 4.1 `meta` (defaults shown)

```yaml
meta:
  release: "9"
  profile: stig                                  # oscap profile id stem
  scap_content: ssg-almalinux9-ds.xml            # datastream filename
```

`profile` becomes `xccdf_org.ssgproject.content_profile_<profile>`.
Override only if you're tailoring against a non-STIG profile (e.g.,
`cis`).

### 4.2 `system` (hostname required)

```yaml
system:
  hostname: web01.example.com      # required, no default
  timezone: UTC                    # default
  locale: en_US.UTF-8
  keyboard: us
```

### 4.3 `network`

```yaml
network:
  interfaces:
    - device: link                 # 'link' = first link-up NIC
      bootproto: dhcp              # dhcp | static
      onboot: true
      # static-only:
      # ip: 10.0.0.10
      # netmask: 255.255.255.0
      # gateway: 10.0.0.1
      # nameservers: [1.1.1.1, 9.9.9.9]
  dns_search: []
  hostname_from_dhcp: false        # don't let DHCP rewrite system.hostname
```

Static interfaces must supply `ip`, `netmask`, **and** `gateway` —
absence of any is a config error.

### 4.4 `disk`

```yaml
disk:
  preset: stig_server              # stig_server | minimal (for custom layouts use disk.layout — see below)
  target: sda                      # optional; confines install to this disk in multi-disk hosts
  wipe: true                       # clearpart --all --initlabel
  bootloader_password: null        # null | "..."
```

`stig_server` is the default and what most production servers want. It
creates separate `/`, `/home`, `/tmp`, `/var`, `/var/log`,
`/var/log/audit`, `/var/tmp`, `swap` LVs with STIG-required mount
options (`nodev`, `nosuid`, `noexec` where appropriate). `minimal`
collapses non-`/` mounts into root.

`bootloader_password` is STIG-required. `null` means "left unset by
ks-gen" — supply a value or accept the resulting STIG finding.

`disk.target` works with all three partitioning modes (`preset:
stig_server`, `preset: minimal`, and `disk.layout`). When set, it
emits `ignoredisk --only-use=<target>`, `clearpart --drives=<target>`,
`bootloader --boot-drive=<target>`, and `part --ondisk=<target>` on
every partition line — so the install cannot touch sibling drives on
multi-disk hosts. Leave unset to keep today's behavior (anaconda picks
disks by enumeration order).

As of v0.13, `disk.target` accepts persistent identifiers under
`/dev/disk/by-id/` and `/dev/disk/by-path/` — drop the leading `/dev/`
when writing the value (e.g. `disk/by-id/ata-FOO`). The same regex
covers bare kernel names (`sda`, `nvme0n1`) so existing host.yaml
files load unchanged. By-id targeting is strongly recommended on
hosts where SATA-port enumeration is unstable (the kernel-name `sda`
can swap to `sdb` on reseat).

#### `disk.layout` (alternative to `disk.preset`)

For operators who need to customize partition sizes or add extra
mountpoints, `disk.layout` accepts a structured LVM definition. It is
mutually exclusive with `disk.preset`.

```yaml
disk:
  target: sda             # see disk.target above; works with layout too
  layout:
    lvs:
      - {name: root, mount: /}
      - {name: home, mount: /home}
      - {name: tmp, mount: /tmp}
      - {name: var, mount: /var, size: 20G}     # override default 10G
      - {name: varlog, mount: /var/log}
      - {name: varlogaudit, mount: /var/log/audit}
      - {name: vartmp, mount: /var/tmp}
      - {name: srv, mount: /srv, size: 50G}     # custom mountpoint
      - {name: swap, fstype: swap}
```

LVs that mount a STIG-required path can omit `size:` and inherit the
default from this table:

| Mountpoint | Default size | Default fsoptions |
|---|---|---|
| `/` | 15G | (none) |
| `/home` | 5G | `nodev,nosuid` |
| `/tmp` | 3G | `nodev,nosuid,noexec` |
| `/var` | 10G | `nodev` |
| `/var/log` | 5G | `nodev,nosuid,noexec` |
| `/var/log/audit` | 3G | `nodev,nosuid,noexec` |
| `/var/tmp` | 2G | `nodev,nosuid,noexec` |
| swap | `--recommended` | (none) |

LVs that mount a non-STIG path (`/srv`, `/data`, etc.) must specify
`size:` explicitly. `fsoptions:` can be set explicitly on any LV to
override the default.

The PV grows to fill the disk; LVs are fixed-size, leaving free VG
space for future `lvextend`. The `/boot` and `/boot/efi` partitions
default to 1G xfs/efi respectively and can be overridden with a top-level
`boot:` or `efi:` block.

STIG-required mountpoints (`/`, `/home`, `/tmp`, `/var`, `/var/log`,
`/var/log/audit`, `/var/tmp`) are enforced at config-load — a layout
missing any of them fails with a specific error.

Per-LV encryption (`lvs[].encrypted: true`) is not supported — use the
`disk.luks` block below for PV-level LUKS that covers all LVs.

#### `disk.data_disks` (secondary mounts, v0.13+)

`disk.data_disks` is a list of secondary physical disks. Each entry
declares one disk:

```yaml
disk:
  target: disk/by-id/ata-SYSTEM_SSD
  preset: stig_server
  data_disks:
    - target: disk/by-id/ata-DATA_HDD     # by-id strongly recommended
      mount: /data                         # must start with /
      fstype: xfs                          # xfs (default) or ext4
      fsoptions: nodev,nosuid              # STIG-aligned default; null for none
      wipe: true                           # true (default) | false
      # wipe: false adds exactly one of:
      # partition: 1                       # /dev/<target>-partN; target must be by-id or by-path
      # partition_uuid: 0f2a-1c3b-...      # UUID=... in fstab
      # partition_label: my_data_lbl       # LABEL=... in fstab
```

When `wipe: true` (the default), anaconda formats the disk via a
`part <mount> --fstype=<fs> --grow --size=1 --ondisk=<target>` line and
mounts it during install — the resulting `/etc/fstab` entry is
generated for free.

When `wipe: false`, the disk is **omitted from `ignoredisk --only-use=`
and `clearpart --drives=`** so anaconda ignores it entirely. The
`data_disks_preserve` rule then writes one fstab entry from `%post`
using the chosen identifier (partition number, UUID, or label),
followed by `mount -a` + `restorecon -R <mounts>`. Pick the
identifier that survives the operation: `partition_uuid` is most
robust; `partition_label` is the friendliest when you control the
label; `partition: 1` is the implicit default and assumes the legacy
single-partition layout. **`partition: N` requires a stable target
(`disk/by-id/...` or `disk/by-path/...`)** — bare kernel-name
targets like `sdb` don't have a `/dev/disk/by-id/sdb-partN` symlink,
so use `partition_uuid` or `partition_label` for those.

Cross-field rules enforced at config load:

- `data_disks` requires `disk.target` to be set (without a system
  target, anaconda's `clearpart --all` would clobber the data disks).
- Targets must be distinct across `disk.target` and all
  `data_disks[*].target`.
- Mounts must be distinct and must not collide with `/`, `/boot`,
  `/boot/efi`, the active layout/preset's LV mounts, or
  `/srv/containers` (when `containers.enabled`).
- The `minimal` preset is incompatible with `data_disks` — use
  `stig_server` or `disk.layout`.

##### Install-regression recommendation

This feature touches every "DO recommend" path in `CLAUDE.md`'s
install-regression guidance: schema defaults, template fan-out, and a
new `%post`-writing rule. Before merging a host that uses `data_disks`
in anger, run the install-regression harness with a two-disk QEMU VM —
once for each of the `wipe: true` and `wipe: false` paths. The
harness recipe lives at `.scratch/install-regression/` (gitignored,
per-developer).

#### `disk.luks` (PV-level LUKS encryption)

Enables LUKS2 encryption on the LVM physical volume, with optional
clevis/tang network-bound unlock.

```yaml
disk:
  preset: stig_server     # or `disk.layout: ...`
  luks:
    preset: partial       # or "tang" or "none" (default)
    passphrase: hunter2   # OR passphrase_file (mutually exclusive)
    # tang only when preset == tang:
    # tang:
    #   servers:
    #     - url: https://tang1.example.com
    #       thumbprint: <sha256-base64url>
    #     - url: https://tang2.example.com
    #       thumbprint: <sha256-base64url>
    #   threshold: 1       # SSS threshold; default 1
```

| Preset | Behavior |
|---|---|
| `none` (default) | No LUKS. |
| `partial` | LUKS2 on the LVM PV (`pv.01`). All LVs inherit. `/boot` and `/boot/efi` stay plain. Passphrase unlock. |
| `tang` | Same coverage as `partial`. Adds a `%post` block that installs `clevis-luks`, binds to each tang server (Shamir Secret Sharing across servers with threshold-of-N), and enables `clevis-luks-askpass.path`. The `passphrase` field stays as a fallback if all tang servers are unreachable. |

**Passphrase source.** Provide exactly one of `passphrase:` (inline,
operator-friendly but lands in VCS if `host.yaml` is committed) or
`passphrase_file:` (relative-to-cwd path read at `ks-gen gen` time;
keep the file out of VCS).

**Tang thumbprint capture.** Tang servers advertise their signing key
via HTTPS. Capture the thumbprint with the same tool that does the
binding:

```bash
clevis-encrypt-tang '{"url": "https://tang1.example.com"}' < /dev/null 2>&1 \
  | grep -oP 'Trust the .*? Tang server.*? \(\K[^)]+'
```

Pin that thumbprint in `host.yaml` to prevent first-boot
trust-on-first-use weakness.

**Constraints.**

- `disk.preset: minimal` has no LVM PV — `disk.luks` is rejected at
  config-load. Use `disk.preset: stig_server` or `disk.layout` instead.
- Per-LV encryption via `disk.layout.lvs[].encrypted: true` is rejected
  at config-load with a pointer to `disk.luks.preset` (the supported
  PV-level path).
- LUKS2 + argon2id is FIPS-compatible on AlmaLinux 9.2+; no special
  configuration needed.

**Post-install rotation.** To rotate the passphrase later:

```bash
cryptsetup luksAddKey   /dev/<pv-device> [/path/to/new-key]
cryptsetup luksRemoveKey /dev/<pv-device> [/path/to/old-key]
```

For tang re-binding after a tang server rotates its key, re-run
`clevis luks bind` with the new thumbprint and remove the old slot
with `clevis luks unbind`.

### 4.5 `user.admin` — the lockout-resistance cornerstone

```yaml
user:
  admin:
    name: opsadmin                 # required; cannot be 'root'
    gecos: "Ops Admin"
    groups: [wheel]                # must include wheel for sudo
    shell: /bin/bash
    password: null                 # null = key-only login
    sudo: nopasswd_no              # nopasswd_no | nopasswd_yes
    authorized_keys:               # at least one if password is null
      - "ssh-ed25519 AAAA... opsadmin@laptop"
```

Two cross-field invariants are enforced at load time:

- `name` cannot be `root` (literal string `"root"` raises a
  validation error).
- If `password` is `null`, `authorized_keys` must have at least one
  entry. Empty list + null password is rejected.

### 4.6 `ssh`

```yaml
ssh:
  port: 22                         # 1-65535
  permit_root_login: "no"          # no | prohibit-password
  password_authentication: false   # default key-only
  client_alive_interval: 600
  client_alive_count_max: 1
  max_auth_tries: 4
  use_pam: true
```

Custom `port` triggers the `ssh_keep_open` rule to add a SELinux
`semanage port` entry and a firewalld port allowance.

### 4.7 `banner`

```yaml
banner:
  text: |
    WARNING: This is a private computer system. Unauthorized access is
    prohibited. All activity on this system may be monitored and logged.
    Use of this system constitutes consent to such monitoring.
  apply_to: [issue, issue_net, motd, gdm]
```

The default text is civilian-equivalent. `apply_to` selects which
files get the banner. `gdm` only matters with a GUI installed.

### 4.8 `time`

```yaml
time:
  servers: [pool.ntp.org]          # not USNO/DoD by default
  chrony_makestep_threshold: 1.0
```

### 4.9 `crypto`

```yaml
crypto:
  policy: MODERN                   # STIG | MODERN | FUTURE
```

See §3.5 for what each value means.

### 4.10 `packages`

```yaml
packages:
  preset: standard               # "standard" (default) or "lean"
  base_groups: ["@^minimal-environment", "@standard"]
  required:                        # STIG/oscap dependencies + ops baseline
    - scap-security-guide
    - openscap-scanner
    - aide
    - audit
    - rsyslog
    - chrony
    - firewalld
    - sudo
    - policycoreutils-python-utils
  extra: []
  excluded:                        # STIG-forbidden defaults
    - telnet-server
    - rsh-server
    - tftp-server
    - vsftpd
    - ypserv
```

`excluded` packages are both removed from `%packages` (`-package`)
and purged via `dnf -y remove` in `%post`. Belt and braces, because
some get pulled in transitively by groups.

#### `preset: standard` vs `preset: lean`

- **`standard`** (default) emits `base_groups` as written. The RHEL/Alma
  `@standard` group lands on the system: vim-enhanced, mlocate, sos,
  smartmontools, postfix, parted, and ~80 other conventional admin tools.
  Closest to the AlmaLinux DVD interactive install.
- **`lean`** strips `@standard` from the emitted base groups and
  auto-adds the packages the STIG profile expects to find regardless
  (`logrotate`, `postfix`, `cronie`, `crontabs`, `parted`). Cuts ~75
  packages off the install footprint with no oscap-remediation cost.
  Choose this for single-purpose appliance hosts (container hosts,
  edge nodes, bastions) where the full admin toolset is not wanted.

The preset is purely additive over `required` — explicitly listing any
of the lean compensating packages in `required` is safe; they are
deduped, not double-added.

`excluded` wins over the preset. If you set `preset: lean` and also
list one of the compensating packages (e.g. `postfix`) in `excluded`,
the package is excluded from `%packages` and purged in `%post` — you
opt out of that part of the lean preset's STIG-compliance guarantee.

### 4.11 `containers` — rootless container host preset

A complete worked example combining this preset with `packages.preset: lean`
lives at [`examples/host-container.yaml`](examples/host-container.yaml) — copy
it, swap in your hostname and SSH keys, and run `ks-gen gen`.

```yaml
containers:
  enabled: true                  # default false
  users:                         # may be empty; script still installs at /root
    - name: webapp
      gecos: "Web app workloads"
      authorized_keys:
        - "ssh-ed25519 AAAA... webapp@bastion"
        - "ssh-ed25519 BBBB... webapp@laptop"
    - name: dbproxy
      authorized_keys:
        - "ssh-ed25519 CCCC... dbproxy@bastion"
  volume:
    size: "20G"                  # default 20G; pattern ^\d+(M|G|T)$
    fsoptions: "nodev,nosuid"    # default; `noexec` token is rejected
```

When `enabled: true`, the generated kickstart:

1. Auto-injects an extra logvol `/srv/containers` (XFS, sized per `volume.size`, mounted with `volume.fsoptions`) into the partition layout. Works for both `disk.preset` and `disk.layout` shapes.
2. Adds the rootless-podman package stack to `%packages`: `podman`, `crun`, `slirp4netns`, `fuse-overlayfs`, `containers-common`, `podman-plugins`. (`policycoreutils-python-utils` for `semanage` is already in the standard required list and gets deduped.)
3. Drops `/root/create-rootless-user.sh` (mode 0550, root:root) — the same script the kickstart uses to create users is available to the operator for post-install user provisioning.
4. Writes `/etc/containers/storage.conf` with `rootless_storage_path = "/srv/containers/$USER/storage"` so podman lands new users' graphroot on the mirror automatically.
5. For each `users[]` entry: calls the script with `-l` (linger always-on) and the configured `gecos`, then writes the full `authorized_keys` file. Container users have no sudo, no wheel group, and a real shell (`/bin/bash`) for SSH login.

#### Recommended pairing with `packages.preset: lean`

A container-host typically wants the lean package baseline (see §4.10). The two presets compose orthogonally:

```yaml
packages:
  preset: lean
containers:
  enabled: true
  users:
    - name: webapp
      authorized_keys: ["..."]
```

#### Post-install user provisioning

After install, the operator can add additional rootless container users with the same script kickstart used:

```bash
sudo /root/create-rootless-user.sh -l -c "Analytics workloads" analytics
# add a public key:
sudo /root/create-rootless-user.sh -l -k "$(cat ~/.ssh/id_ed25519.pub)" deploy
# scaffold a starter Quadlet set for testing:
sudo /root/create-rootless-user.sh -l -q -c "Sandbox" sandbox
```

The script is idempotent — re-running it on an existing user is safe and will just (re)apply any options you pass.

#### Constraints

- Container users' names must be distinct from `user.admin.name` (container users are for rootless workloads; admins manage the host).
- If you're using `disk.layout` (not `disk.preset`), don't add a `/srv/containers` LV yourself — the container-host preset auto-injects it.
- `volume.fsoptions` rejects `noexec`. Container image layers must execute.
- **Disk-size budget.** With `disk.preset: stig_server`, the fixed STIG LVs already consume ~44 GiB (`/` 15, `/var` 10, `/home` 5, `/var/log` 5, `/var/log/audit` 3, `/var/tmp` 2, `/tmp` 3) plus `--recommended` swap and `/boot` + EFI. The default `volume.size: 20G` for `/srv/containers` therefore needs a disk of roughly **70 GiB or larger** to install cleanly. On smaller disks, shrink `volume.size` accordingly or move the container LV onto a separate disk via `disk.layout`.

### 4.12 `overrides` — the conflict-point matrix

Each knob has a safe-by-default value. You override to either tighten
or loosen the STIG/remote-safe tradeoff for a specific host.

```yaml
overrides:
  fips_mode: false                 # bool; mutex with crypto.policy != STIG
  faillock:
    enable: true
    deny: 3
    unlock_time: 900               # STIG default 0 (forever) -> 900s for remote safety
    even_deny_root: false          # STIG says true; false keeps an emergency root path
  auditd:
    disk_full_action: SUSPEND      # STIG default HALT
    disk_error_action: SUSPEND
    max_log_file_action: ROTATE    # STIG default keep_logs
  ssh_keep_open:
    ensure_firewalld_port: true
    ensure_selinux_port: true
  usbguard:
    enable: false                  # default off for cloud/headless
  kernel_module_blacklist:
    enable: true
    modules: [usb-storage, cramfs, freevxfs, jffs2, hfs, hfsplus, squashfs, udf]
  package_purge:
    enable: true
  dod_root_ca:
    install: false                 # default skip
  unattended_updates:
    enable: true                              # master switch; false leaves STIG defaults
    nightly_security:
      enable: true
      on_calendar: "*-*-* 02:00:00"           # systemd OnCalendar; nightly 02:00 host-local
    monthly_full:
      enable: true
      on_calendar: "Sun *-*-1..7 02:30:00"    # first Sunday each month, 02:30 host-local
    reboot_window:
      enable: true
      on_calendar: "Sun *-*-* 03:00:00"       # weekly Sunday 03:00 host-local
```

**Fleet operators:** the maintenance-window defaults are *not* staggered.
A datacenter where every host runs the same `host.yaml` will see every
host reboot at Sunday 03:00 in unison. Set `reboot_window.on_calendar`
to different values per host (or per rack) to avoid a synchronous
fleet-wide reboot.

The rule preserves the STIG `timer_dnf-automatic_enabled` control — it
overrides the stock timer's `OnCalendar` via a systemd drop-in rather
than disabling and replacing the unit.

See §6 for what each rule does with these inputs.

### 4.13 `custom_post`

```yaml
custom_post:
  - |
    # Raw shell appended to %post --erroronfail, after all rule blocks.
    echo "post-install hook from custom_post" >> /root/install.log
```

Each list entry becomes its own `%post` block separated by
`# ===== custom_post =====` markers. Runs **after** every ks-gen
rule's `emit_post`.

### 4.14 `exceptions`

```yaml
exceptions:
  - id: no-luks
    reason: "Cloud provider encrypts volumes; remote unattended reboot required."
    stig_rules_disabled:
      - xccdf_org.ssgproject.content_rule_encrypt_partitions
```

For deliberate, operator-acknowledged deviations outside the override
matrix. Each entry:

- Names an `id` (any string — appears in `exceptions.md` as a heading)
- Gives a `reason` that ends up in the audit report
- Lists the XCCDF rule IDs it disables (`stig_rules_disabled` is
  required and non-empty)

These flow straight into the generated `tailoring.xml`. Use them
sparingly and keep the `reason` honest.

---

## 5. Subcommands

All subcommands accept `--help`. Exit codes documented at §5.7.

### 5.1 `ks-gen new`

Interactive wizard. Walks you through hostname, timezone, locale,
admin user, SSH keys, SSH port, and crypto policy, then offers an
opt-in checkbox for three optional sections: disk layout, network,
and the override matrix. Writes the full 4-file bundle.

```bash
ks-gen new --out ./build
# ./build/<hostname>/{host.yaml,ks.cfg,tailoring.xml,exceptions.md}

ks-gen new --out ./build --non-interactive
# Errors out unless every required field has a default;
# skips all optional sections (output matches the legacy 4-prompt run).
```

The optional sections cover:

- **Disk**: preset (`stig_server` / `minimal`), wipe confirmation,
  LUKS encryption (`none` / `partial` with inline or sidecar-file
  passphrase). Custom `disk.layout:`, `bootloader_password`, and
  `tang` LUKS are intentionally hand-edit only.
- **Network**: per-interface device, bootproto (dhcp / static), and
  for static interfaces IP / netmask / gateway / nameservers. Loops
  to "add another?" after each interface. Bond / bridge / VLAN are
  hand-edit only.
- **Override matrix**: two checkbox prompts — default-on rules to
  disable (`faillock`, `kernel_module_blacklist`, `package_purge`,
  `unattended_updates`), and default-off rules to enable (`usbguard`,
  `dod_root_ca`). Nested fields (e.g., `faillock.deny`,
  `unattended_updates.nightly_security.on_calendar`) remain
  hand-edit; same for `fips_mode`, `auditd_actions`, `ssh_keep_open`,
  and the `exceptions:` list.

### 5.2 `ks-gen gen`

Non-interactive re-render from an existing `host.yaml`. The
CI/change-control path:

```bash
ks-gen gen --config build/web01/host.yaml --out build/web01

# Override individual fields on the command line
ks-gen gen --config build/web01/host.yaml \
           --set ssh.port=2222 \
           --set overrides.fips_mode=true \
           --out build/web01-fips
```

`--set` supports `key=value` pairs (repeatable). Values are parsed
YAML-style: `true`/`false`/`null`/integers/floats/quoted strings.
For non-trivial structures, edit the YAML directly.

After writing the bundle, `gen` auto-runs `lint` on the produced
`ks.cfg`. A lint failure causes `gen` to exit with code 4.

### 5.3 `ks-gen lint`

Two-stage validation against a `ks.cfg` on disk:

1. `pykickstart`'s `ksvalidator` — structural kickstart grammar.
2. Internal re-parser — confirms the load-bearing safety invariants
   (authorized_keys present, `# ===== admin_user_and_keys =====`
   precedes `# ===== ssh_config_apply =====`, tailoring referenced).

```bash
ks-gen lint build/web01/ks.cfg
# OK    (exit 0)

# Or, on a broken file:
# FAIL: missing: authorized_keys write in %post
# FAIL: ordering: admin_user_and_keys must precede ssh_config_apply
# (exit 4)
```

Useful for re-checking a hand-edited or stored kickstart.

### 5.4 `ks-gen iso`

Repackages the AlmaLinux DVD ISO with `ks.cfg` and `tailoring.xml`
embedded at the root.

```bash
ks-gen iso \
  --src AlmaLinux-9-latest-x86_64-dvd.iso \
  --ks  build/web01/ks.cfg \
  --tailoring build/web01/tailoring.xml \
  --out web01-installer.iso \
  --volid ALMA9            # default
```

**Unattended boot:** the wrapper rewrites `isolinux/isolinux.cfg` and
`EFI/BOOT/grub.cfg` to add a top-level "Unattended STIG install
(ks-gen)" entry, set it as the default, and shorten the timeout to
5 seconds. The original "Install AlmaLinux 9" entry is preserved
below as a fallback — arrow-down to recover the interactive flow.
Both BIOS (isolinux) and UEFI (grub) paths are rewritten.

**How `tailoring.xml` gets to oscap:** the generated `ks.cfg` opens
with a `%post --nochroot` block that runs in the Anaconda installer
environment (not the target chroot) and copies
`/run/install/repo/tailoring.xml` — the path Anaconda mounts the
boot media at — to `/mnt/sysimage/root/tailoring.xml`
(= `/root/tailoring.xml` on the installed system).
A chrooted `%post` block then runs `oscap xccdf eval --remediate`
against it. The same `--nochroot` block handles HTTP delivery via
`curl`; the transport is auto-detected from `/proc/cmdline`. No HTTP
server is needed for the ISO path.

`xorriso` must be on `PATH`. If it isn't, `iso` exits 5 with a
clear error.

### 5.5 `ks-gen rules`

Lists the shipped rule catalog. Useful for audit and "did this
version add a rule?" diffs.

```bash
ks-gen rules                       # table view
ks-gen rules --id crypto_policy    # detailed view of one rule
ks-gen rules --format json         # machine-readable
```

The JSON output is suitable for piping into `jq`, archiving as a
release artifact, or driving tooling that needs the canonical list
of XCCDF rules each ks-gen rule touches.

### 5.6 `ks-gen schema`

Emits the JSON Schema for `host.yaml` on stdout:

```bash
ks-gen schema > host.schema.json
```

Drop it next to your config file and editors like VSCode or PyCharm
will give you autocomplete + inline validation via:

```yaml
# yaml-language-server: $schema=./host.schema.json
```

### 5.7 Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Usage error (bad CLI arguments) |
| 2 | Config invalid (YAML or schema failed) |
| 3 | Rule conflict (e.g., `crypto.policy=MODERN` + `fips_mode=true`) |
| 4 | Lint failure on generated `ks.cfg` |
| 5 | External tool missing (`xorriso`, `ksvalidator`, `ssh`/`scp`) |
| 6 | `verify`: at least one rule fails on the live host |
| 7 | `verify`: transport failure (ssh unreachable, sudo prompt, ARF parse error) |
| 8 | `verify --check-tailoring`: workstation `host.yaml` differs from deployed `/root/tailoring.xml` (and compliance is otherwise clean) |

CI scripts can branch on these precisely. Code 3 in particular tells
you the YAML is internally inconsistent in a way that isn't a typo —
the generator refused to produce an unsafe kickstart. Codes 6, 7, and 8
are only emitted by `ks-gen verify`; see §8.5 for details.

---

## 6. The override rule catalog

Thirteen rules ship today. Each has its own file in
`src/ks_gen/rules/`. Run `ks-gen rules` for the live list with
exact XCCDF IDs.

### Lockout-resistance critical (not optional)

| Rule | What it does |
|---|---|
| `admin_user_and_keys` | Creates the wheel admin in `%post`, drops `authorized_keys`, writes `/etc/sudoers.d/00-ks-gen-admin`. **Runs first.** |
| `ssh_keep_open` | If `ssh.port != 22`: `semanage port -a -t ssh_port_t -p tcp <port>`. Always (when enabled): `firewall-offline-cmd --add-port=<port>/tcp`. **Runs before firewalld is enabled.** |
| `faillock_safety` | Tailors `unlock_time` and `deny` variables; when `even_deny_root=false`, disables the matching XCCDF rule; re-asserts `/etc/security/faillock.conf` in `%post`. |
| `crypto_policy` | `update-crypto-policies --set {FIPS|DEFAULT|FUTURE}`. When not STIG: tailoring disables `enable_fips_mode`, `sshd_use_approved_{ciphers,kex,macs,mac_ordered}`; `%post` runs `ssh-keygen -A` to generate Ed25519 host keys (which `sshd-keygen` won't make in FIPS mode). |
| `ssh_config_apply` | Writes `/etc/ssh/sshd_config.d/00-ks-gen.conf` with `Port`, `PermitRootLogin`, `PasswordAuthentication`, `ClientAlive*`, `MaxAuthTries`, `UsePAM`; runs `sshd -t` to validate. Hard depends on `admin_user_and_keys` and `ssh_keep_open`. |

### DoD-content neutralization

| Rule | What it does |
|---|---|
| `banner_text` | Disables the XCCDF rules that would set DoD banner content; `%post` writes civilian text to `/etc/issue`, `/etc/issue.net`, `/etc/motd`, and the GDM banner file if present. |
| `time_servers` | Writes `/etc/chrony.conf` from `cfg.time.servers` (defaults to `pool.ntp.org`, not USNO). |
| `dod_root_ca` | When `overrides.dod_root_ca.install: false`, disables the XCCDF rule that mandates installing the DoD root/intermediate CA bundle. |

### Environment knobs

| Rule | What it does |
|---|---|
| `auditd_actions` | Sets `disk_full_action` / `disk_error_action` / `max_log_file_action` to operator-chosen values (defaults `SUSPEND`/`SUSPEND`/`ROTATE` instead of STIG's `HALT`/`HALT`/`keep_logs`). |
| `usbguard` | Per `overrides.usbguard.enable`: either selects the USBGuard install + service oscap rules, or disables them. |
| `kernel_module_blacklist` | Writes `/etc/modprobe.d/ks-gen-blacklist.conf` with `install <mod> /bin/true` lines for each configured module. |
| `package_purge` | `dnf -y remove <packages.excluded>` after install completes — catches transitive pulls from group installs. |
| `unattended_updates` | Configures `dnf-automatic` for nightly security + monthly full updates and drops a `needs-restarting`-driven reboot timer that fires only inside `overrides.unattended_updates.reboot_window`. Stock `dnf-automatic.timer` is kept enabled with operator-supplied `OnCalendar` via drop-in. |

### What is NOT a rule (handled by oscap)

SELinux enforcing, AIDE install + initial DB build, `login.defs`
UMASK/PASS_MAX_DAYS, sudo `!rootpw` + `requiretty`, `/etc/issue`
*permissions*, audit rules content (~80 `auditctl` rules), firewalld
*enabled*, chronyd *enabled*, and the full ~400 other STIG rules
remain owned by the upstream `scap-security-guide` profile. ks-gen
doesn't touch them.

If a STIG release ever moves one of these into "conflict" territory,
it graduates into a new rule file.

---

## 7. The audit story — `exceptions.md`

Every bundle includes an `exceptions.md`. It's not optional and it's
not for ks-gen's authors — it's for you and your auditor.

Structure:

```markdown
# Exceptions report

Generated: 2026-06-01T12:34:56Z
Host: `web01.example.com`

## Summary
- Applied rules: 12
- Tailored XCCDF rules: 13
- Declared exceptions: 1

## Applied rules
- `admin_user_and_keys` — Create wheel admin, drop authorized_keys, sudoers fragment.
- `ssh_keep_open` — Ensure ssh.port reachable in firewalld + SELinux before sshd starts.
- ...

## Tailored XCCDF rules (oscap rules disabled or value-tailored)
| XCCDF rule | Tailored by |
|---|---|
| xccdf_org.ssgproject.content_rule_banner_etc_issue | banner_text |
| xccdf_org.ssgproject.content_rule_sshd_use_approved_ciphers | crypto_policy |
| ...

## Rule exception details
### `banner_text` — Substitutes private-system banner for DISA-mandated DoD text.
_Reason:_ Server is not a U.S. Government Information System; literal DoD
banner would make false legal claims. Civilian text satisfies the rule
intent (warn unauthorized users; consent to monitoring).

Disabled XCCDF rules:
- `xccdf_org.ssgproject.content_rule_banner_etc_issue`
- ...

## Declared exceptions (from host.yaml)
### `no-luks`
_Reason:_ Cloud provider encrypts volumes; remote unattended reboot required.

Disabled XCCDF rules:
- `xccdf_org.ssgproject.content_rule_encrypt_partitions`
```

How to read it:

- **"Applied rules"** is what `ks-gen rules` would have shown for
  this exact config. It's the inventory.
- **"Tailored XCCDF rules"** is the diff vs. the stock oscap STIG
  profile. Every row is an oscap rule that won't run as the upstream
  intended. The right column says which ks-gen rule made the call.
- **"Rule exception details"** is each ks-gen rule's reasoning for
  its tailoring. Use this section to challenge a deviation: if the
  reason isn't convincing for your environment, change the override
  knob and regenerate.
- **"Declared exceptions"** is your `host.yaml`'s `exceptions:` block
  — deliberate operator decisions outside the override matrix.

The **"no silent compliance drift"** invariant guarantees that any
XCCDF rule disabled by ks-gen is listed here. If you grep
`tailoring.xml` for `selected="false"` and any IDs don't appear in
`exceptions.md`, that's a bug — please file it.

---

## 8. Building and using an installer

The kickstart is a text file. Anaconda fetches it via one of several
mechanisms; pick the one that matches your environment.

### 8.1 HTTP delivery (PXE / cloud-init)

Serve the bundle from an HTTP root:

```
http://provisioner.example.com/web01/ks.cfg
http://provisioner.example.com/web01/tailoring.xml
```

Point the bootloader at it:

```
inst.ks=http://provisioner.example.com/web01/ks.cfg
```

`ks.cfg` references `tailoring.xml` by the relative path
`/tailoring.xml`, so both must live at the same URL root the
bootloader fetches from.

### 8.2 OEMDRV USB

Anaconda auto-mounts a USB volume labelled `OEMDRV` and looks for
`ks.cfg` at its root:

```bash
mkfs.vfat -n OEMDRV /dev/sdX
mount /dev/sdX /mnt
cp build/web01/ks.cfg build/web01/tailoring.xml /mnt/
umount /mnt
```

Boot the target from the standard AlmaLinux ISO with the USB
plugged in. No kernel cmdline edit required.

### 8.3 Embedded in a custom ISO

```bash
ks-gen iso \
  --src AlmaLinux-9-latest-x86_64-dvd.iso \
  --ks dist/web01/ks.cfg \
  --tailoring dist/web01/tailoring.xml \
  --out web01-installer.iso
```

Boot the resulting ISO and the unattended STIG install runs by
default after a 5-second timeout. If you need to recover the
interactive Anaconda flow, arrow-down to "Install AlmaLinux 9" within
the timeout window.

For writing the resulting ISO to a USB stick on Windows, see §8.6.

### 8.4 First-boot verification

Once the system reboots and you can SSH in:

```bash
# Confirm STIG profile applied
sudo oscap xccdf eval \
  --profile xccdf_org.ssgproject.content_profile_stig \
  --tailoring-file /root/tailoring.xml \
  /usr/share/xml/scap/ssg/content/ssg-almalinux9-ds.xml

# Confirm admin user works
id opsadmin
sudo -lU opsadmin

# Confirm SSH config
sshd -T | egrep -i '^(port|permitrootlogin|passwordauth|clientalive)'

# Confirm firewalld port
sudo firewall-cmd --list-ports

# Confirm crypto policy
update-crypto-policies --show
```

The oscap result should be a small set of "fail" entries — every one
of them should correspond to an entry in your `exceptions.md`. If
something fails that ISN'T in `exceptions.md`, that's drift between
the kickstart and the live system and warrants investigation.

### 8.5 Post-install verification (`ks-gen verify`)

`ks-gen verify` automates the §8.4 oscap re-run from the workstation
side — no manual SSH, no raw oscap command. It runs `oscap` on the
deployed host over SSH, pulls the ARF, reconciles failures against
`host.yaml`, and reports compliance + drift against the install-time
baseline.

#### Command shape

```bash
ks-gen verify --host <addr> --config hosts/<name>/host.yaml
```

All flags:

| Flag | Default | Purpose |
|---|---|---|
| `--host` | (required) | Target address or hostname |
| `--config`/`-c` | (required) | Path to `host.yaml` |
| `--user` | `cfg.user.admin.name` | SSH login user |
| `--ssh-opts` | `""` | Extra args appended to every `ssh`/`scp` call (shell-quoted) |
| `--format` | `table` | Output format: `table` or `json` |
| `--arf-out` | (none) | Persist pulled ARFs to this directory |
| `--keep-arf` | false | Persist pulled ARFs to a new temp directory (path is echoed) |
| `--no-drift` | false | Skip the install-time ARF pull; compliance-only |
| `--timeout` | 600 | oscap run timeout in seconds |

#### Prerequisites

- `ssh` and `scp` on the workstation's `PATH`. Missing either exits
  with code 5.
- The admin user (`cfg.user.admin.name`) reachable via SSH with the
  workstation's key in `~/.ssh/authorized_keys`.
- **Passwordless sudo** for that user. The wizard defaults to
  `sudo: nopasswd_no`; set `sudo: nopasswd_yes` for hosts you intend
  to verify remotely. The locked-password-requires-nopasswd validator
  enforces it whenever the admin has no password. Hosts not configured
  this way fail with:
  ```
  ks-gen verify: sudo -n true failed (exit N) on <host> as <user>: passwordless sudo is required
  ```
- `/root/tailoring.xml` present on the host (placed there by every
  ks-gen install). Hosts not provisioned by ks-gen are not supported.

#### Output

Plain-text table grouped by category, omitting clean rules:

```
verify host=h1.example.com user=ops at=2026-06-07T12:00:00Z
  summary: clean=412 expected_fail=3 new_fail=1 regression=2 incomplete=0 — FAILURES

  CATEGORY    CURRENT  INSTALL  EXP  RULE
  regression  fail     pass     no   xccdf_org.ssgproject.content_rule_<id>
  new_fail    fail     -        no   xccdf_org.ssgproject.content_rule_<id>
  ...
```

Column widths are dynamic. The `EXP` column is `yes` when the rule
appears in the host's declared exceptions (so a failure is allowed),
`no` otherwise. `--format json` emits the same data as a JSON document.

#### Drift comparison

`verify` pulls the install-time ARF from `/root/oscap-remediation-results.xml`
and compares rule outcomes against the live run. A rule that passes
now and failed at install is clean; a rule that fails now and passed
at install is reported as `regression`.

If the install-time ARF is missing (e.g., rotated or never written),
the table prints a banner:

```
  NOTE: drift comparison skipped — install-time ARF not present on host
```

The compliance check still runs; only the `regression` vs. `new_fail`
distinction is lost. `--no-drift` skips the install-baseline pull
entirely (compliance-only mode).

#### Exit codes

| Code | Meaning |
|---|---|
| 0 | All rules pass or are accounted for by declared exceptions (`expected_fail`); no `new_fail` or `regression`. |
| 1 | Bad `--format` value (usage error). |
| 2 | `host.yaml` invalid. |
| 5 | `ssh` or `scp` not on `PATH`. |
| 6 | At least one rule fails on the live host (`new_fail` or `regression`). |
| 7 | Transport failure: ssh unreachable, sudo prompt, oscap not runnable, ARF parse error. |
| 8 | `--check-tailoring`: workstation `host.yaml` differs from deployed `/root/tailoring.xml`, and compliance is otherwise clean. Compliance failures (code 6) take precedence — a host with both exits 6. |

Codes 3 and 4 are never emitted by `verify` (they're `gen`/`lint`-only —
see §5.7 for the global table). CI scripts can branch on these; code 6
in particular means the host is live but non-compliant — actionable for
a remediation pass.

#### Out of scope (v0.3)

Single-host, on-demand only. Batch sweeps, captured-baseline mode,
tailoring drift detection, on-host self-check timers, history tracking,
HTML report generation, and exception auto-suggest are tracked
separately as GitHub issues #10–#17.

---

#### Auto-suggesting exception entries

When `verify` reports `new_fail` or `regression` rules, three new flags
help close the audit loop:

- `--suggest-exceptions` — render one `ExceptionDecl` per failing rule
  (`new_fail` and `regression` both), formatted for paste into
  `host.yaml`'s `exceptions:` list. Each suggestion's `id` is
  `auto-<category>-<rule_id>`; its `reason` starts with `TODO:` and
  carries the verify-run context (host, date, current/install states).
- `--apply` — append the suggestions to `host.yaml` after writing a
  backup at `host.yaml.bak` (single rotating slot) and round-tripping
  the candidate through `HostConfig.model_validate()`. The original
  file is byte-identical to its pre-call state on any failure path
  (yaml-parse error, schema-rejecting candidate, IO error). Implies
  `--suggest-exceptions`.
- `--allow-regression` — let `--apply` write regression-category
  suggestions in addition to `new_fail`. The split is deliberate:
  regressions represent rules that passed at install but now fail,
  which is more often a real correctness drift than a legitimate new
  exception. The two-flag dance forces an explicit operator decision.

Worked example:

```bash
ks-gen verify --host web01.example.com --config build/web01/host.yaml \
              --suggest-exceptions
# (prints the table report, then a "## Suggested exception entries"
# block of YAML you can paste into host.yaml's exceptions: list)

ks-gen verify --host web01.example.com --config build/web01/host.yaml \
              --apply
# (also writes the new_fail suggestions to host.yaml; .bak preserves
# the prior content; regression-category suggestions are skipped with
# a stderr note)

ks-gen verify --host web01.example.com --config build/web01/host.yaml \
              --apply --allow-regression
# (also writes regression-category suggestions)
```

**Formatting caveat.** `--apply` uses PyYAML to round-trip
`host.yaml`. Comments and quoting style choices in the original file
are not preserved. The `host.yaml.bak` is the recovery path. Operators
who maintain hand-written comments in `host.yaml` should hand-paste
the rendered suggestions instead of using `--apply`.

Re-running `--apply` with the same suggestions is idempotent: each
already-present `auto-<category>-<rule_id>` id is skipped (no second
write, mtime unchanged), so verifying once and applying twice doesn't
duplicate entries.

#### Detecting tailoring drift

`ks-gen verify --check-tailoring` re-renders the tailoring locally from
the workstation `host.yaml` and diffs it against `/root/tailoring.xml`
on the deployed host. Use this when you've edited `host.yaml` after
install and want to confirm the change hasn't been deployed yet.

Drift is reported as a per-op diff:

````
Tailoring drift detected — workstation host.yaml differs from /root/tailoring.xml.
Re-run `ks-gen gen <host.yaml>` and redeploy to align.

  + disable xccdf_org.ssgproject.content_rule_grub2_audit_argument
  - disable xccdf_org.ssgproject.content_rule_package_telnet_removed
  ~ xccdf_org.ssgproject.content_value_var_password_pam_unix_remember: 5 → 24
````

Glyphs: `+` op present in expected but not deployed, `-` present in
deployed but not expected, `~` set-value differs (shown as
`deployed → expected`).

**Exit codes.** When `--check-tailoring` is set and drift is detected
but compliance is otherwise clean, `verify` exits `8`
(`TAILORING_DRIFT`). Compliance failures (exit `6`) take precedence —
a host with both compliance fail and drift exits `6`. A host with no
drift and clean compliance exits `0`.

**Drift does not mean non-compliant.** The host is still being
measured against the tailoring deployed at install time. The drift
report is about workstation/host divergence — your intent vs the
host's reality. The fix path is `ks-gen gen <host.yaml>` followed by
redeploying the bundle (re-burn ISO, ship updated `tailoring.xml`, etc.
— whatever delivery method you used originally).

**JSON output.** `verify --format json --check-tailoring` adds a
top-level `tailoring_drift` key. The key is omitted (not present) when
the flag isn't set, so consumers can use `key in payload` to detect
whether the check ran.

#### Capturing and using a workstation baseline

`ks-gen verify --capture-baseline <path>` runs oscap on the host as
usual, then writes the resulting ARF to `<path>` on your workstation.
The normal verify report still prints — capture is a side effect of a
regular verify run, not a separate operation.

`ks-gen verify --baseline <path>` uses that captured file as the drift
baseline instead of the host's `/root/oscap-remediation-results.xml`.
The install ARF is not pulled at all when `--baseline` is set.

The two flags are mutually exclusive in a single invocation — capturing
and using a baseline are two operator intents on two different days.

**When to use this.** Two common scenarios:

1. **Post-install manual review.** You finish a kickstart install, SSH
   in, fix some failing rules by hand or accept others as exceptions
   in `host.yaml`. You want future verify runs to treat the reviewed
   state as ground truth, not the dirty install state. Capture the
   baseline after review:

   ````
   ks-gen verify --capture-baseline ./baseline.arf.xml \
       --host host.example.com --config host.yaml
   # ... review the report ...
   # From now on:
   ks-gen verify --baseline ./baseline.arf.xml \
       --host host.example.com --config host.yaml
   ````

2. **SSG upgrade staleness.** Months later, `scap-security-guide`
   upgrades and adds/removes rules. The install ARF on the host
   references rule IDs that no longer exist in the current SCAP
   content. Verify can't reliably distinguish "rule passed" from "rule
   no longer evaluated" against a stale install ARF — recapture against
   the new SSG to refresh.

**Stale-baseline warning.** When the captured baseline references rules
that don't exist in the current ARF (typically caused by an SSG upgrade
between capture and verify), the report shows:

````
  NOTE: 7 rules in baseline not present in current ARF — baseline may be stale (SSG upgraded?)
````

Doesn't change exit codes — pure information. The JSON output's
`baseline.orphans` array lists the affected rule IDs.

**File format.** Same XCCDF ARF that `oscap xccdf eval` produces —
verbatim. An operator can hand-produce one with stock `oscap` (without
ks-gen) and feed it in via `--baseline`. The capture flow simply
relocates what's already there.

**Doesn't replace `host.yaml` exceptions.** Captured baseline and
declared exceptions are orthogonal axes:
- `host.yaml` exceptions = "this failing rule is intentional; never
  surface it as a problem"
- Captured baseline = "the reconcile diff should be measured against
  THIS state, not against install state"

Use both together when appropriate.

**JSON output.** `verify --format json --baseline <path>` adds a
top-level `baseline` key with `path`, `captured_utc`, and `orphans`.
The key is omitted when `--baseline` isn't set.

### 8.6 Writing a ks-gen ISO to USB on Windows (Rufus)

Boot media for `ks-gen iso` output on Windows. Verified against
Rufus 4.x on Windows 11. (`ks-gen iso` itself still needs `xorriso`,
which on Windows means a WSL Ubuntu install with `apt install
xorriso` — see §2 for the venv setup. This section is about turning
the resulting `.iso` into a bootable USB stick.)

#### Step 1 — Reset the USB stick if it was previously DD-written

A USB that's been previously written with Rufus's "DD image" mode
(or any tool that wrote a raw hybrid ISO to the block device)
carries a partition table that Windows tools can't reliably
re-partition. `diskpart`'s `clean` command wipes the table and
disk signatures so Rufus can treat the stick as a blank target.

Open an elevated PowerShell, find the USB by size:

```powershell
Get-Disk
```

Then, substituting the correct disk number for `N`:

```powershell
Clear-Disk -Number N -RemoveData -RemoveOEM -Confirm:$false
```

Double-check the disk number before running. Picking the system
drive's number wipes your OS.

#### Step 2 — Run Rufus

1. **Device:** the USB stick.
2. **Boot selection:** click *Select* and pick your ks-gen ISO.
3. **Partition scheme:** **MBR**. Produces a USB bootable on both
   BIOS-CSM and UEFI targets. Pick GPT only if you know the target
   firmware has no CSM/legacy path.
4. **Target system:** *BIOS or UEFI* (auto-set by the MBR choice).
5. **Volume label:** must read exactly `ALMA9`. Rufus reads this
   from the ISO's volid (which `ks-gen iso` sets via `-volid`), so
   it should already be correct — but glance at the field before
   clicking *Start*. **If it's anything else, type `ALMA9` in
   manually.** The bootloader cmdline that ks-gen wrote references
   `hd:LABEL=ALMA9` for both `inst.stage2=`, `inst.repo=`, and
   `inst.ks=`. A label mismatch means anaconda can't find the
   install tree, the kickstart, or both.
6. **File system:** *FAT32* (Rufus default for hybrid Linux ISOs).
7. Click *Start*. At the ISOHybrid prompt, choose **Write in ISO
   Image mode (Recommended)**. **Do not pick DD Image mode** —
   some UEFI firmwares only enumerate the ESP partition of a DD-
   written hybrid ISO, hiding `/ks.cfg` from anaconda entirely.

Eject the USB cleanly from Explorer when Rufus finishes. Plug it
into the target, boot, pick the USB in the firmware boot menu.
The ks-gen menu entry runs by default after a 5-second timeout.

#### When this isn't enough

For multi-disk targets where the kernel's `sda`/`sdb`/`sdc`
enumeration shuffles between boots, the kickstart needs stable disk
identifiers (`/dev/disk/by-id/...`) instead of kernel device names.
Anaconda accepts these in `--ondisk=`, `--drives=`, and
`--boot-drive=`. Hand-edit the post-`ks-gen gen` `ks.cfg` to
substitute kernel names with by-id paths, then re-run `ks-gen iso`.
See §9.6 for the recommended patch-tracking workflow that keeps the
substitution version-controlled and reproducible across
regenerations.

#### Alternatives if Rufus still doesn't work

- **OEMDRV USB** (§8.2) — skip `ks-gen iso` entirely. Boot from a
  vanilla AlmaLinux DVD ISO (write to USB with any tool, including
  Rufus's straightforward path for an unmodified AlmaLinux ISO),
  with a second FAT-formatted USB labeled `OEMDRV` carrying just
  `ks.cfg` and `tailoring.xml`. Anaconda auto-discovers the
  kickstart by label. No bootloader rewrite, no label-matching
  gymnastics, no xorriso requirement on the workstation.
- **HTTP delivery** (§8.1) — for cloud / network-boot environments,
  serving the bundle over HTTP sidesteps physical media entirely.

## 9. Common workflows

### 9.1 Spin up a new cloud VM

1. Run `ks-gen new --out ./build`, answer the prompts, paste your
   SSH public key.
2. Upload `build/<hostname>/ks.cfg` and
   `build/<hostname>/tailoring.xml` to your HTTP provisioner
   (or wherever your cloud's custom-image workflow expects them).
3. Boot the instance with `inst.ks=` pointing at `ks.cfg`.
4. SSH in as the admin user with the key you supplied.

### 9.2 Build an installer USB for a bare-metal box

1. `ks-gen new --out ./build`.
2. Edit `build/<hostname>/host.yaml` to set static networking and
   `overrides.usbguard.enable: true` (bare metal has a console; you
   probably want USBGuard).
3. `ks-gen gen --config build/<hostname>/host.yaml --out build/<hostname>`
   to re-render.
4. `ks-gen iso --src ... --out installer.iso`, burn to USB.
5. Boot, hit Tab/e, append the `inst.ks=` line, install.

### 9.3 Re-render after a STIG release update

When `scap-security-guide` ships a new release, XCCDF rule IDs
sometimes change. Workflow:

1. Update `meta.scap_content` if the datastream filename changed.
2. Run `ks-gen gen` for each host you manage.
3. Run `pytest -q` on the ks-gen source tree — the golden snapshots
   will fail if any tailored XCCDF ID was renamed.
4. Investigate snapshot diffs. If a rule renamed, update the
   relevant ks-gen rule file's hardcoded ID constant. Regenerate.
5. Diff each host's new `ks.cfg` against the version-controlled one.
6. Re-deploy.

### 9.4 Add a custom `%post` block

Append shell to `custom_post[]` in `host.yaml`:

```yaml
custom_post:
  - |
    # Pull our org's CA bundle
    curl -fsSL https://internal.example.com/ca.pem \
      -o /etc/pki/ca-trust/source/anchors/org-ca.pem
    update-ca-trust extract
```

It runs **after** every ks-gen rule's `emit_post`, which means the
admin user, sshd config, firewalld, crypto policy, etc., are all in
place by then. Don't put lockout-sensitive logic here.

### 9.5 Diff two configs before changing one

`exceptions.md` is the right diff target — not `ks.cfg`. Two
configs produce very different `ks.cfg` files for trivial reasons
(different hostnames, regenerated timestamps), but the exceptions
report only changes when the *security posture* changes.

```bash
diff build/web01/exceptions.md build/web02/exceptions.md
```

### 9.6 Hand-edit the kickstart via a tracked patch

When you need to extend the generated kickstart beyond what
`host.yaml` models — RAID layouts, stable disk identifiers
(`/dev/disk/by-id/...` substituted for `sda`/`sdb`/`sdc`),
bootloader cmdline tweaks, custom `%pre` blocks — the right pattern
is **not** to hand-edit `ks.cfg` once and call it done. Hand-edits
get lost the next time you regenerate. Instead, capture the delta
as a `patch` file checked into the same place `host.yaml` lives,
and re-apply it as a build step.

#### Capture the patch once (after your first hand-edit)

```bash
ks-gen gen --config host.yaml --out build/

cd build/<hostname>
cp ks.cfg ks.cfg.orig
# Hand-edit ks.cfg: RAID layout, by-id paths, whatever you need.
diff -u ks.cfg.orig ks.cfg > ../../kickstart.patch
cd ../..

git add host.yaml kickstart.patch
git commit -m "track <hostname> kickstart customization"
```

#### Apply on every regeneration

```bash
ks-gen gen  --config host.yaml --out build/
patch -d build/<hostname>/ -p0 < kickstart.patch
ks-gen lint build/<hostname>/ks.cfg
ks-gen iso \
  --src AlmaLinux-9-latest-x86_64-dvd.iso \
  --ks build/<hostname>/ks.cfg \
  --tailoring build/<hostname>/tailoring.xml \
  --out build/<hostname>/installer.iso
```

#### Wrapper script

Drop this next to `host.yaml` and `kickstart.patch` in your operator
repo as `build-installer.sh`. Run from WSL on Windows (or any Linux
shell) — `ks-gen iso` needs `xorriso`.

```bash
#!/usr/bin/env bash
# Build an installer ISO from host.yaml + kickstart.patch.
set -euo pipefail

HOST="${1:?usage: $0 <hostname> [host.yaml] [kickstart.patch] [src.iso]}"
HOST_YAML="${2:-host.yaml}"
PATCH_FILE="${3:-kickstart.patch}"
SRC_ISO="${4:-AlmaLinux-9-latest-x86_64-dvd.iso}"

BUNDLE="build/$HOST"

ks-gen gen --config "$HOST_YAML" --out build/
[[ -f "$PATCH_FILE" ]] && patch -d "$BUNDLE" -p0 < "$PATCH_FILE"
ks-gen lint "$BUNDLE/ks.cfg"
ks-gen iso \
  --src "$SRC_ISO" \
  --ks "$BUNDLE/ks.cfg" \
  --tailoring "$BUNDLE/tailoring.xml" \
  --out "$BUNDLE/installer.iso"

echo "ready: $BUNDLE/installer.iso"
```

#### Cautions

- **Always re-lint after patching.** `ks-gen lint` re-validates the
  three load-bearing safety invariants (§3.4). If your patch
  reorders `admin_user_and_keys` past `ssh_config_apply`, drops the
  oscap fetch block, or strips the `--fetch-remote-resources` flag,
  lint exits 4 and you find out before burning an ISO. The wrapper
  script runs lint between patch and iso for exactly this reason.
- **Patches are line-positionally brittle.** When ks-gen upstream
  changes lines around your edits, the patch fails to apply
  (`Hunk #N FAILED`). When that happens, re-capture: delete
  `kickstart.patch`, regenerate, re-edit, re-diff, re-commit.
  Don't merge stale hunks by hand.
- **Don't patch `%post` bodies that come from rules.** If you find
  yourself editing shell inside a `# ===== <rule_id> =====` block,
  that's a signal you want either a new rule (file in
  `src/ks_gen/rules/`) or a `custom_post` block in `host.yaml` —
  not a patch. Patches are for layout-level things ks-gen's schema
  doesn't model yet (RAID, by-id, bootloader cmdline).

---

## 10. Troubleshooting

### "I can't SSH into the freshly-installed VM"

Most likely causes, in descending probability:

1. **You forgot to wait for the post-install reboot.** The kickstart
   ends with `reboot --eject`. SSH isn't available until after the
   reboot completes (~30-90 seconds depending on the host).
2. **Network came up on a different interface than expected.** Check
   your cloud provider's serial console / VM console for the actual
   assigned IP. If you used `device: link` and DHCP, the configured
   hostname is in the lease.
3. **Wrong key.** Confirm the public key in `host.yaml` is the one
   matching your private key (`ssh-keygen -y -f ~/.ssh/id_ed25519`).
4. **firewalld didn't get the rule.** Should never happen — the
   `ssh_keep_open` invariant test prevents it — but if you suspect
   it: at the console, `firewall-cmd --list-ports`.
5. **fail2ban / cloud security group.** Your cloud provider's
   network ACL may be the actual blocker. Check the provider side.

If you're truly locked out and have console access:

```bash
# At the local console, log in via the password you set in host.yaml,
# or via single-user mode if no password was set.
sudo cat /root/.ssh/authorized_keys   # confirm the bundle landed
sudo systemctl status sshd            # confirm sshd is running
sudo journalctl -u sshd               # confirm sshd accepted the config
sudo firewall-cmd --list-all          # confirm the port is in the zone
```

### "ks-gen lint failed on my ks.cfg"

Common lint failures:

- **`missing: authorized_keys write in %post`** — Something stripped
  the admin user block. Either your `custom_post` overwrites it, or
  a hand-edit removed it. Regenerate.
- **`ordering: admin_user_and_keys must precede ssh_config_apply`** —
  Same root cause; topo sort would never produce this.
  Hand-edit removed the section markers, or the rule registry is
  bypassed.
- **`missing: %post --nochroot oscap fetch block`** — The leading
  `%post --nochroot` block that stages `tailoring.xml` is missing
  or its `--log=` path was hand-edited. Regenerate.
- **`ordering: oscap fetch block must precede oscap eval block`** —
  Something reordered the `%post` blocks; the fetch must run before
  the chrooted oscap eval. Regenerate.
- **`missing: hd:LABEL= branch in oscap fetch case`** — The
  `hd:LABEL=*)` arm of the fetch `case` statement was removed.
  ISO-delivered installs (`inst.ks=hd:LABEL=…`) will hard-fail
  without it. Regenerate.
- **`missing: hd: cp from /run/install/repo in oscap fetch case`** —
  The `hd:LABEL=` arm is present but the `cp /run/install/repo/...`
  line that does the actual staging was edited. Regenerate.
- **`missing: --fetch-remote-resources flag in %post oscap block`** —
  The chrooted `oscap xccdf eval` invocation is missing the
  `--fetch-remote-resources` argument. Without it, STIG rules tied
  to the AlmaLinux OVAL CVE feed silently skip at install time.
  Regenerate.
- **`ksvalidator: ...`** — pykickstart's parser disagrees with the
  syntax. Almost always a malformed `%post` heredoc or stray
  character from a hand-edit.

If lint fails on a freshly-generated bundle (no hand edits), that's
a bug — please file it.

### "oscap remediation failed during install"

Check `/root/ks-post-oscap-fetch.log`, `/root/ks-post-oscap.log`,
and `/root/ks-post.log` (in that order — they correspond to the
fetch / eval / overrides `%post` blocks), and `/tmp/anaconda.log`
on the install media or via VNC. The most
common remediation failures:

- A package was removed but oscap expected it to be present.
- A service was disabled but oscap's rule tried to enable it.
- The custom crypto policy hadn't been applied yet when oscap
  checked for FIPS mode.

The oscap remediation `%post` block runs *before* the `ks-gen`
rule-overrides `%post` block, so any `crypto_policy` rule output
in the overrides block is too late to influence oscap's view.
Tailoring is the right channel for this — and ks-gen
handles it for the rules in its catalog. If you've added custom
oscap rules, you may need to add tailoring entries for them in
`exceptions[]`.

### "I see a fetch failure for security.almalinux.org in the oscap log on an ISO install"

Expected. The install-time `oscap xccdf eval` invocation passes
`--fetch-remote-resources` so STIG rules whose OVAL definitions
reference the AlmaLinux CVE feed at
`https://security.almalinux.org/oval/org.almalinux.alsa-9.xml.bz2`
can run. On an ISO-delivered (`hd:LABEL=`) install with no
install-time network access, that fetch fails — the eval wrapper
`|| true` swallows the non-zero exit, the install completes, and
the affected OVAL-dependent rules skip the same way they did in
v0.1.

If you need CVE-tied coverage on an air-gapped install, re-run
`oscap xccdf eval` manually after the system boots with network
access and an updated SSG content package — there is no
installer-side workaround in v0.2.

If the failed fetch appears on an install that DOES have network
access (HTTP delivery, working DNS, no egress filtering of
`security.almalinux.org`), that's a real problem worth
investigating: check `/etc/resolv.conf`, the host firewall, and
any upstream proxy configuration.

### "the install reboots to a black screen"

`fips=1` on the bootloader requires the dracut FIPS module. If
`overrides.fips_mode: true` is set and the dracut module wasn't
regenerated, the kernel won't come up. This is one of the reasons
the v0.1 default is `fips_mode: false`.

If you need FIPS, ensure `dracut --regenerate-all --force` ran
successfully in `%post`. The `crypto_policy` rule does this in the
STIG path; if it didn't, check the log.

### "I added a rule but it's not running"

`ks-gen rules` lists the discovered rules. If yours isn't there:

- File must be in `src/ks_gen/rules/` (not a subdirectory).
- Filename can't start with `_` (underscored modules are skipped).
- Must export a module-level `RULE` binding satisfying the protocol.
- Must be reachable via `from ks_gen.rules.<name>` import (i.e.,
  no syntax errors).

If it's listed but its output isn't in the bundle, check
`applies(cfg)` — it might be returning `False` for your config.

### "Rufus made a USB that boots, but anaconda's install source / packages / user sections are all blank"

Two near-certain causes:

1. **Volume label mismatch.** The bootloader cmdline references the
   install media by `hd:LABEL=ALMA9` for `inst.stage2=`,
   `inst.repo=`, and `inst.ks=`. If Rufus formatted the USB's FAT32
   partition with a label other than `ALMA9`, none of those lookups
   resolve. Open the USB in Windows Explorer; the drive name must
   read exactly `ALMA9`. If it doesn't, redo the write with Rufus's
   "Volume label" field manually set to `ALMA9` before clicking
   Start. See §8.6 step 2.
2. **DD Image mode was picked at the ISOHybrid prompt.** Some UEFI
   firmwares only enumerate the ESP partition of a DD-written
   hybrid ISO, hiding `/ks.cfg` and the AlmaLinux package tree on
   the ISO9660 partition. Symptom variant: stage2 loads but
   anaconda shows "Error setting up base repository," or it boots
   but only sees the UEFI filesystem. Run `Clear-Disk` on the USB
   to reset the partition table (§8.6 step 1), then redo with
   Rufus's **ISO Image mode**.

If neither matches the symptom, check that you're running ks-gen
v0.12.2 or later — v0.12.1 and earlier omitted `inst.repo=` from
the bootloader cmdline and the top-level `user --name=` directive
from the kickstart, both of which anaconda's GUI needs to satisfy
its prerequisite gates on FAT32 USB installs.

---

## 11. Glossary

- **Anaconda** — Red Hat's OS installer. Reads kickstart files.
- **Kickstart** — Anaconda's automation config format. The `ks.cfg`
  file. Documented at the [Anaconda project][anaconda].
- **OSCAP** — The OpenSCAP scanner / remediator. CLI tool.
- **`oscap-anaconda-addon`** — Anaconda addon that runs `oscap` with
  remediation enabled during install. Reads tailoring at install time.
- **SCAP** — Security Content Automation Protocol. The umbrella of
  XCCDF + OVAL + CPE + … specifications.
- **SCAP Security Guide (SSG)** — Upstream collection of XCCDF
  profiles; the `scap-security-guide` package. Contains the
  `xccdf_org.ssgproject.content_profile_stig` profile this generator
  drives.
- **STIG** — Security Technical Implementation Guide. DISA's
  hardening baseline.
- **XCCDF** — Extensible Configuration Checklist Description Format.
  The rule language SCAP uses.
- **Tailoring** — An XCCDF document that selects which rules of a
  profile run, and overrides their variables, without modifying the
  upstream profile.
- **FIPS 140-3** — NIST's federal crypto module certification. The
  RHEL 9 `FIPS` system crypto-policy enforces FIPS-approved
  algorithms.
- **Curve25519 / Ed25519** — Modern elliptic curves with strong
  security properties; not FIPS-approved as of early 2026.
- **`update-crypto-policies`** — RHEL/AlmaLinux command that switches
  the system-wide crypto policy. One change, applies to SSH, TLS,
  GnuTLS, NSS, libssh, and the kernel.

[anaconda]: https://anaconda-installer.readthedocs.io/en/latest/kickstart.html

---

## 12. References

- DISA STIG for Red Hat Enterprise Linux 9 — https://public.cyber.mil/stigs/
- AlmaLinux 9 documentation — https://wiki.almalinux.org/
- Upstream SCAP Security Guide — https://github.com/ComplianceAsCode/content
- Anaconda kickstart syntax — https://pykickstart.readthedocs.io/
- `oscap-anaconda-addon` — https://github.com/OpenSCAP/oscap-anaconda-addon
- RHEL 9 crypto policies — https://access.redhat.com/articles/3642912

For ks-gen's own design rationale, see
[`docs/superpowers/specs/2026-06-01-alma-stig-kickstart-design.md`](docs/superpowers/specs/2026-06-01-alma-stig-kickstart-design.md).
For the implementation plan, see
[`docs/superpowers/plans/2026-06-01-ks-gen-implementation.md`](docs/superpowers/plans/2026-06-01-ks-gen-implementation.md).
