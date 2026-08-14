# STIG means kernel FIPS — design

Closes #84. Date: 2026-08-13.

## Problem

`crypto.policy: STIG` sets the system crypto *policy* to FIPS but never puts
the *kernel* in FIPS mode. On the first AlmaLinux 10 STIG install (harness run
2026-08-14) a live `oscap` scan showed:

```
sysctl_crypto_fips_enabled    fail
system_booted_in_fips_mode    fail
enable_fips_mode              fail
fips_crypto_subpolicy         pass
```

`/proc/sys/crypto/fips_enabled` was `0` and no `fips=1` was on the kernel
command line. ks-gen never runs `fips-mode-setup --enable`, and on
ssg-almalinux9 (0.1.80) and ssg-almalinux10 (0.1.81) the `enable_fips_mode`
remediation only acts inside a bootc container, so it is a no-op on a normal
install.

Two consequences: a host advertised as the FIPS-aligned option is not
FIPS-validated, and three stig-selected rules fail on every AL9/AL10 STIG host
with nothing in `exceptions.md` to explain them — indistinguishable from a
genuine regression. That is the same failure class as #61 and #67.

MANUAL.md already documents the behaviour we do not have. §3.5's table claims
`crypto.policy: STIG` sets `fips=1`, and the black-screen troubleshooting entry
claims "the `crypto_policy` rule does this in the STIG path" about a
`dracut --regenerate-all` that no rule runs. The docs over-claim; this change
makes them true rather than walking them back.

## Findings that shaped the design

Established by reading the code and the pinned datastream extracts, not
assumed:

