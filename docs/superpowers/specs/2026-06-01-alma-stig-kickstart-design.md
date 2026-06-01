# Design: AlmaLinux 9 STIG Kickstart Generator (`ks-gen`)

**Status:** approved design, pre-implementation
**Date:** 2026-06-01
**Author:** Patrick Connallon (with Claude)

## 1. Motivation and goals

We need a Python CLI, `ks-gen`, that emits an AlmaLinux 9 kickstart configuration
which:

1. Applies every applicable DISA STIG control, primarily via the upstream
   `scap-security-guide` `stig` profile driven by the `oscap-anaconda-addon`.
2. Is **remote-safe by default** — a server installed from the generated
   kickstart on a cloud or headless host comes up reachable over SSH and stays
   reachable across reboots. No surprise lockouts.
3. Is **auditable** — every place the generator deviates from a literal STIG
   rule is recorded in a generated `exceptions.md` with the affected XCCDF rule
   IDs and the reason.
4. Is **reproducible** — the same input YAML always produces the same output
   bundle. CI re-renders, diffs, ships.

The central tension is that several STIG controls, applied literally, will lock
out the only admin on a remote box (full-disk LUKS that prompts at boot;
`pam_faillock` with `unlock_time=0`; firewalld enabled before the SSH port is
allowed; FIPS-only crypto that excludes modern client defaults). The generator
resolves these conflict points with a small, explicit override matrix — every
override is a named flag with a safe default, and every override is logged in
the exception report.

A second tension: DISA STIG language is DoD/USG-specific (the warning banner
literally claims "U.S. Government Information System"). For a private server
that text is incorrect and misleading. The generator substitutes
civilian-equivalent text that satisfies the *intent* of those controls (warn
unauthorized users; assert monitoring), and records the substitution as an
exception.

## 2. Architecture

```
┌────────────────────┐
│  CLI / subcommands │   typer: new, gen, iso, lint, rules, schema
└──────────┬─────────┘
           │
┌──────────▼─────────┐
│  Config layer      │   YAML → pydantic HostConfig (typed, strict)
│                    │   load → defaults → --set merge → validation
└──────────┬─────────┘
           │
┌──────────▼──────────────────────────┐
│  Rule registry                      │   discovers src/ks_gen/rules/*.py
│  for each Rule:                     │     applies(cfg)? → emit_tailoring,
│                                     │     emit_post, exception_entry
└──────────┬──────────────────────────┘
           │
┌──────────▼──────────┐  ┌────────────────────────────┐
│  Tailoring builder  │  │  Skeleton renderer         │
│  XCCDF XML fragment │  │  Jinja2 → static directives│
│  (TailoringOp list  │  │  + injects rule %post block│
│   → XML)            │  │                            │
└──────────┬──────────┘  └──────────┬─────────────────┘
           │                        │
           └──────────┬─────────────┘
                      │
        ┌─────────────▼──────────────┐
        │  Output writer             │
        │  ks.cfg, tailoring.xml,    │
        │  host.yaml, exceptions.md  │
        └─────────────┬──────────────┘
                      │
        ┌─────────────▼──────────────┐
        │  (optional) ISO builder    │   xorriso wrapper, rewrites
        │                            │   isolinux/grub for unattended boot
        └────────────────────────────┘
```

Four boundaries: config in, rules applied, output written, optional ISO
repackaging.

### 2.1 Hybrid STIG application

Most STIG rules (~400) are owned by `oscap` remediation via the
`%addon org_fedora_oscap` block. The generator does **not** reimplement those.
The generator owns only the named *conflict points* between STIG and
remote-safety, plus DoD-content neutralization — roughly 12 rules in v1.

Each rule has two channels:

- **Tailoring channel:** XCCDF fragments merged into a per-host `tailoring.xml`.
  This runs *before* oscap remediation and prevents oscap from doing things
  (`disable` an XCCDF rule, `set_value` for a variable).
- **Post channel:** shell injected into `%post` after oscap remediation. Used
  to add things oscap doesn't (admin authorized_keys, civilian banner) or
  re-assert values oscap may have over-tightened.

Execution timeline inside Anaconda:

```
%packages → %addon org_fedora_oscap [reads tailoring.xml, remediates] → %post → reboot
```

