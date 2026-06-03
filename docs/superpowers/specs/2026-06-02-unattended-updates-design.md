## Design: unattended updates and reboots

**Date:** 2026-06-02
**Status:** Draft — awaiting plan
**Target release:** v0.2.0

## Problem

`ks-gen` v0.1.0 installs a STIG-compliant AlmaLinux 9 host and walks away.
The SCAP Security Guide profile enables `dnf-automatic.timer` with the
upstream defaults, which on RHEL/AlmaLinux 9 amount to *download only,
no apply, no reboot*. The result: a freshly installed STIG box accrues
unpatched CVEs from the moment it boots and stays vulnerable until an
operator logs in to run `dnf upgrade` and `systemctl reboot`. That is
precisely the failure mode "unattended" patching exists to prevent.

Two facets need to be solved together, not separately:

- **Updates** — security patches need to land automatically every night;
  full updates can wait for a monthly cadence so feature churn is bounded
  and predictable.
- **Reboots** — kernel, glibc, and systemd updates require a reboot to
  actually take effect. `dnf-automatic`'s native `reboot = when-needed`
  reboots immediately after the update transaction, which would mean
  unannounced mid-night reboots whenever a security update happens to
  pull in a new kernel. Operators of headless STIG hosts want reboots
  confined to a predictable maintenance window.

## Goals

- Nightly automatic application of *security-only* updates.
- Monthly automatic application of *all* updates (still within the AL9
  major version; no system-upgrade).
- Reboots, when required to pick up a pending kernel/glibc/etc., happen
  only inside a per-host configurable maintenance window.
- All three schedules expressible in `host.yaml`, with sensible defaults
  so an operator can opt in with a single `enable: true`.
- Fail-loud posture matches the rest of `ks-gen`: a broken reboot check
  logs at error and skips the reboot rather than silently masking
  pending kernel updates.
- The `dnf-automatic_*` SCAP rules the STIG profile enables still pass
  unmodified — this feature *reinforces* the STIG control rather than
  fighting it.

## Non-goals

- Cross-major-version upgrades (AL9 → AL10). `dnf-automatic` cannot do
  this without explicit `dnf system-upgrade` invocation; out of scope.
- Per-package exclusions ("never auto-upgrade kernel"). Operators with
  that requirement can append a `dnf.conf` override via `custom_post`.
  Not a first-class knob in v0.2.0.
- Reboot deferral based on host state (active SSH sessions, running
  jobs, etc.). The maintenance window is the answer to "when is it safe
  to reboot."
- Cluster-aware rolling reboots. That's an orchestration concern; ks-gen
  produces single-host kickstarts.
- Email / Slack / PagerDuty notifications on update or reboot events.
  Updates and reboots log to journal and motd; consumption is the host
  operator's choice.

## Design

### YAML schema

A new `overrides.unattended_updates` block, modeled with the existing
`StrictModel` (`extra="forbid"`, `frozen=True`) pattern in `config.py`:

```yaml
overrides:
  unattended_updates:
    enable: true                              # master switch
    nightly_security:
      enable: true                            # opt out by setting false
      on_calendar: "*-*-* 02:00:00"           # systemd OnCalendar; nightly 02:00 host-local
    monthly_full:
      enable: true                            # opt out by setting false
      on_calendar: "Sun *-*-1..7 02:30:00"    # first Sunday each month, 02:30 host-local
    reboot_window:
      enable: true                            # opt out by setting false
      on_calendar: "Sun *-*-* 03:00:00"       # weekly Sunday 03:00 host-local
```

All fields optional. With `unattended_updates: {}` an operator gets the
full default config above. With `unattended_updates: { enable: false }`
the rule no-ops and the kickstart leaves the stock STIG-managed
`dnf-automatic.timer` exactly as oscap remediation set it.

Backing pydantic models, named to match the rest of `config.py`:

- `UnattendedUpdatesCfg(enable, nightly_security, monthly_full, reboot_window)`
- `NightlySecurityCfg(enable, on_calendar)`
- `MonthlyFullCfg(enable, on_calendar)`
- `RebootWindowCfg(enable, on_calendar)`

`on_calendar` is typed as `str` with `min_length=1`; we do not try to
parse systemd calendar grammar in pydantic — `systemd-analyze calendar`
inside the installed host will reject typos at first boot, which is
sufficient for a fail-loud posture.

One cross-field validator on `UnattendedUpdatesCfg`:

- `reboot_window.enable=true` requires at least one of
  `nightly_security.enable` or `monthly_full.enable` to be true. If both
  update timers are off and the reboot window is on, raise: `reboot_window
  requires at least one update timer enabled — otherwise the host will
  reboot weekly against a never-updated system`.

### Rule plugin

A new module `src/ks_gen/rules/unattended_updates.py` exporting a
module-level `RULE`, following the contract in `rules/_types.py`:

| Attribute | Value |
|---|---|
| `id` | `"unattended_updates"` |
| `summary` | `"Configure dnf-automatic for nightly security + monthly full updates, with reboot inside a maintenance window."` |
| `depends_on` | `[]` |
| `stig_rules_affected` | `[]` |
| `applies(cfg)` | `cfg.overrides.unattended_updates.enable` |
| `emit_tailoring(cfg)` | `[]` — no XCCDF changes |
| `emit_post(cfg)` | The bash block (next section) |
| `exception_entry(cfg)` | `None` — nothing disabled |

The rule does not touch tailoring. The STIG profile's
`timer_dnf-automatic_enabled` rule, and any companion rules requiring
`apply_updates = yes` and `upgrade_type = security`, still pass —
because the rule's bash block configures `/etc/dnf/automatic.conf` with
exactly those values and leaves the stock `dnf-automatic.timer` enabled
(merely overrides its `OnCalendar` via a systemd drop-in).

### Package additions

`Packages.required` defaults in `config.py` extended with two entries:

- `dnf-automatic` — required by the stock STIG timer anyway, but
  listing it explicitly makes the kickstart self-documenting.
- `dnf-utils` — provides `needs-restarting`, used by the reboot script.

The list grows from 9 to 11 entries. Operators who hand-trimmed
`packages.required` in their `host.yaml` are unaffected; the defaults
only apply when the field is absent.

### Post-install bash block

The rule emits one `%post` block fragment (composed into the existing
`%post --log=/root/ks-post.log` block by the template loop). Sections:

**1. Stock dnf-automatic config — nightly security (conditional).** Only
emitted when `nightly_security.enable=true`. Rewrite
`/etc/dnf/automatic.conf` from scratch (don't try to merge with whatever
the package shipped):

```ini
[commands]
upgrade_type = security
apply_updates = yes
reboot = never
network_online_timeout = 60
[emitters]
emit_via = motd
[base]
debuglevel = 1
```

`reboot = never` is critical — reboots are owned by the maintenance-window
timer, not by dnf-automatic.

**2. Stock timer override — operator's nightly schedule (conditional).**
Only emitted when `nightly_security.enable=true`. Drop-in at
`/etc/systemd/system/dnf-automatic.timer.d/ks-gen.conf`:

```ini
[Timer]
OnCalendar=
OnCalendar={nightly_on_calendar}
RandomizedDelaySec=0
```

The empty `OnCalendar=` line is required: systemd treats `OnCalendar` as
a list-valued setting, so without the reset the override *appends* to the
stock 06:00 schedule rather than replacing it.

**3. Monthly full (conditional).** Only emitted when
`monthly_full.enable=true`. Three files:

- `/etc/dnf/automatic-full.conf` — same as the security config but with
  `upgrade_type = default`.
- `/etc/systemd/system/ks-gen-dnf-automatic-full.service` — oneshot,
  `ExecStart=/usr/bin/dnf-automatic /etc/dnf/automatic-full.conf`,
  `After=network-online.target`, `Wants=network-online.target`.
- `/etc/systemd/system/ks-gen-dnf-automatic-full.timer` — `OnCalendar`
  from config, `Persistent=true`, installed in `timers.target`.

**4. Reboot window (conditional).** Only emitted when
`reboot_window.enable=true`. Three files:

- `/usr/local/sbin/ks-gen-reboot-if-needed` — bash script (mode 755):

  ```bash
  #!/bin/bash
  set -euo pipefail
  if ! command -v needs-restarting >/dev/null 2>&1; then
    logger -t ks-gen -p user.err "needs-restarting missing; cannot evaluate reboot"
    exit 1
  fi
  if needs-restarting -r >/dev/null 2>&1; then
    logger -t ks-gen "no reboot needed at $(date -Is)"
    exit 0
  fi
  logger -t ks-gen "reboot needed, rebooting at $(date -Is)"
  systemctl reboot
  ```

  `needs-restarting -r` exits 0 when no reboot is required, 1 when one
  is. The script logs every outcome to the system journal under the
  `ks-gen` tag so operators auditing reboot history have a paper trail.
  Missing `needs-restarting` logs at error level and exits non-zero —
  systemd will mark the timer's last run as failed and the operator
  will see it in `systemctl list-timers --failed`.

- `/etc/systemd/system/ks-gen-reboot-if-needed.service` — oneshot,
  `ExecStart=/usr/local/sbin/ks-gen-reboot-if-needed`.
- `/etc/systemd/system/ks-gen-reboot-if-needed.timer` — `OnCalendar`
  from config, `Persistent=true`, installed in `timers.target`.

**5. Activation.** `systemctl daemon-reload`, then `systemctl enable`
each custom timer that was emitted. The stock `dnf-automatic.timer` is
re-enabled when nightly security is on (the STIG profile already enabled
it, but explicitly re-running `systemctl enable` after our drop-in
guarantees the override file is picked up on first boot). When
`nightly_security.enable=false`, leave the stock timer alone — the STIG
profile's state stands.

### Why `dnf-automatic` is configured but reboot is custom

Two reasons we don't use `dnf-automatic`'s built-in `reboot = when-needed`:

- It reboots immediately after the update transaction. With nightly
  security updates, that's a nightly potential reboot — surprises
  operators who expect a predictable window.
