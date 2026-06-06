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
- [8. Building and using an installer](#8-building-and-using-an-installer)
- [9. Common workflows](#9-common-workflows)
- [10. Troubleshooting](#10-troubleshooting)
- [11. Glossary](#11-glossary)
- [12. References](#12-references)

---

## 1. What ks-gen is

`ks-gen` is a Python 3.11+ CLI that turns one YAML file into a fully
configured AlmaLinux 9 Anaconda kickstart. The generated kickstart is:

- **DISA STIG compliant** — most rules are applied by the upstream
  `scap-security-guide` profile (via the `oscap-anaconda-addon`),
  driven by a per-host `tailoring.xml`.
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
| `tailoring.xml` | An XCCDF 1.2 tailoring document referenced by `%addon org_fedora_oscap`. | `oscap` during Anaconda's remediation phase. |
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
in v0.1. Everything else is owned by `oscap` remediation via the
`%addon org_fedora_oscap` block.

Each ks-gen rule has up to two channels:

- **Tailoring channel** — XCCDF fragments merged into `tailoring.xml`.
  Runs *before* oscap remediation. Prevents oscap from doing something
  (disable a rule, set a variable's value).
- **Post channel** — shell injected into `%post`. Runs *after* oscap
  remediation. Used to add things oscap doesn't (admin authorized_keys,
  civilian banner) or re-assert values oscap may have over-tightened.

Execution timeline inside Anaconda:

```
%packages -> %addon org_fedora_oscap [reads tailoring.xml, remediates] -> %post -> reboot
```

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
  preset: stig_server              # stig_server | minimal (custom reserved for v0.2)
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
  base_groups: ["@^minimal-environment", "@standard"]
  required:                        # STIG/oscap dependencies + ops baseline
    - scap-security-guide
    - openscap-scanner
    - oscap-anaconda-addon
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

### 4.11 `overrides` — the conflict-point matrix

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

### 4.12 `custom_post`

```yaml
custom_post:
  - |
    # Raw shell appended to %post --erroronfail, after all rule blocks.
    echo "post-install hook from custom_post" >> /root/install.log
```

Each list entry becomes its own `%post` block separated by
`# ===== custom_post =====` markers. Runs **after** every ks-gen
rule's `emit_post`.

### 4.13 `exceptions`

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
admin user, SSH keys, SSH port, crypto policy. Writes the full
4-file bundle.

```bash
ks-gen new --out ./build
# ./build/<hostname>/{host.yaml,ks.cfg,tailoring.xml,exceptions.md}

ks-gen new --out ./build --non-interactive
# Errors out unless every required field has a default
```

The wizard in v0.1 covers system / user / SSH / crypto. Disk,
network, and override-matrix tuning go through `--set` or by
editing the produced `host.yaml` and re-running `ks-gen gen`.

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

**v0.1 limitation:** the wrapper places the files at the ISO root
but does NOT rewrite `isolinux/isolinux.cfg` or
`EFI/BOOT/grub.cfg`. At the Anaconda boot prompt you must press
**Tab** (BIOS) or **e** (UEFI) and append:

```
inst.ks=hd:LABEL=ALMA9:/ks.cfg
```

Bootloader rewriting for fully unattended installs is tracked for
v0.2.

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
| 5 | External tool missing (`xorriso`, `ksvalidator`) |

CI scripts can branch on these precisely. Code 3 in particular tells
you the YAML is internally inconsistent in a way that isn't a typo —
the generator refused to produce an unsafe kickstart.

---

## 6. The override rule catalog

Twelve rules ship in v0.1. Each has its own file in
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

### 8.3 Embedded in a custom ISO (v0.1 limitation)

```bash
ks-gen iso \
  --src AlmaLinux-9-latest-x86_64-dvd.iso \
  --ks build/web01/ks.cfg \
  --tailoring build/web01/tailoring.xml \
  --out web01-installer.iso
```

At the Anaconda boot prompt:

- **BIOS:** press Tab on the highlighted entry, append
  `inst.ks=hd:LABEL=ALMA9:/ks.cfg`, press Enter.
- **UEFI:** press `e`, find the `linux` (or `linuxefi`) line, append
  `inst.ks=hd:LABEL=ALMA9:/ks.cfg`, press Ctrl-X.

v0.2 will rewrite the bootloader configs so the kickstarted entry
becomes the unattended default.

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

---

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

The four most common lint failures:

- **`missing: authorized_keys write in %post`** — Something stripped
  the admin user block. Either your `custom_post` overwrites it, or
  a hand-edit removed it. Regenerate.
- **`ordering: admin_user_and_keys must precede ssh_config_apply`** —
  Same root cause; topo sort would never produce this.
  Hand-edit removed the section markers, or the rule registry is
  bypassed.
- **`missing: %addon does not reference tailoring.xml`** — The addon
  block was edited. Regenerate.
- **`ksvalidator: ...`** — pykickstart's parser disagrees with the
  syntax. Almost always a malformed `%post` heredoc or stray
  character from a hand-edit.

If lint fails on a freshly-generated bundle (no hand edits), that's
a bug — please file it.

### "oscap remediation failed during install"

Check `/root/ks-post.log` (if you got far enough into `%post`) and
`/tmp/anaconda.log` on the install media or via VNC. The most
common remediation failures:

- A package was removed but oscap expected it to be present.
- A service was disabled but oscap's rule tried to enable it.
- The custom crypto policy hadn't been applied yet when oscap
  checked for FIPS mode.

The `%addon org_fedora_oscap` block runs *before* `%post`, so any
`crypto_policy` rule output in `%post` is too late to influence
oscap's view. Tailoring is the right channel for this — and ks-gen
handles it for the rules in its catalog. If you've added custom
oscap rules, you may need to add tailoring entries for them in
`exceptions[]`.

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