**Tailoring delivery.** `oscap-anaconda-addon` reads `tailoring.xml` from
a local installer-FS path (`/tailoring.xml`), not a URL. A static `%pre`
block emitted into every `ks.cfg` is responsible for staging the file at
that path before `%addon` runs — `curl`-ing from the same base URL when
the kickstart was served over `http(s)://`, or `cp`-ing it from
`/run/install/repo` when delivered via `hd:LABEL=` (the `ks-gen iso`
path). See `docs/superpowers/specs/2026-06-01-tailoring-pre-fetcher-design.md`
for the full design.

### 2.2 External tool dependencies

**Generated `ks.cfg` references:**

- `scap-security-guide` package (installed by `%packages`).
- `oscap-anaconda-addon` package.

**Generator host runtime:**

- Python 3.11+ with `typer`, `pydantic>=2`, `jinja2`, `pyyaml`, `pykickstart`.
- `xorriso` only for the `iso` subcommand.

## 3. Data model

A `host.yaml` is the single source of truth. Produced by `ks-gen new`
interactively, then re-rendered by `ks-gen gen`. Strictly validated by
pydantic at load time; unknown keys are errors. CLI `--set KEY=VALUE`
applies dotted-path overrides on top of the YAML before validation.

### 3.1 Canonical example

```yaml
meta:
  release: "9"
  profile: stig
  scap_content: ssg-almalinux9-ds.xml

system:
  hostname: web01.example.com
  timezone: UTC
  locale: en_US.UTF-8
  keyboard: us

network:
  interfaces:
    - device: link
      bootproto: dhcp
      onboot: true
  dns_search: []
  hostname_from_dhcp: false

disk:
  preset: stig_server          # stig_server | minimal | custom
  wipe: true
  bootloader_password: null    # null = generate random and print to console

user:
  admin:
    name: opsadmin
    gecos: "Ops Admin"
    groups: [wheel]
    shell: /bin/bash
    password: null             # null = key-only login
    sudo: nopasswd_no
    authorized_keys:
      - "ssh-ed25519 AAAA... opsadmin@laptop"

ssh:
  port: 22
  permit_root_login: "no"
  password_authentication: false
  client_alive_interval: 600
  client_alive_count_max: 1
  max_auth_tries: 4
  use_pam: true

banner:
  text: |
    WARNING: This is a private computer system. Unauthorized access is
    prohibited. All activity on this system may be monitored and logged.
    Use of this system constitutes consent to such monitoring.
  apply_to: [issue, issue_net, motd, gdm]

time:
  servers: [pool.ntp.org]
  chrony_makestep_threshold: 1.0

crypto:
  policy: MODERN               # STIG | MODERN | FUTURE

packages:
  base_groups: ["@^minimal-environment", "@standard"]
  required:
    - scap-security-guide
    - openscap-scanner
    - oscap-anaconda-addon
    - aide
    - audit
    - rsyslog
    - chrony
    - firewalld
    - sudo
  extra: []
  excluded:
    - telnet-server
    - rsh-server
    - tftp-server
    - vsftpd
    - ypserv

overrides:
  fips_mode: false
  faillock:
    enable: true
    deny: 3
    unlock_time: 900
    even_deny_root: false
  auditd:
    disk_full_action: SUSPEND
    disk_error_action: SUSPEND
    max_log_file_action: ROTATE
  ssh_keep_open:
    ensure_firewalld_port: true
    ensure_selinux_port: true
  usbguard:
    enable: false
  kernel_module_blacklist:
    enable: true
    modules: [usb-storage, cramfs, freevxfs, jffs2, hfs, hfsplus, squashfs, udf]
  package_purge:
    enable: true
  dod_root_ca:
    install: false

custom_post:
  - |
    # User additions go here; runs after all override rules.

exceptions:
  - id: no-luks
    reason: "Cloud provider encrypts volumes; remote unattended reboot required."
    stig_rules_disabled:
      - xccdf_org.ssgproject.content_rule_encrypt_partitions
```

### 3.2 Crypto policy semantics