- It has no concept of a window. Once dnf-automatic decides a reboot
  is warranted, it goes. We need a *separate scheduler* that knows
  about the window; `needs-restarting -r` queried by a window-scoped
  systemd timer is the cleanest separation.

A small systemd unit doing the reboot itself also keeps the responsibility
visible — an operator running `systemctl list-timers` sees
`ks-gen-reboot-if-needed.timer` in the list and can immediately reason
about it.

### Why we don't replace the stock dnf-automatic.timer

We override its `OnCalendar` via drop-in but leave the unit itself
enabled, because:

- The STIG profile's `timer_dnf-automatic_enabled` rule asserts that
  specific unit is enabled. Replacing it with a custom-named unit would
  require a tailoring `disable` for the SSG rule and an
  `exception_entry`, complicating the audit story.
- A drop-in override is the documented systemd mechanism for exactly
  this case ("upstream unit, operator-supplied schedule change").

### Defaults rationale

- **Nightly 02:00** — chosen over the SSG default 06:00 because 06:00
  collides with morning startup activity on shared infrastructure; 02:00
  is consistently quiet across time zones.
- **First Sunday of month, 02:30** — `Sun *-*-1..7 02:30:00` matches
  systemd's idiom for "first Sunday." Thirty minutes after the nightly
  timer slot gives the security path room to finish if the two ever
  collide.
- **Sunday 03:00 reboot** — sits 30 min after the monthly full update
  on first-Sunday weeks, giving slack for slow mirrors. On the other
  three Sundays of the month it picks up any pending kernel from the
  preceding week's nightly security runs.

These are *defaults* and fleet operators are expected to stagger them
across hosts to avoid synchronized fleet-wide reboots at 03:00. This is
called out explicitly in `MANUAL.md`.

## Testing strategy

| Layer | What it asserts | Mechanism |
|---|---|---|
| Unit | `applies()` true when enabled, false when `enable=false` | New `tests/rules/test_unattended_updates.py` |
| Unit | `emit_post()` contains the security config + timer drop-in (incl. the empty `OnCalendar=` reset) when `nightly_security.enable=true`, monthly block when `monthly_full.enable=true`, reboot block when `reboot_window.enable=true`; each is omitted when its `enable` is false | Same file |
| Unit | Operator-supplied `on_calendar` strings appear verbatim in the emitted bash | Same file |
| Unit | `emit_tailoring()` returns `[]` and `exception_entry()` returns `None` | Same file |
| Config | `reboot_window.enable=true` with both `nightly_security.enable=false` and `monthly_full.enable=false` raises ValueError | New case in `tests/test_config.py` |
| Config | Defaults round-trip and validate | Existing schema-round-trip test picks this up automatically |
| Snapshot | Four existing golden scenarios regenerated to pick up the new defaults | `tests/golden/snapshots/{minimal-dhcp,stig-strict,modern-crypto,bare-metal-usbguard}/` |
| Snapshot | New `unattended-disabled` scenario showing the rule no-op'd | New directory under `tests/golden/snapshots/` plus YAML in `tests/golden/scenarios/` |
| End-to-end | First-boot Hyper-V VM shows three timers in `systemctl list-timers` and motd reflects update emitter | Manual `MINIMAL-TEST.md` walkthrough |

## Scope of changes

| File | Change |
|---|---|
| `src/ks_gen/config.py` | Add `UnattendedUpdatesCfg` + nested models; wire `unattended_updates` into `Overrides`; add `dnf-automatic` and `dnf-utils` to `Packages.required` defaults |
| `src/ks_gen/rules/unattended_updates.py` | New rule plugin (frozen dataclass + module-level `RULE`) |
| `tests/rules/test_unattended_updates.py` | New test module |
| `tests/test_config.py` | Add validator coverage for the cross-field rule |
| `tests/golden/scenarios/unattended-disabled.yaml` | New scenario fixture |
| `tests/golden/snapshots/{minimal-dhcp,stig-strict,modern-crypto,bare-metal-usbguard}/ks.cfg` | Regenerate (will diff by the new `%post` fragment and two new packages) |
| `tests/golden/snapshots/unattended-disabled/` | New snapshot directory (`ks.cfg`, `tailoring.xml`, `exceptions.md`, `host.yaml`) |
| `MANUAL.md` | New "Unattended updates" subsection under the override matrix; explicit note on fleet-wide window staggering |
| `MINIMAL-TEST.md` | Add post-install verification step for the three timers |
| `CHANGELOG.md` | New `Added` entry under `## [v0.2.0] - unreleased` |

## Branch and release strategy

Lands on a feature branch `impl/v0.2.0-unattended-updates` off `main`.
Single PR. Tag `v0.2.0` is *not* cut from this PR alone — the v0.1.x
queue items (`hd:` oscap transport, `--fetch-remote-resources` for OVAL)
also belong on the next minor and will land separately before the tag.

## Open questions

None at design time. The validator-driven config space is tight enough
that operator misuse fails at `ks-gen gen`, not at install or first boot.
