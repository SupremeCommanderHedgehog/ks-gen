# Design: `hd:LABEL=` transport for oscap tailoring fetch

**Date:** 2026-06-06
**Status:** Active. One of the two v0.1.x gaps queued before tagging v0.2.0.
**Companion plan:** `docs/superpowers/plans/2026-06-06-hd-oscap-transport-implementation.md` (to be written next)

## Problem

`ks-gen iso` produces an AlmaLinux 9 install ISO with `/ks.cfg` and
`/tailoring.xml` at the ISO root. The operator boots the ISO and types
`inst.ks=hd:LABEL=<volid>:/ks.cfg` at the GRUB prompt. Today, the install
proceeds far enough to load the kickstart — but the oscap remediation
`%post` block fails on its only `case` arm:

```
ks-gen: unsupported inst.ks transport 'hd:LABEL=ALMA9:/ks.cfg' (v0.1 supports http(s) only)
```

The block exits non-zero under `--erroronfail` and the install aborts.
The HTTP delivery path (the original v0.1.0 acceptance test) works
because `curl` reaches the kickstart server. ISO delivery has never
worked end-to-end.

This spec defines the `hd:LABEL=` branch — the second of the two known
v0.1 gaps that should land before tagging v0.2.0. (The first is
`--fetch-remote-resources` for OVAL.)

## Goals

- `ks-gen iso` bundles run through oscap remediation at install time
  without an HTTP server.
- HTTP delivery is unchanged from an operator's perspective.
- Failure to stage `tailoring.xml` hard-fails the install with a clear
  error message, not a silent fallback to base STIG.
- The split that makes `hd:LABEL=` work is explicit in the template,
  not buried in a one-line hack that future maintainers might collapse.

## Non-goals

- Supporting `cdrom:`, `nfs:`, `hd:UUID=`, or bare `hd:/dev/sdX`
  transports. Only `hd:LABEL=<volid>:/ks.cfg` (the form `ks-gen iso`
  produces and `MANUAL.md` documents) is in scope. Other `hd:*` forms
  fall through to the existing unsupported-transport error.
- Rewriting `isolinux`/`grub` boot configs inside `ks-gen iso` so the
  operator no longer has to type `inst.ks=hd:LABEL=…` at the boot
  prompt. Still tracked for v0.2 backlog (separate from v0.2.0 tag).
- Configuration knobs. No new YAML field, no `--set` switches; the
  transport is derived from `/proc/cmdline` at install time, exactly
  as for HTTP today.

## Why not the obvious one-liner

The seductive approach is to add a single `hd:*)` arm to the existing
chrooted `%post` that does:

```
cp /run/install/repo/tailoring.xml /root/tailoring.xml
```

This is wrong. `/run/install/repo` is mounted on the **installer**
side of the chroot wall; by default Anaconda does not bind-mount it
into the target chroot during `%post`. The `cp` silently fails at
install time (file not found), `%post --erroronfail` aborts, and we
end up with a different failure mode at the acceptance test — exactly
the same class of mistake as the v0.1.0 `%addon` saga (see
`docs/superpowers/specs/2026-06-01-tailoring-pre-fetcher-design.md`,
"Superseded by" section).

The HTTP branch happens to work in the chrooted `%post` because
Anaconda configures the network stack reachable from inside the
chroot. Media access does not get the same treatment.

## Design

### Architecture: split the oscap `%post` into fetch + eval

The current single chrooted `%post` block at lines 42-75 of
`src/ks_gen/templates/ks.cfg.j2` becomes two adjacent blocks:

**Block 1 — fetch stage**, `%post --nochroot`. Runs in the installer
environment where both network (`curl` for HTTP) and the kickstart
media at `/run/install/repo` (for `hd:LABEL=`) are reachable. Stages
`tailoring.xml` into the target rootfs at `/mnt/sysimage/root/`.

**Block 2 — eval stage**, `%post` (chrooted, as today). Runs `oscap
xccdf eval --remediate` against the staged tailoring. No transport
awareness; reads `/root/tailoring.xml` unconditionally.