| `crypto.policy` | System crypto-policy | FIPS kernel mode | Ed25519/X25519/ChaCha20 |
|---|---|---|---|
| `STIG`   | `FIPS`    | `fips=1` on cmdline | blocked (kernel-level) |
| `MODERN` | `DEFAULT` | off                 | allowed |
| `FUTURE` | `FUTURE`  | off                 | allowed |

Hard constraint enforced by config validation: `crypto.policy in {MODERN,
FUTURE}` with `overrides.fips_mode: true` is rejected at config-load time
(exit code 3) with an error naming both fields, because FIPS kernel mode
blocks Curve25519 below the application layer.

### 3.3 Disk layout

V1 ships three presets. `stig_server` is the default:

| Mount | Size | Mount options |
|---|---|---|
| `/boot/efi` | 1 GiB vfat | — |
| `/boot` | 1 GiB xfs | `nodev`, `nosuid` |
| `/` (LVM) | 15 GiB xfs | — |
| `/home` (LVM) | 5 GiB xfs | `nodev`, `nosuid` |
| `/tmp` (LVM) | 3 GiB xfs | `nodev`, `nosuid`, `noexec` |
| `/var` (LVM) | 10 GiB xfs | `nodev` |
| `/var/log` (LVM) | 5 GiB xfs | `nodev`, `nosuid`, `noexec` |
| `/var/log/audit` (LVM) | 3 GiB xfs | `nodev`, `nosuid`, `noexec` |
| `/var/tmp` (LVM) | 2 GiB xfs | `nodev`, `nosuid`, `noexec` |
| `swap` (LVM) | min(RAM, 4 GiB) | — |

No LUKS in any preset (per the no-LUKS exception). `minimal` collapses
non-required mounts into `/`. `custom` reads a `layout:` block enumerating
partitions, LVs, and mount options explicitly.

### 3.4 Two cross-field validation rules carried by tests

```python
def test_modern_crypto_with_fips_mode_rejected(): ...
def test_password_null_requires_authorized_keys(): ...
```

These are the two failures most likely to silently produce an unusable install
and are guarded both by `config.py` validators and by `test_schema.py`.

## 4. Rule contract and catalog

### 4.1 Contract

```python
class Rule(Protocol):
    id: str                          # stable, e.g. "faillock_safety"
    summary: str                     # one line, surfaces in exceptions.md
    depends_on: list[str]            # rule ids that must run before this one
    stig_rules_affected: list[str]   # XCCDF IDs this rule overrides/tailors

    def applies(self, cfg: HostConfig) -> bool: ...
    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]: ...
    def emit_post(self, cfg: HostConfig) -> str: ...
    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None: ...
```

`TailoringOp` is a typed dataclass: `{rule_id, action: "disable"|"select"|"set_value", value?}`.
Rules never emit raw XML; `tailoring.py` is the only thing that serializes XCCDF.

`exception_entry` returns `None` when a rule only re-asserts a STIG-default-equivalent value.
When a rule disables an oscap rule, `exception_entry` must return a non-None entry.

### 4.2 Discovery and ordering

Filesystem-based: `src/ks_gen/rules/*.py` each define a module-level `RULE =
Rule(...)`. The registry imports them all at startup. No decorators, no
entry-point plugins.

Ordering inside `%post` is a topological sort over `depends_on`.

### 4.3 Load-bearing safety invariants

Three properties get their own test file (`tests/test_topo_sort.py`) because
they are the safety claims of the tool:

1. **Lockout-resistance.** For every shipped scenario and every fuzz-generated
   override permutation, the admin `authorized_keys` write occurs earlier in
   `%post` than any `systemctl ... sshd` line.
2. **Firewall sequencing.** No scenario enables firewalld before `ssh.port` is
   added to it.
3. **No silent compliance drift.** Any rule whose `emit_tailoring` includes a
   `disable` op must return a non-None `exception_entry` naming that XCCDF rule.

A test-suite failure on any of these is a P0 — never updated by changing the
test.

### 4.4 V1 catalog

**Remote-safe critical** (not optional)

