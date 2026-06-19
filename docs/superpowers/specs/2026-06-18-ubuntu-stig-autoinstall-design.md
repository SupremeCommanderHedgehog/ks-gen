# Design: Ubuntu 24.04 LTS STIG Autoinstall (`ks-gen` distro extension)

**Status:** approved design, pre-implementation
**Date:** 2026-06-18
**Author:** Patrick Connallon (with Claude)
**Tracking issue:** #81

## 1. Motivation and goals

Extend `ks-gen` so it can produce installer artifacts for **Ubuntu 24.04 LTS Subiquity autoinstall** targets, applying the DISA Canonical Ubuntu 24.04 LTS STIG (v1r5, 2026-05-05) with the same remote-safe / civilian-substitution exception model the AlmaLinux 9 path already uses.

End state: an operator writes `distro: ubuntu2404` in `host.yaml` and `ks-gen gen` produces an autoinstall seed (`user-data` + `meta-data`) plus a parallel `tailoring.xml` and `exceptions.md` keyed by Ubuntu XCCDF rule IDs. Existing alma9 users see no breaking change — the absent `distro:` field defaults to `alma9`.

The central tension is the same as the alma9 path: several Ubuntu STIG controls applied literally will lock out the only admin on a remote box, or pull in DoD-specific assets a private operator can't satisfy. The same small, audited override matrix that the alma9 rules implement is preserved on the Ubuntu side — same operator-visible knobs, equivalent Ubuntu XCCDF rules disabled, same `exceptions.md` audit trail.

A non-goal is rule-by-rule duplication of the AlmaLinux 9 design spec (`2026-06-01-alma-stig-kickstart-design.md`). That document is the source of truth for the rule *intent*; this spec covers the delta needed to apply that intent on Ubuntu without disturbing the alma9 path.

## 2. Architecture

The current four-stage pipeline (config → rules → tailoring + skeleton → writer) is preserved. One new dimension — `distro` — flows through every stage.

```
host.yaml (with distro: alma9 | ubuntu2404)
      │
      ▼
config.py — HostConfig stays single, gains `distro` discriminator;
            post-validators reject distro-incompatible field
            combinations (e.g., firewalld zones only with distro=alma9)
      │
      ▼
registry.load_rules(distro) — loads rules/<distro>/*.py only;
            each rule imports its shared id/summary/exception_text
            from rules/_meta/<rule_id>.py so auditor English never drifts
      │
      ▼
writer.build_bundle(cfg) — distro-aware dispatch:
   alma9      → ks.cfg + tailoring.xml + host.yaml + exceptions.md
   ubuntu2404 → user-data + meta-data + tailoring.xml + host.yaml + exceptions.md
```

Four invariants stay intact across distros:

1. Same operator-facing config shape (`host.yaml`).
2. Same Rule Protocol (`applies` / `emit_tailoring` / `emit_post` / `emit_packages` / `exception_entry`).
3. Same `tailoring.xml` XCCDF shape; different rule IDs inside.
4. Same `exceptions.md` markdown shape; different rule IDs inside.

The four boundaries from the alma9 spec — config in, rules applied, output written, optional ISO repackaging — are preserved. The "ISO repackaging" boundary becomes "HTTP-served seed" for ubuntu2404 first ship (see §8).

## 3. Schema delta in `config.py` / `host.yaml`

### 3.1 New top-level field

```python
class HostConfig(BaseModel):
    distro: Literal["alma9", "ubuntu2404"] = "alma9"
    meta: Meta
    system: System
    ...
```

Absent `distro:` defaults to `alma9` — zero migration for existing configs.

### 3.2 Distro-aware semantics on existing fields

These fields keep their operator-facing names and values; their *implementation* changes per distro:

| Field | alma9 semantics | ubuntu2404 semantics |
|---|---|---|
| `meta.scap_content` | `ssg-almalinux9-ds.xml` (default) | `ssg-ubuntu2404-ds.xml` (default) |
| `crypto.policy: STIG \| MODERN \| FUTURE` | `update-crypto-policies --set <POLICY>` | `/etc/ssl/openssl.cnf` `[default_sect].MinProtocol` + sshd_config `KexAlgorithms`/`Ciphers`/`MACs` |
| `packages.preset: minimal \| lean \| standard` | dnf groups + RHEL package names | apt package set + Ubuntu names (no tasksel server-bundles in `lean`) |
| `unattended_updates.*` | `dnf-automatic` config | `unattended-upgrades` + `apt.conf.d/20auto-upgrades` config |
| `kernel_module_blacklist.modules` | `/etc/modprobe.d/ks-gen-blacklist.conf` | same path, same format |
| `disk.preset: stig_server \| minimal \| custom` | parted layout + LVM | parted layout + LVM (same layout, different default mount-option keywords on a couple of filesystems) |

Default `meta.scap_content` is computed from `distro`; explicit override is post-validated to match the distro family (e.g., setting `scap_content: ssg-almalinux9-ds.xml` when `distro: ubuntu2404` is a validation error).

### 3.3 Distro-incompatible fields (post-validator rejections)

These combinations raise `ValidationError` at config-load time with explicit messages naming both the field and the offending `distro`:

| Field | Allowed when |
|---|---|
| `container_host.*` | `distro == "alma9"` (first ship — see #88) |
| `container_host.firewalld_zone` | `distro == "alma9"` |
| `unattended_updates.dnf_automatic_*` | `distro == "alma9"` |
| `unattended_updates.apt_periodic_*` | `distro == "ubuntu2404"` |
| `disk.luks` | both (no change) |
| `overrides.ssh_keep_open.ensure_selinux_port` | `distro == "alma9"` (no SELinux on ubuntu) |
| `overrides.ssh_keep_open.ensure_firewalld_port` | `distro == "alma9"` (no firewalld on ubuntu) |
| `overrides.ssh_keep_open.ensure_ufw_port` | `distro == "ubuntu2404"` (no ufw on alma) |

Validator error format: `"<field>: not supported on distro=<distro>; this field is only valid when distro=<allowed>"`. No silent ignore — the operator either fixes the YAML or explicitly switches `distro`.

### 3.4 New fields

Ubuntu introduces one new override namespace:

```yaml
overrides:
  ssh_keep_open:
    ensure_ufw_port: true   # ubuntu2404; defaults to true if cfg.distro == "ubuntu2404"
```

`ensure_ufw_port` replaces `ensure_firewalld_port` semantically on ubuntu2404 (firewalld doesn't exist there). A post-validator wires up the default based on `distro`.

## 4. Rule system

### 4.1 New directory layout

```
src/ks_gen/rules/
├── __init__.py
├── _types.py                    # Rule Protocol — UNCHANGED
├── _meta/                        # NEW: shared per-rule metadata
│   ├── __init__.py
│   ├── ssh_keep_open.py         #   id, summary, depends_on, exception_text
│   ├── banner_text.py
│   └── ...                      #   (one per rule)
├── alma9/                        # NEW dir; existing 15 rules move here
│   ├── __init__.py
│   ├── ssh_keep_open.py
│   ├── banner_text.py
│   └── ...
└── ubuntu2404/                   # NEW dir; greenfield Ubuntu rules
    ├── __init__.py
    ├── ssh_keep_open.py
    ├── banner_text.py
    └── ...
```

### 4.2 Shared metadata pattern

Each rule's distro-agnostic identity lives in `rules/_meta/<rule_id>.py`:

```python
# rules/_meta/ssh_keep_open.py
ID = "ssh_keep_open"
SUMMARY = "Ensure ssh.port reachable before sshd starts."
DEPENDS_ON: list[str] = []
EXCEPTION_REASON = (
    "Default firewall drops would otherwise block first-boot SSH on a remote install."
)
```

Both distro implementations import from `_meta`:

```python
# rules/alma9/ssh_keep_open.py
from ks_gen.rules._meta import ssh_keep_open as meta

@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=lambda: [
        "xccdf_org.ssgproject.content_rule_<alma9-rule-id>",
        ...
    ])
    def emit_post(self, cfg): ...  # uses semanage + firewall-offline-cmd

# rules/ubuntu2404/ssh_keep_open.py
from ks_gen.rules._meta import ssh_keep_open as meta

@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=lambda: [
        "xccdf_org.ssgproject.content_rule_<ubuntu2404-rule-id>",
        ...
    ])
    def emit_post(self, cfg): ...  # uses ufw
```

The exception text (auditor-facing English) and the rule's identity (`id`, `summary`) cannot drift between distros because they're literally the same Python module.

### 4.3 Registry change

`registry.load_rules` gains a `distro` argument:

```python
def load_rules(distro: str) -> list[Rule]:
    pkg_path = f"ks_gen.rules.{distro}"
    # discover and import all *.py under pkg_path
    # each module exports `RULE: Rule`
    return [...]
```

Caller (`writer.build_bundle`) passes `cfg.distro`. The Rule Protocol itself is unchanged; the discovery just narrows.

### 4.4 Migration of existing rules

The 15 current `src/ks_gen/rules/*.py` files (except `_types.py` and `__init__.py`) move into `rules/alma9/`. The `id`, `summary`, and `EXCEPTION_REASON`-equivalent strings get factored into `rules/_meta/<rule_id>.py`; each existing rule imports them. Behavior change: none. Golden snapshots: unchanged (the shared module's constants resolve to the same strings).

### 4.5 Rule Protocol unchanged

```python
class Rule(Protocol):
    id: str
    summary: str
    depends_on: list[str]
    stig_rules_affected: list[str]

    def applies(self, cfg: HostConfig) -> bool: ...
    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]: ...
    def emit_post(self, cfg: HostConfig) -> str: ...      # bash, same as today
    def emit_packages(self, cfg: HostConfig) -> list[str]: ...
    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None: ...
```

`emit_post` returns a bash string in both distros. The writer wraps it differently per distro (§5.2).

## 5. Writer and builder

### 5.1 `Bundle` dataclass reshape

```python
@dataclass(frozen=True)
class Bundle:
    distro: Literal["alma9", "ubuntu2404"]
    tailoring_xml: str          # shared shape, different rule IDs inside
    host_yaml: str              # shared
    exceptions_md: str          # shared shape, different rule IDs inside

    # distro-specific payload (exactly one set populated):
    ks_cfg: str | None = None              # alma9
    user_data: str | None = None           # ubuntu2404
    meta_data: str | None = None           # ubuntu2404
```

Constructor invariants enforced at build time: `alma9` bundles have `ks_cfg is not None` and `user_data is None`; `ubuntu2404` bundles invert it.

### 5.2 `build_bundle` dispatch and `late-commands` wrapping

`build_bundle(cfg)` dispatches on `cfg.distro`. For ubuntu2404, each rule's `emit_post(cfg)` bash body gets wrapped into one `late-commands:` entry:

```yaml
late-commands:
  - curtin in-target --target=/target -- bash -c |
      # rule:ssh_keep_open
      ufw allow 22/tcp
  - curtin in-target --target=/target -- bash -c |
      # rule:banner_text
      cat > /etc/issue <<'BANNER'
      WARNING: This is a private computer system. ...
      BANNER
  - ...
```

`curtin in-target` chroots into the installed target (`/target` is the canonical Subiquity install-root path), giving the rule's bash a normal `/etc`, `/usr/bin/systemctl`, etc. — the same operating model as kickstart `%post --chroot`. The per-rule comment header (`# rule:<id>`) preserves the audit trail that kickstart gets from `PostBlock(rule_id=...)`.

For rules whose Ubuntu equivalent doesn't fit a single bash one-liner (e.g., `crypto_policy` editing multiple files), `emit_post` returns a multi-line bash heredoc and the writer wraps it in a single `late-commands` entry per rule. This preserves rule isolation for the audit trail.

### 5.3 `write_bundle` file layout

For ubuntu2404:

```
out/
├── user-data         # autoinstall + cloud-init payload (YAML)
├── meta-data         # cloud-init instance-id, hostname
├── tailoring.xml     # XCCDF tailoring for ssg-ubuntu2404-ds.xml
├── exceptions.md     # auditor report
└── host.yaml         # echoed input
```

The `user-data` is YAML with top-level keys `#cloud-config` (header), `autoinstall:` (Subiquity), and `late-commands:` (post). The `meta-data` is YAML with `instance-id` and `local-hostname`.

### 5.4 Tailoring across distros

`build_tailoring_xml` is unchanged — it builds an XCCDF tailoring document from a list of `TailoringOp`. The profile ID is computed from `cfg.meta.profile`:

```python
profile_id = f"xccdf_org.ssgproject.content_profile_{cfg.meta.profile}"
```

This works for both `ssg-almalinux9-ds.xml` and `ssg-ubuntu2404-ds.xml` (same XCCDF profile-naming convention). The contents of the tailoring (which XCCDF rule IDs to disable, which set_value entries to apply) come from `Rule.emit_tailoring`, which is distro-specific.

## 6. Ubuntu rule sketches

One-paragraph approach per rule; full implementation lives in the child issues from §11.

| Rule | Ubuntu approach |
|---|---|
| `admin_user_and_keys` | Use autoinstall `identity:` (username, hostname) + cloud-init `users:` (authorized_keys, sudo). No late-command; cloud-init handles user creation natively. `emit_post` returns empty; rule output lives in skeleton/autoinstall YAML. |
| `ssh_keep_open` | `ufw allow <port>/tcp` (no SELinux analog needed; AppArmor doesn't gate ports). `emit_packages` ensures `ufw` is installed. |
| `ssh_config_apply` | Drop-in at `/etc/ssh/sshd_config.d/10-ks-gen.conf`; tailoring disables Ubuntu STIG sshd rules ks-gen overrides (banner, ClientAlive*, MaxAuthTries, etc.). |
| `banner_text` | Write `/etc/issue`, `/etc/issue.net`, `/etc/ssh/sshd-banner`; sshd_config drop-in sets `Banner`; tailoring disables Ubuntu STIG DoD-text rules. |
| `dod_root_ca` | No-op by default (same as alma); tailoring disables Ubuntu STIG DoD-PKI rules. |
| `time_servers` | Edit `/etc/chrony/chrony.conf`; `emit_packages` pins `chrony`. Tailoring disables strict DoD-NTP-source rule. |
| `crypto_policy` | Per `crypto.policy` value: edit `/etc/ssl/openssl.cnf` `[default_sect]` (`activate = 1`, `MinProtocol`), edit sshd `KexAlgorithms`/`Ciphers`/`MACs`. Tailoring disables overlapping STIG rules. |
| `faillock_safety` | Configure `/etc/security/faillock.conf` (Ubuntu 24.04 uses `pam_faillock`) with `deny`/`unlock_time` matching alma's safety margin. |
| `unattended_updates` | Configure `/etc/apt/apt.conf.d/50unattended-upgrades` + `/etc/apt/apt.conf.d/20auto-upgrades`; `emit_packages` pins `unattended-upgrades`. |
| `kernel_module_blacklist` | Write `/etc/modprobe.d/ks-gen-blacklist.conf` (path is shared with alma; Ubuntu runs `update-initramfs -u` instead of `dracut`). |
| `package_purge` | `apt-get purge -y <names>` in a late-command; package-name list in `_meta` carries a distro-mapping table. |
| `usbguard` | `apt install usbguard` + drop-in policy file; tailoring disables overlapping rules. |
| `auditd_actions` | Edit `/etc/audit/auditd.conf` (path shared); `emit_packages` pins `auditd`. |
| `container_host` | **Alma9-only first ship.** Post-validator rejects `container_host.*` on `distro: ubuntu2404`. Ubuntu implementation tracked in #88. |
| `data_disks_preserve` | Ports cleanly — partition-level (parted). Only differences are in `disk.preset` package selection. |

## 7. HTTP-seed delivery

### 7.1 Bundle file layout

For `cfg.distro == "ubuntu2404"`, `ks-gen gen` writes:

```
out/
├── user-data         # autoinstall + cloud-init payload
├── meta-data         # cloud-init instance-id, hostname
├── tailoring.xml
├── exceptions.md
└── host.yaml
```

### 7.2 Operator workflow

1. `ks-gen gen --config host.yaml --out out/`
2. Serve `out/` over HTTP from any reachable host:
   ```
   python3 -m http.server 8000 --directory out/
   ```
3. Boot the stock Ubuntu 24.04 LTS Server ISO. At the GRUB menu, press `e` and append to the kernel line:
   ```
   autoinstall ds=nocloud-net;s=http://<ip>:8000/
   ```
   Boot.
4. The installer fetches `user-data` + `meta-data`, runs the autoinstall (Subiquity), executes `late-commands`, reboots into a STIG-hardened host.

### 7.3 Limitation versus the Alma flow

The boot-cmdline edit is the only operator action that has no parallel in Alma's `ks-gen iso` flow. Ubuntu Server ISO has a default GRUB entry; the autoinstall boot args must be appended once. The README will document this; full ISO repack (which would bake the boot args in) is tracked as a deferred child issue (#87).

## 8. Verify (`verify/*`)

The reconcile algorithm is portable across distros; the data it operates on is not. Audit plan:

| Module | Change |
|---|---|
| `verify/arf.py` | None expected. ARF parsing is format-driven. |
| `verify/baseline.py` | **Distro-aware.** Read `host.yaml.distro` from the bundle dir; pick `ssg-ubuntu2404-ds.xml` vs `ssg-almalinux9-ds.xml`. Pin Ubuntu datastream version in CI (SSG 0.1.78+). |
| `verify/reconcile.py` | Audit for hard-coded `xccdf_org.ssgproject.content_rule_` prefix assumptions (expected safe — same XCCDF namespace). |
| `verify/suggest.py` | **Rewrite.** RHEL-shaped remediation hints (`dnf install`, `semanage`, `firewall-cmd`) need distro-aware dispatch. Most user-visible delta. |
| `verify/remote.py` + `verify/ssh.py` | None expected. SSH execution is distro-portable; the `oscap` invocation (`oscap xccdf eval --remediate --tailoring-file ...`) is the same. |
| `verify/report.py` | None expected. Rule IDs in the report come from `reconcile`. |
| `verify/tailoring_drift.py` | None expected. XML drift is format-driven. |

Net change: one new datastream pin, one new dispatch in `baseline.py`, one rewrite in `suggest.py`.

## 9. Testing

### 9.1 Unit tests

Each new `rules/ubuntu2404/*.py` gets a unit test mirroring its `rules/alma9/*.py` counterpart. Same fixture shape (a minimal `HostConfig` with `distro: ubuntu2404`); asserts on `emit_post` / `emit_tailoring` / `emit_packages` / `exception_entry` output.

### 9.2 Golden snapshots

Existing `tests/golden/__snapshots__/` gains ubuntu2404 variants. A new `tests/golden/fixtures/ubuntu-minimal.yaml` fixture covers the ubuntu path. Existing alma9 fixtures (`unifi`, `cougar`) are alma9-only by design and remain so.

### 9.3 Schema tests

New validator-rejection tests for cross-distro field combinations (firewalld zone on ubuntu2404, `unattended_updates.apt_periodic_*` on alma9, `overrides.ssh_keep_open.ensure_selinux_port` on ubuntu2404, `container_host.*` on ubuntu2404).

### 9.4 Verify tests

A fixture ARF for an Ubuntu host (captured from a known-good `oscap` run, checked into `tests/fixtures/verify/`) feeds reconcile and asserts expected exceptions are matched.

### 9.5 Install-regression harness (Ubuntu variant)

Mirror of `.scratch/install-regression/` (#57). Lives at `.scratch/install-regression-ubuntu/`; gitignored; per-developer; local-only. Recipe: Ubuntu Server 24.04 LTS ISO + HTTP-served seed + QEMU EFI boot + SSH-in + smoke check. Same 30–90 min on TCG as the alma harness.

Recommend-running rules from `CLAUDE.md`: changes in `src/ks_gen/rules/ubuntu2404/`, `src/ks_gen/iso/` (when #87 lands), `templates/` ubuntu paths, or `writer.py` distro dispatch trigger a recommendation. Docs/test-only/alma9-only changes do not.

## 10. External tool dependencies

**Generated ubuntu2404 bundle references:**

- `ssg-ubuntu2404-ds.xml` from `scap-security-guide` 0.1.78+ (installed via apt during the autoinstall, or fetched into the target before `oscap` runs).
- `oscap` CLI from Ubuntu's OpenSCAP apt packages (exact package selection determined during implementation; run from `late-commands`, not from a Subiquity addon — there is no `oscap-anaconda-addon` analog).

**Generator host runtime:**

- Python 3.11+ with existing deps (`typer`, `pydantic>=2`, `jinja2`, `pyyaml`, `pykickstart`). No new runtime deps for ubuntu2404 bundle emission.
- `xorriso` only for `ks-gen iso` (alma9-only first ship).

## 11. Phasing — child issues to file (deferred to a follow-up session)

Suggested PR cadence, smallest-first:

1. **Schema discriminator + registry dispatch.** Add `distro:` field to `HostConfig`, implement `load_rules(distro)`, introduce `rules/_meta/`, mechanically move existing rules to `rules/alma9/`. No ubuntu rules yet. No behavior change for alma9 users (golden snapshots unchanged). Single PR.
2. **Bundle reshape + writer dispatch.** `Bundle.distro`, `Bundle.user_data`/`meta_data`, `build_bundle` distro switch. Emits an empty/placeholder ubuntu bundle. Single PR.
3. **Ubuntu rule ports.** One PR per rule, in the order in §6's sketch table. Each PR includes the rule file, unit test, and golden snapshot refresh. Skip `container_host` (tracked in #88). ~14 PRs.
4. **Verify distro-awareness.** Single PR covering the audit changes in §8.
5. **Install-regression harness for ubuntu2404.** Mirror of #57. Local-only, gitignored, documented in CLAUDE.md.

Acceptance for the tracking issue #81: design spec linked, decisions recorded, child issues 1–5 filed with labels (`type:feature`, `priority:p3`, `status:triage`).

Beyond first ship (already filed as separate tracking issues — see §12):

6. *(deferred)* `ks-gen iso` for ubuntu2404 — #87
7. *(deferred)* `container_host` on ubuntu2404 — #88
8. *(deferred)* 22.04 LTS secondary — #83

## 12. Out of scope (explicit non-goals)

Each item below has a dedicated tracking issue so a future drive-by reader has a place to attach interest or requirements without expanding this spec's scope:

- **Ubuntu 22.04 LTS** as a secondary target — #83
- **Debian (non-Ubuntu) STIG support** — #84
- **Non-Subiquity Ubuntu derivative support** (Mint, Pop!_OS, Zorin, elementary) — #85
- **Ubuntu Desktop hardening profile** — #86
- **`ks-gen iso` for Ubuntu (autoinstall ISO repack with CIDATA seed)** — #87
- **`container_host` rule for ubuntu2404** — #88

Other items intentionally not given a tracker (policy stance, no expected change):

- **Ubuntu 20.04 LTS** — EOL window too close.
- **Ubuntu interim releases (24.10, 25.04, 25.10)** — LTS only.
- **OEM / preinstalled-image flows (`oem-config`)** — outside the autoinstall surface.

## 13. Open questions resolved

The six open questions from tracking issue #81, with the decisions and reasoning recorded.

### 13.1 22.04 LTS secondary support? — Deferred

**Decision:** 24.04 LTS only for first ship; 22.04 stays open as a real option, tracked in #83.

**Reasoning:** Marginal cost of a second target is real (separate datastream pin, separate snapshots, separate install-regression harness target, some SSG rule-ID drift between ubuntu2204 and ubuntu2404). 22.04 LTS standard support runs through April 2027 — operators with existing 22.04 fleets remain a real audience; the door stays open.

### 13.2 Derivative scope? — Subiquity-only formal boundary

**Decision:** `ks-gen` supports targets that use **Subiquity + autoinstall + a `*.ubuntu.com` apt mirror**. Ubuntu Server LTS and Ubuntu Pro qualify; Mint (Ubiquity), Pop!_OS, Zorin, elementary do not.

**Reasoning:** Subiquity + autoinstall is a sharp, verifiable test. Each non-Subiquity derivative ships a different installer (some without any autoinstall analog); supporting them would mean a parallel installer-emission codepath, effectively a parallel `iso/` + `templates/` + writer. Tracked separately as #85.

### 13.3 Schema shape? — Single `HostConfig` with discriminator

**Decision:** Single `HostConfig` with a `distro: Literal["alma9", "ubuntu2404"] = "alma9"` field. Distro-specific fields gated by pydantic post-validators that raise explicit errors when misused.

**Reasoning:** Preserves operator UX (same config shape); zero migration for existing alma9 users (default discriminator); post-validators give "is this field valid here" checking without the upfront refactor a forked or discriminated-union schema would force. If divergence grows over time, evolving to a discriminated union is mechanical.

### 13.4 Rule abstraction? — Per-distro directories with shared `_meta`

**Decision:** `rules/<distro>/*.py` per distro, each fully implementing the Rule Protocol. A shared `rules/_meta/<rule_id>.py` module holds `id`, `summary`, `depends_on`, exception text — both distro implementations import from it.

**Reasoning:** Each rule's distro-specific implementation lives in one focused file; the shared `_meta` module gives a single source of audit text that an adapter pattern was trying to achieve, without forcing every rule through an abstraction it doesn't fit (DoD-CA install paths, faillock pam files, datastream selection don't fit a clean adapter). Adapter pattern (`PackageMgr`, `Firewall`, `Mac`) is the right end-state if Ubuntu becomes the third or fourth distro; at N=2 it's premature.

### 13.5 ISO builder for Ubuntu? — HTTP-served seed first

**Decision:** First-ship Ubuntu delivery is **HTTP-served seed** (`user-data` + `meta-data`). Full autoinstall ISO repack tracked as a deferred child issue (#87).

**Reasoning:** The hard part of Ubuntu support is rule porting (~13 rules × tailoring + post + packages); ISO repack is well-understood mechanics that can ship as a focused follow-up. Operator UX is slightly different from Alma's "download ISO, boot, done" — operator needs an HTTP host and a one-time boot-cmdline edit. Acceptable for first ship; #87 closes the gap.

### 13.6 Verify / reconcile distro-awareness? — Distro-aware loading in `verify/*`

**Decision:** `verify/baseline.py` reads `host.yaml.distro` from the bundle; loads the correct datastream. `verify/suggest.py` rewrites for distro-aware remediation hints. Other `verify/*` modules audited for hidden RHEL assumptions; expected to need no significant change.

**Reasoning:** The bundle already carries everything verify needs once `host.yaml` records the distro (per §3). The reconcile algorithm itself (intersect deployed-fail rules with expected-disabled rules) is portable across distros — the only thing that meaningfully differs is which datastream is loaded and which remediation hints are emitted. Forking `verify/reconcile.py` per distro would pay a complexity tax for an algorithm that's identical.

## 14. References

- Tracking issue: [#81](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/81)
- AlmaLinux 9 design spec: [`docs/superpowers/specs/2026-06-01-alma-stig-kickstart-design.md`](2026-06-01-alma-stig-kickstart-design.md)
- DISA Canonical Ubuntu 24.04 LTS STIG v1r5 (2026-05-05)
- Subiquity autoinstall reference: <https://canonical-subiquity.readthedocs-hosted.com/en/latest/reference/autoinstall-reference.html>
- cloud-init NoCloud datasource: <https://cloudinit.readthedocs.io/en/latest/reference/datasources/nocloud.html>
- ComplianceAsCode/content `products/ubuntu2404/`: <https://github.com/ComplianceAsCode/content/tree/master/products/ubuntu2404>
- Child issues filed during design: #83, #84, #85, #86, #87, #88