Both transports go through the fetch block's `case` statement, which
keeps transport dispatch in one place.

### Rendered template

```jinja
%post --nochroot --erroronfail --log=/mnt/sysimage/root/ks-post-oscap-fetch.log
set -euo pipefail

# Stage tailoring.xml into the target rootfs. Runs in the installer
# environment so both network (http(s)) and the kickstart media at
# /run/install/repo (hd:LABEL=) are reachable. The chrooted oscap
# block that follows reads /root/tailoring.xml unconditionally.
ks_arg=$(awk -F'inst.ks=' 'NF>1{print $2}' /proc/cmdline | awk '{print $1}')
case "$ks_arg" in
  http://*|https://*)
    base="${ks_arg%/*}"
    curl -fsSL --retry 5 --retry-delay 3 \
      "${base}/tailoring.xml" -o /mnt/sysimage/root/tailoring.xml
    ;;
  hd:LABEL=*)
    cp /run/install/repo/tailoring.xml /mnt/sysimage/root/tailoring.xml
    ;;
  *)
    echo "ks-gen: unsupported inst.ks transport '$ks_arg' (supports http(s) and hd:LABEL=)" >&2
    exit 1
    ;;
esac
chmod 0600 /mnt/sysimage/root/tailoring.xml
%end

%post --erroronfail --log=/root/ks-post-oscap.log
set -euo pipefail

test -s /root/tailoring.xml
head -c 5 /root/tailoring.xml | grep -q '<?xml'

# --remediate can exit non-zero when rules remain failed (e.g., exception-
# disabled rules). The next %post block (ks-gen rule overrides) re-asserts
# critical state, so don't abort the install on a non-zero oscap exit.
oscap xccdf eval --remediate \
  --profile xccdf_org.ssgproject.content_profile_{{ cfg.meta.profile }} \
  --tailoring-file /root/tailoring.xml \
  --results-arf /root/oscap-remediation-results.xml \
  --report /root/oscap-remediation-report.html \
  /usr/share/xml/scap/ssg/content/{{ cfg.meta.scap_content }} || true
%end
```

### Notable details

- **New log file:** `/root/ks-post-oscap-fetch.log` (written via
  `/mnt/sysimage/root/...` from `--nochroot`). The eval-stage log stays
  at `/root/ks-post-oscap.log`. Both land in `/root/` on the installed
  system — same audit surface as today, one extra file.
- **`chmod 0600`** on the staged tailoring. Today the mode is whatever
  curl writes (umask-dependent); this is mildly tighter and explicit.
- **Error message** updated from `(v0.1 supports http(s) only)` to
  `(supports http(s) and hd:LABEL=)` — operator-visible.
- **Ordering** matters: the `--nochroot` fetch block must precede the
  chrooted eval block. Anaconda runs `%post` blocks top-to-bottom; the
  template emits them in that order unconditionally.
- **The two trailing `%post` blocks** (rule overrides, `custom_post`)
  are unchanged.

### `iso.py` impact: none

`src/ks_gen/iso.py` already maps `tailoring.xml` to `/tailoring.xml`
at the ISO root. When the ISO is mounted at `/run/install/repo` during
install, the file lives at `/run/install/repo/tailoring.xml` — exactly
where the `hd:LABEL=*)` arm reads from. No changes to `iso.py`.

## `lint.py` invariants

`lint.py` validates load-bearing invariants in the rendered ks.cfg.
The split touches two existing invariants and adds one new one.

**Adjusted (existing):**

- *oscap `%post` block presence* — currently asserts a single `%post`
  match with the oscap invocation. Becomes a two-block assertion: a
  fetch-stage `%post --nochroot` followed immediately by a chrooted
  eval-stage `%post` carrying the `oscap xccdf eval --remediate`
  invocation.
- *oscap invocation + `--tailoring-file` reference* — unchanged regex,
  now anchored inside the eval block.

**New:**