| Rule | Channel | Purpose |
|---|---|---|
| `admin_user_and_keys` | post | Create wheel admin, drop authorized_keys, sudoers fragment. Runs first. |
| `ssh_keep_open` | post | `semanage port -a -t ssh_port_t -p tcp <port>`; `firewall-offline-cmd --add-port=<port>/tcp`. Runs before any service mgmt. |
| `faillock_safety` | tailor + post | `unlock_time=900`, `even_deny_root=false`. |
| `crypto_policy` | tailor + post | `update-crypto-policies --set {STIG|DEFAULT|FUTURE}`. When not STIG: tailoring disables `enable_fips_mode`, `sshd_use_approved_{ciphers,kex,macs,mac_ordered}`; post generates Ed25519 host keys if missing. |
| `ssh_config_apply` | post | Writes `/etc/ssh/sshd_config.d/00-ks-gen.conf` with `Port`, `PermitRootLogin`, `PasswordAuthentication`, `ClientAliveInterval`, then `systemctl reload sshd`. Hard dep on `admin_user_and_keys` and `ssh_keep_open`. |

**DoD-content neutralization**

| Rule | Channel | Purpose |
|---|---|---|
| `banner_text` | tailor + post | Tailoring disables banner-content rules; post writes civilian text to `/etc/issue`, `/etc/issue.net`, `/etc/motd`, and the GDM banner file if present. |
| `time_servers` | tailor + post | Tailoring disables the rule hardcoding USNO time servers; post writes `/etc/chrony.conf` from `time.servers`. |
| `dod_root_ca` | tailor | When `overrides.dod_root_ca.install: false`, disables the rule that mandates the DoD root CA bundle. |

**Environment knobs**

| Rule | Channel | Purpose |
|---|---|---|
| `auditd_actions` | tailor + post | Tailoring sets `var_auditd_disk_full_action` etc. to `SUSPEND`/`ROTATE`; post re-asserts on `/etc/audit/auditd.conf`. |
| `usbguard` | tailor + post | When `false`: tailoring disables `package_usbguard_installed`, `service_usbguard_enabled`. When `true`: opposite. |
| `kernel_module_blacklist` | post | Writes `/etc/modprobe.d/ks-gen-blacklist.conf` from configured module list. |
| `package_purge` | post | `dnf -y remove <packages.excluded>` after install (catches transitive pulls). |

### 4.5 Not a rule — covered by oscap

SELinux enforcing, AIDE install + initial db build, login.defs UMASK/PASS_MAX_DAYS,
sudo `!rootpw` + `requiretty`, `/etc/issue` *permissions*, audit rules content
(80+ `auditctl` rules), firewalld *enabled*, chronyd *enabled*. If a STIG
release moves any of these into conflict territory, it graduates into a new
rule file.

## 5. CLI surface

Built on `typer`. Five subcommands; each does one thing.

### 5.1 `ks-gen new`

Interactive wizard. Walks `host.yaml` schema with safe defaults pre-filled.
Validates inline — pasted SSH key must parse, hostname must be a valid DNS
label, admin name can't be `root`. Writes:

```
out/<hostname>/
  host.yaml          # canonical config, re-runnable
  ks.cfg             # the kickstart
  tailoring.xml      # XCCDF tailoring referenced by %addon
  exceptions.md      # audit report
```

Flags:

- `--out DIR` overrides output directory.
- `--non-interactive` makes any unanswered question a hard error.

### 5.2 `ks-gen gen`

Non-interactive re-render from an existing `host.yaml`. The CI/change-control
path.

```bash
ks-gen gen --config host.yaml --out out/web01/
ks-gen gen --config host.yaml \
  --set ssh.port=2222 \
  --set overrides.fips_mode=true \
  --out out/web01-fips/
```

`--set KEY=VALUE` (repeatable) applies dotted-path overrides on top of the
YAML before validation. CLI overrides are recorded in `exceptions.md` as
`applied via --set`.

### 5.3 `ks-gen iso`

Thin `xorriso` wrapper that repackages the AlmaLinux DVD ISO into a
self-installing image.

```bash
ks-gen iso \
  --src AlmaLinux-9-latest-x86_64-dvd.iso \
  --ks  out/web01/ks.cfg \
  --tailoring out/web01/tailoring.xml \
  --out web01-installer.iso
```

Steps:

1. Extract source ISO contents.
2. Inject `/ks.cfg` and `/tailoring.xml` at ISO root.
3. Rewrite `isolinux/isolinux.cfg` (BIOS) and `EFI/BOOT/grub.cfg` (UEFI) so
   the default boot entry appends `inst.ks=hd:LABEL=<volid>:/ks.cfg
   inst.stage2=hd:LABEL=<volid>` and timeout becomes 5s.
4. Rebuild as a hybrid BIOS+UEFI bootable ISO.

Flags:

- `--volid LABEL` overrides auto-detected ISO label.
- `--no-default` keeps the original "Test this media & install" entry as
  default and adds the kickstarted entry as a second option.

Refuses to run if `xorriso` isn't on PATH; tells you the package name.

### 5.4 `ks-gen lint`

Two-stage validation:

1. `pykickstart` `ksvalidator` — structural grammar.
2. Internal pass — re-parses `%post` and re-asserts the Section 4.3
   invariants on a stored `ks.cfg`.

Runs automatically at the end of `new` and `gen`.

### 5.5 `ks-gen rules`

Lists the shipped rule catalog. Useful for audit and "did this version add a
rule?" diffs.

```bash
ks-gen rules                  # table
ks-gen rules --id crypto_policy  # detailed view
ks-gen rules --format json    # for tooling
```

### 5.6 `ks-gen schema`

Emits the JSON Schema for `host.yaml` to stdout for editor integration:

```yaml
# yaml-language-server: $schema=./host.schema.json
```

### 5.7 Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | usage error |
| 2 | config validation error |
| 3 | rule conflict (e.g. `crypto.policy=MODERN` + `fips_mode=true`) |
| 4 | lint failure |
| 5 | external tool missing (`xorriso`, `ksvalidator`) |

## 6. Testing

Strategy: static lint + unit tests + golden snapshots. No VM install in CI.
The bet: if every rule is unit-tested, the topo-sort invariants are enforced,
`ksvalidator` accepts the output, and representative full configs match
golden snapshots, regressions land as code-level failures long before they
reach an actual install.

### 6.1 Tooling

`pytest` + `syrupy` (snapshots) + `pykickstart` + `ruff` + `mypy --strict`
on `src/ks_gen/`. CLI tests use typer's `CliRunner`.

### 6.2 Per-rule tests

Each rule file gets one test file covering five cases minimum:

1. `applies()` returns true on a config that should trigger it.
2. `applies()` returns false on a config that shouldn't.
3. `emit_tailoring()` produces the expected `TailoringOp` list.
4. `emit_post()` output passes `bash -n` (syntactic shell check, no execution).
5. `emit_post()` is idempotent — running it twice changes nothing the second time.

### 6.3 Golden scenarios

| Scenario | Highlights |
|---|---|
| `minimal-dhcp` | All defaults, DHCP, MODERN crypto, no LUKS — happy path cloud install |
| `stig-strict` | `crypto.policy=STIG`, `fips_mode=true`, USBGuard on, password auth off, faillock at STIG defaults |
| `modern-crypto` | Demonstrates MODERN crypto with the tailored crypto rules visible in `exceptions.md` |
| `bare-metal-usbguard` | Static IP, USBGuard enabled, custom SSH port 2222 |

Snapshots committed. Updating a snapshot is a code-review event. A rendered
output normalizer (strips trailing whitespace, collapses blank-line runs)
prevents drift from unrelated formatting.

### 6.4 Invariant tests

Three parametrized fixtures iterate over the four golden scenarios plus ~100
fuzz-generated configs (toggling every boolean in the override matrix):

```python
def test_authorized_keys_always_before_sshd_restart(every_scenario): ...
def test_ssh_port_opened_in_firewalld_before_firewalld_enable(every_scenario): ...
def test_no_rule_disables_an_oscap_rule_without_exceptions_entry(every_scenario): ...
```

### 6.5 Out of scope for v1

- No actual install. No QEMU, no `virt-install`, no Anaconda run in CI.
- No live oscap scan in CI.
- No network round-trip in `iso` tests — `xorriso` mocked at `subprocess.run`.

Before each release the four golden scenarios get built into ISOs and
installed by hand into a libvirt VM, SSH'd into, and scanned with
`oscap xccdf eval --profile stig`. Result lives in a release note.

A future `ks-gen verify --host <ip>` subcommand can automate this — easy to
add later because the test fixtures already exist.