1. **AL8 is already in FIPS.** `alma8/crypto_policy.py:54` disables
   `enable_dracut_fips_module` only when *not* STIG, and its own comment
   records that AL8's remediation for that rule runs `fips-mode-setup
   --enable`. Under STIG it stays enabled and fires. This resolves the "likely
   distro split" left open in #84 without needing an AL8 install: the change is
   explicit-but-idempotent on AL8, not new behaviour.
2. **AL9 has a fourth broken rule the issue missed.**
   `enable_dracut_fips_module` is stig-selected on AL9 with no remediation
   shipped (`alma9/crypto_policy.py:38-40`), so it also fails forever on AL9
   STIG.
3. **`overrides.fips_mode` has no degrees of freedom.** `config.py:782`
   already rejects `fips_mode: true` with MODERN and FUTURE. Once STIG implies
   kernel FIPS, the field is exactly `policy is STIG`. The "kernel FIPS without
   the STIG policy" configuration it appears to offer was never loadable.
4. **The knob as shipped is a boot-bricking trap.**
   `tests/golden/stig-strict.host.yaml:12` sets `fips_mode: true`, which
   renders a bare `fips=1` (`ks.cfg.j2:31,33`) with no dracut FIPS module and
   no `boot=UUID=`. ks-gen always creates a separate `/boot`
   (`partitioning_stig_server.j2:4`), so dracut panics on the integrity check.
   The knob must be replaced, not switched on.
5. **On Ubuntu the knob is inert.** `user-data.j2` never reads `fips_mode`, so
   `fips_mode: true` on ubuntu2404 silently does nothing today.
6. **Ubuntu cannot reach kernel FIPS at all.** It requires an Ubuntu Pro
   `fips-updates` entitlement that ks-gen does not manage
   (`ubuntu2404/crypto_policy.py:57`).

## Decisions

| Question | Decision |
|---|---|
| What does `crypto.policy: STIG` mean? | Kernel FIPS on alma8/9/10. No opt-out. |
| `overrides.fips_mode`? | Becomes derived; the field survives only as a checked assertion. |
| Mechanism? | `fips-mode-setup --enable` in `%post`, not an installer boot arg. |
| Ubuntu? | In scope — declared as an exception, since it structurally cannot pass. |
| Merge gate? | AL9 + AL10 STIG install-regression runs. |

Rejected alternatives, and why:

- **Declare it and keep STIG policy-only.** Smaller and honest, but leaves the
  shipped MANUAL wrong and "STIG" meaning something weaker than every reader
  assumes.
- **`fips=1` on the installer boot line** (anaconda-native, RHEL's preferred
  route). Needs `HostConfig` plumbed into `build_iso` — which today takes only
  the rendered `ks.cfg` (`iso/builder.py:25`) — and leaves `ks-gen gen` users
  on a stock ISO with no FIPS at all.
- **A separate `fips_mode` rule.** Splits an ordering-critical sequence across
  two `%post` blocks held together only by a `depends_on` edge. The coupling is
  real: `fips-mode-setup` resets the crypto policy, so the `FIPS:STIG` re-set
  must follow it in the same block.
- **Deleting `overrides.fips_mode`.** `StrictModel` forbids extra keys, so
  removal breaks any `host.yaml` that mentions it.

## Design

### Config semantics

- **New derived property** `HostConfig.kernel_fips` —
  `crypto.policy is STIG and distro in {alma8, alma9, alma10}`.
  `ks.cfg.j2:31,33` reads this instead of `cfg.overrides.fips_mode`.
- **`overrides.fips_mode` becomes `bool | None = None`.** `None` means
  "derive". This is the compatibility hinge: existing STIG `host.yaml` files
  that never mention the key keep loading and now gain kernel FIPS. Under the
  current `bool = False` default, any rule rejecting `False` + STIG would break
  every one of those files.
- **Rejected at load**, each with a friendly message via `loader.py:86`:
  - `False` + STIG — STIG enables kernel FIPS; there is no opt-out, choose
    MODERN or FUTURE.
  - `True` + MODERN/FUTURE — unchanged from today.
  - `True` + ubuntu2404 — kernel FIPS needs a Pro `fips-updates` entitlement
    ks-gen does not manage. Explicit rejection rather than today's silent
    no-op.

### `%post` mechanism

`_emit_post` in `alma9/crypto_policy.py` (shared by the alma8 and alma10
siblings) gains a STIG-only block, in this order:

```sh
fips-mode-setup --enable
dracut -f --regenerate-all
update-crypto-policies --set FIPS:STIG    # existing; MUST come after
```

- **Order is forced.** `fips-mode-setup` resets the policy to plain `FIPS`, so
  AL9's `FIPS:STIG` re-set has to follow it or #66 returns.
- **`--regenerate-all` is load-bearing.** Inside anaconda's chroot `uname -r`
  is the *installer's* kernel, not the installed one, so `fips-mode-setup`'s
  own `dracut -f` can rebuild the wrong initramfs or none. `--regenerate-all`
  covers every installed kernel. This is the fix MANUAL's black-screen entry
  already prescribes.
- **No `|| true`.** A failed `fips-mode-setup` leaves a host that boots fine
  and is not in FIPS — bug #84 again, silently. Under `set -euxo pipefail` it
  aborts the install after echoing a ks-gen diagnostic. A failed install is
  recoverable; a host that falsely claims FIPS is the defect being fixed.

**Packages.** None. This design assumed AL8 needed `dracut-fips`; the
verification step it mandated refuted that before any code was written.
AlmaLinux 8's `dracut` ships `/usr/lib/dracut/modules.d/01fips/` itself and
carries only a virtual `Provides: dracut-fips` — there is no installable
package by that name in any AL8 repo. `emit_packages` stays `[]` on every
distro.

### Tailoring and exceptions

**Alma (8/9/10): no change.** `emit_tailoring` already returns `[]` under STIG
and `exception_entry` already returns `None`. Both stay, and for the first time
are true — the rules pass rather than failing unexplained.

AL9's `enable_dracut_fips_module` should pass once `fips-mode-setup` writes
`/etc/dracut.conf.d/40-fips.conf`. This is the one claim the AL9 regression run
must confirm; if it does not hold, that rule gets declared as an exception
rather than left failing.

**Ubuntu: split the disable set.** `is_fips_mode_enabled` moves out of
`_TAILORED_WHEN_NOT_STIG` into a new always-disabled list, since no Ubuntu
policy can pass it. `emit_tailoring` disables that list under every policy;
`exception_entry` stops returning `None` under STIG and names it with the
Pro-entitlement reason. This keeps the `disabled ⊆ named-in-exception`
invariant (`test_invariants.py:77`) satisfied and stops oscap remediating
toward FIPS on a host that structurally cannot get there.

### Install-time behaviour

The oscap scan runs pre-reboot, so `fips_enabled` is still `0` in the install
ARF and these rules land in the baseline as `fail`. The first post-reboot
`ks-gen verify` shows them as fixed. That sequence is correct and is left
visible rather than papered over.

## Testing

**Unit tests.**

- **`kernel_fips` truth table** — 4 distros × 3 policies × the tri-state
  `fips_mode` field, generated by parametrize. This cluster has broken four
  times (#61, #66, #67, #84), each time somewhere the example tests did not
  reach. A mechanical table over every combination closes it; more examples do
  not.
- **New STIG-side invariant in `test_fips_dependent_rules.py`** — for every
  distro, each FIPS candidate under STIG must be either satisfiable because
  `kernel_fips` is on, or disabled and named in an exception entry. That file
  already asserts this for MODERN/FUTURE (#67); the missing STIG direction is
  the hole #84 fell through. `test_stig_policy_disables_no_fips_rule` folds
  into it.
- **Loader rejections** — the three new error paths and their friendly
  messages.

**Snapshots.** `tests/golden/stig-strict` regenerates: `%post` gains the FIPS
block, the bootloader line is unchanged (that fixture already set
`fips_mode: true`). Ubuntu goldens gain an `exceptions.md` entry under STIG.
The regen diff is read before committing and must contain those changes and
nothing else.

**Docs.** MANUAL.md is wrong in five places, all corrected here: §3.5's table
(true for Alma after this, needs a Ubuntu carve-out), the `fips_mode` line at
:750, the wizard example at :885, the rule description at :1016, and the
black-screen entry at :2023 which claims a `dracut --regenerate-all` no rule
runs.

**Commit shape.** `feat!` with a `BREAKING CHANGE:` footer — existing STIG
`host.yaml` files gain kernel FIPS on their next build, which must not arrive
as a quiet minor bump.

## Validation

AL9 + AL10 STIG install-regression runs gate the merge. The checks are added to
the harness smoke-check set so they remain a permanent gate rather than a
one-time manual look:

- the host boots at all (the black-screen failure mode)
- `/proc/sys/crypto/fips_enabled` is `1`, and `/proc/cmdline` carries both
  `fips=1` and a `boot=UUID=`
- SSH-with-key still authenticates — FIPS changes what sshd offers, the #72 and
  #73 scar
- a live `oscap` scan shows all four FIPS rules passing on each distro —
  AL9: `enable_fips_mode`, `sysctl_crypto_fips_enabled`,
  `enable_dracut_fips_module`, `fips_crypto_subpolicy`; AL10:
  `enable_fips_mode`, `sysctl_crypto_fips_enabled`,
  `system_booted_in_fips_mode`, `fips_crypto_subpolicy`

AL8 is not gated, for the reason in Finding 1; #84 gets a note recording that
as reasoned rather than observed.

**Rollback.** There is no runtime kill switch. If a regression run
black-screens, the change is reverted, not flag-disabled — which is why both
runs gate the merge.

**Review.** `/code-review high` before the push: this can brick a boot, and the
failure is silent until reboot.