- *`hd:LABEL=` branch present in fetch case statement* — guards the
  regression where a future change collapses the `case` back to
  HTTP-only. The rendered ks.cfg must contain `hd:LABEL=*)` followed
  by a `cp /run/install/repo/tailoring.xml` line before the next
  `;;`. Failure key: `oscap_hd_label_branch_missing` (or similar; the
  exact key lands during implementation).

**Test additions** in `tests/test_lint.py`:

- One positive test: render a config, assert `lint.py` passes.
- One negative test: render the same config, mutate the rendered
  output to delete the `hd:LABEL=*)` arm, assert lint fails with the
  expected error key.

## Tests

1. **Golden snapshots** (`tests/golden/__snapshots__/*.ambr`,
   five scenarios) regenerated via
   `pytest tests/golden/ --snapshot-update`. Each diff inspected
   manually before commit. Expected change shape: every snapshot
   gains the `%post --nochroot` fetch block + the `hd:LABEL=*)` case
   arm + the `chmod 0600`; the eval block sheds its leading curl-and-
   case-statement preamble; nothing else moves.
2. **`tests/test_lint.py`** — new positive + negative tests for the
   `hd:LABEL=` invariant.
3. **No new template-render unit test.** The golden snapshots already
   cover "the rendered text contains the hd: branch" trivially.

### Manual acceptance: MINIMAL-TEST.md

A new section, slotted after the existing HTTP walkthrough, mirrors
its structure for the ISO path:

- **Step 1b — Build a tailored ISO** with `ks-gen iso ... --volid
  ALMA9KS`.
- **Step 4 (modified)** — attach the tailored ISO instead of the
  stock one. Other VM-creation lines unchanged.
- **Step 5 (modified)** — at the GRUB `e`-edit prompt, append `
  inst.ks=hd:LABEL=ALMA9KS:/ks.cfg`. No HTTP server needed.
- **Expected signals** — `/root/ks-post-oscap-fetch.log` and
  `/root/ks-post-oscap.log` both exist on the installed system. Login
  + SSH check + oscap audit proceed as in Steps 6-8 of the HTTP
  walkthrough (referenced, not duplicated).

The label `ALMA9KS` is chosen distinct from the existing v0.1.0
`ALMA9` reference to make it visually clear that the label is
operator-chosen.

## Documentation

- **`MANUAL.md`** — one-paragraph note in the `ks-gen iso` section
  that `tailoring.xml` is staged from the ISO at install time via a
  `%post --nochroot` block, and that the resulting bundle does not
  require an HTTP server.
- **`README.md`** — one line under "Other delivery modes" pointing at
  the `ks-gen iso` flow. Detail lives in MANUAL.
- **`CHANGELOG.md`** — new entry under v0.2.0 (alongside the existing
  unattended-updates entry):
  > **`hd:LABEL=` transport for oscap tailoring fetch.** The oscap
  > `%post` block is now split into a `--nochroot` fetch stage and a
  > chrooted eval stage. ISO-delivered bundles (`ks-gen iso`) now
  > reach oscap remediation at install time; previously, install
  > failed with `unsupported inst.ks transport`. HTTP delivery is
  > unchanged operator-visibly. Closes the second of the two v0.1.x
  > gaps queued before v0.2.0.

## Commit hygiene

Four logical commits (conventional commits, signed with the user's
`BE707B220C995478` key per global git config). The spec doc lands
first so the implementation commits can reference it:

1. `docs(spec): hd:LABEL= oscap transport design`
2. `feat(template): split oscap %post into --nochroot fetch + chrooted eval; add hd:LABEL= branch`
3. `test(golden): regenerate snapshots for hd: transport split` +
   `test(lint): hd:LABEL= branch invariant` (may split into two)
4. `docs: MANUAL + README + CHANGELOG + MINIMAL-TEST hd: walkthrough`

Local CI parity check (`ruff check && ruff format --check && mypy &&
pytest -q`) per `CLAUDE.md` runs before each push.

## After this lands

The first v0.1.x gap (`--fetch-remote-resources` for OVAL) is the
remaining blocker for tagging v0.2.0. That spec is small enough to
brainstorm separately in its own session.