### 6.6 CI

GitHub Actions, single workflow: `ruff` → `mypy` → `pytest`. Matrix on
Python 3.11 / 3.12 / 3.13. Target wall-clock: under 30 seconds.

## 7. Repository layout

```
alma-linux-security/
├── pyproject.toml
├── README.md
├── LICENSE                           # Apache-2.0
├── CHANGELOG.md
├── .gitignore                        # excludes *.iso, out/, dist/, etc.
├── .github/workflows/ci.yml
├── docs/superpowers/specs/
│   └── 2026-06-01-alma-stig-kickstart-design.md   # this document
├── src/ks_gen/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── wizard.py
│   ├── config.py
│   ├── registry.py
│   ├── topo.py
│   ├── tailoring.py
│   ├── skeleton.py
│   ├── writer.py
│   ├── iso.py
│   ├── lint.py
│   ├── exceptions_report.py
│   ├── templates/
│   │   ├── ks.cfg.j2
│   │   └── partials/
│   └── rules/
│       ├── __init__.py
│       ├── admin_user_and_keys.py
│       ├── ssh_keep_open.py
│       ├── ssh_config_apply.py
│       ├── faillock_safety.py
│       ├── crypto_policy.py
│       ├── banner_text.py
│       ├── time_servers.py
│       ├── dod_root_ca.py
│       ├── auditd_actions.py
│       ├── usbguard.py
│       ├── kernel_module_blacklist.py
│       └── package_purge.py
└── tests/
    ├── test_schema.py
    ├── test_topo_sort.py
    ├── test_tailoring_builder.py
    ├── test_cli/
    │   ├── test_new.py
    │   ├── test_gen.py
    │   ├── test_iso.py
    │   ├── test_lint.py
    │   └── test_rules.py
    ├── rules/
    │   └── test_<each_rule>.py
    └── golden/
        ├── minimal-dhcp.host.yaml
        ├── minimal-dhcp.ks.cfg
        ├── minimal-dhcp.tailoring.xml
        ├── minimal-dhcp.exceptions.md
        ├── stig-strict.{host.yaml,ks.cfg,tailoring.xml,exceptions.md}
        ├── modern-crypto.{host.yaml,ks.cfg,tailoring.xml,exceptions.md}
        └── bare-metal-usbguard.{host.yaml,ks.cfg,tailoring.xml,exceptions.md}
```

### 7.1 Packaging

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "ks-gen"
version = "0.1.0"
requires-python = ">=3.11"
license = { file = "LICENSE" }
dependencies = [
  "typer>=0.12",
  "pydantic>=2.6",
  "jinja2>=3.1",
  "pyyaml>=6.0",
  "pykickstart>=3.52",
]

[project.optional-dependencies]
dev = ["pytest>=8", "syrupy>=4", "ruff>=0.5", "mypy>=1.10"]

[project.scripts]
ks-gen = "ks_gen.cli:app"
```

### 7.2 Install paths

1. `pipx install ks-gen` — default.
2. `pip install ks-gen` in a venv — for repo work.
3. `python -m ks_gen ...` — from a checked-out tree.

### 7.3 License

Apache-2.0. The patent grant matters for cryptography-relevant defaults.

### 7.4 Out of scope for v1

- PyPI publication. Distribution is "clone, install, use" until the rule
  catalog has stabilized through one STIG release cycle.
- Docker image.
- `setup.cfg`, `requirements*.txt`. `pyproject.toml` is the single source of
  truth.

## 8. Deferred for later versions

- `ks-gen verify --host <ip>` — SSH into an installed box, run oscap, diff
  against the host's `exceptions.md`. Closes the loop on "did we actually
  ship a compliant box?"
- Multiple AlmaLinux releases (10.x). v1 targets AlmaLinux 9 only.
- LUKS presets — `partial` (LUKS on /var, /var/log, /var/tmp, /home, /tmp),
  `tang` (Clevis network-bound disk encryption). Deferred because the user
  declared no-LUKS as an accepted-risk exception in v1.
- `ks-gen verify-tailoring` — a separate lint pass that validates
  `tailoring.xml` against the upstream XCCDF schema with `xmllint`. Useful;
  not blocking for v1.
