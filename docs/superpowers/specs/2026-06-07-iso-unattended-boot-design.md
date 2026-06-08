# ISO unattended boot — design

**Issue:** [#6 — ks-gen iso: rewrite isolinux/grub so the kickstart entry boots unattended](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/6)

**Status:** approved 2026-06-07

**Goal:** Make `ks-gen iso` produce a self-booting installer ISO: the
default boot entry passes `inst.ks=hd:LABEL=<volid>:/ks.cfg`
automatically with a short timeout, with the upstream AlmaLinux
entries preserved as fallback. Closes the v0.1 limitation called out
in `MANUAL.md` §5.4 and §8.3.

## Background

`ks-gen iso` currently injects `ks.cfg` and `tailoring.xml` at the ISO
root via `xorriso -map`, but does not touch `isolinux/isolinux.cfg` or
`EFI/BOOT/grub.cfg`. The operator still has to type
`inst.ks=hd:LABEL=ALMA9:/ks.cfg` at the Anaconda boot prompt, which
defeats the unattended-install story for anyone deploying off bare
media (USB, IPMI virtual media, hypervisor-attached ISO). The existing
`build_iso(...)` signature already reserves a `keep_original_default:
bool = False` parameter as a placeholder for this work.

## Goals

- Default boot entry boots into the unattended STIG install with no
  keystrokes on both BIOS (isolinux) and UEFI (grub) paths.
- Upstream AlmaLinux entries ("Install AlmaLinux 9", "Test this media
  & install AlmaLinux 9", troubleshooting submenu) preserved verbatim
  below the new entry — operator can arrow-down to the original
  interactive flow if they need to recover.
- Rewrite logic is version-tolerant against minor upstream AlmaLinux
  isolinux/grub config tweaks — match on structural anchors (the first
  `label` / `menuentry` keyword), not on hard-coded line numbers or
  upstream text.
- Idempotent: re-running `ks-gen iso` on an already-rewritten ISO
  produces the same output (so a re-run after a `ks.cfg` change
  doesn't stack a second unattended entry).
- Pure-function rewriters fully unit-tested via golden snapshots; the
  `xorriso` orchestration tested via `subprocess.run` mocks.

## Non-goals (deferred)

- Configurable boot timeout — hardcoded 5s for v0.2. Future
  `--timeout` CLI flag is trivial to add if anyone asks.
- Opt-out flag (`--no-rewrite-bootloader`) — not adding until there's
  a use case. The injected `ks.cfg` still works with the original
  interactive flow because the upstream entries are preserved.
- Non-Alma RHEL-family ISOs (Rocky, RHEL, CentOS) — the rewriters
  should work on these in practice (Anaconda config files are nearly
  identical across the family), but we don't promise it. Acceptance
  is AlmaLinux 9 only.
- Secure Boot signature validation — `grub.cfg` is unsigned config, so
  the rewrite doesn't break SB. A Hyper-V SB-enabled smoke test is
  worth running once manually before tagging v0.2, but it's not
  part of this design.

## Architecture

```
src/ks_gen/iso/
├── __init__.py        # re-exports build_iso, IsoBuildError
├── builder.py         # was iso.py — xorriso orchestration
├── bootloader.py      # pure str -> str rewriters
└── _menu.py           # new-entry templates (constants)
```

The existing flat `src/ks_gen/iso.py` is promoted to a package because
`builder.py` grows non-trivially (three xorriso passes instead of one,
temp-dir lifecycle) and `bootloader.py` is genuinely a separate concern
worth isolating for testing. The package's `__init__.py` re-exports
`build_iso` and `IsoBuildError` so external callers (`cli.py`,
`tests/test_iso.py`) don't need import changes.

## Component design

### `bootloader.py` — pure rewriters

Two pure functions, no I/O:

```python
def rewrite_isolinux(text: str, *, volid: str, timeout: int = 5) -> str: ...
def rewrite_grub(text: str, *, volid: str, timeout: int = 5) -> str: ...
```

Plus one shared error type:

```python
class BootloaderRewriteError(ValueError): ...
```

**`rewrite_isolinux`** does three things:

1. Replace the `timeout NNN` line at file scope (units are 1/10 sec, so
   `timeout 50` = 5s). If no `timeout` line exists, insert one near
   the top of the file.
2. Strip any existing `menu default` directive from every label block
   (only one entry can be default).
3. Prepend a new `label ksgen-unattended` block at the start of the
   labels section (above the first `label` keyword), including
   `menu default` and a kernel `append` line containing
   `inst.stage2=hd:LABEL=<volid> inst.ks=hd:LABEL=<volid>:/ks.cfg quiet`.

**`rewrite_grub`** does three things:

1. Replace the `set timeout=N` line. If absent, insert near the top.
2. Replace `set default=...` with `set default="0"`. If absent, insert
   near the top.
3. Prepend a new `menuentry 'Unattended STIG install (ks-gen)'` block
   before the first existing `menuentry` line, with `linuxefi
   /images/pxeboot/vmlinuz inst.stage2=hd:LABEL=<volid>
   inst.ks=hd:LABEL=<volid>:/ks.cfg quiet` and `initrdefi
   /images/pxeboot/initrd.img`.

Both rewriters:

- Anchor on the first `label` (isolinux) or `menuentry` (grub) keyword
  to locate the insertion point.
- Raise `BootloaderRewriteError` if no such anchor exists — caller
  must surface this as `IsoBuildError`.
- Are **idempotent**: detect their own prepended block by the literal
  marker `# ks-gen unattended entry — do not edit` placed in a comment
  above the inserted block. If the marker is present, no-op and return
  the input unchanged.

### `_menu.py` — entry templates

Two module-level string constants:

```python
ISOLINUX_UNATTENDED_ENTRY = """\
# ks-gen unattended entry — do not edit
label ksgen-unattended
  menu label ^Unattended STIG install (ks-gen)
  menu default
  kernel vmlinuz
  append initrd=initrd.img inst.stage2=hd:LABEL={volid} inst.ks=hd:LABEL={volid}:/ks.cfg quiet
"""

GRUB_UNATTENDED_ENTRY = """\
# ks-gen unattended entry — do not edit
menuentry 'Unattended STIG install (ks-gen)' --class fedora --class gnu-linux --class gnu --class os {{
  linuxefi /images/pxeboot/vmlinuz inst.stage2=hd:LABEL={volid} inst.ks=hd:LABEL={volid}:/ks.cfg quiet
  initrdefi /images/pxeboot/initrd.img
}}
"""
```

Kept as constants so the snapshot tests are diffed against a stable
source of truth, and `bootloader.py` stays focused on the str-rewrite
logic.

### `builder.py` — xorriso orchestration

Three-pass operation:

1. **Extract** the two boot configs from `src_iso` into a `tempfile.TemporaryDirectory()`:
   ```
   xorriso -indev <src> -osirrox on -extract /isolinux/isolinux.cfg <tmp>/isolinux.cfg
   xorriso -indev <src> -osirrox on -extract /EFI/BOOT/grub.cfg     <tmp>/grub.cfg
   ```
2. **Rewrite** in pure Python via `bootloader.rewrite_isolinux(...)`,
   `bootloader.rewrite_grub(...)`, writing the result back over the
   temp files.
3. **Author** the output ISO in a single xorriso call, mapping the
   four files (ks.cfg, tailoring.xml, rewritten isolinux.cfg,
   rewritten grub.cfg) and replaying El Torito + UEFI boot:
   ```
   xorriso -indev <src> -outdev <out>
     -boot_image any replay
     -volid <volid>
     -map <tmp>/isolinux.cfg /isolinux/isolinux.cfg
     -map <tmp>/grub.cfg     /EFI/BOOT/grub.cfg
     -map <ks.cfg>           /ks.cfg
     -map <tailoring.xml>    /tailoring.xml
     -chmod 0444 /ks.cfg /tailoring.xml /isolinux/isolinux.cfg /EFI/BOOT/grub.cfg
     --
   ```

The single author pass keeps the output atomic — if it fails, no
half-written `out.iso` is left behind. Temp dir is removed via the
context manager regardless of outcome.

The `keep_original_default: bool = False` parameter on `build_iso` is
removed (it was an unused placeholder for this work — the new design
always rewrites because Q1 settled on the "new entry as default, keep
originals" shape, which doesn't need a toggle).

## Failure modes

All wrapped in `IsoBuildError` (exit code 5, matching the existing
`TOOL_MISSING` convention):

| Condition | Message |
|---|---|
| `xorriso` not on PATH | (existing) "xorriso not on PATH (install: dnf install xorriso / brew install xorriso)" |
| Extract fails (config missing) | "source ISO missing /isolinux/isolinux.cfg or /EFI/BOOT/grub.cfg — not an AlmaLinux 9 DVD?" |
| `BootloaderRewriteError` from rewriter | "could not locate boot entries in <file> — bootloader rewrite aborted: <reason>" |
| Final author pass fails | (existing) "xorriso failed: <stderr>" |

## Testing

### `tests/fixtures/alma9-bootloader/`

- `isolinux.cfg` — verbatim copy from the current AlmaLinux 9.6 x86_64 DVD ISO.
- `grub.cfg` — verbatim copy from the same ISO.

These are small text files (a few KB each) and don't bloat the repo.

### `tests/test_bootloader.py`

Pure-function golden snapshot tests via `syrupy`, matching the existing pattern at `tests/golden/`:

- `test_rewrite_isolinux_happy_path` — rewrites the fixture, snapshots the result.
- `test_rewrite_grub_happy_path` — same for grub.
- `test_rewrite_isolinux_idempotent` — rewrites the already-rewritten output, asserts identical to the first rewrite (idempotency via the marker comment).
- `test_rewrite_grub_idempotent` — same for grub.
- `test_rewrite_isolinux_no_label_raises` — feed in text with no `label` keyword, assert `BootloaderRewriteError`.
- `test_rewrite_grub_no_menuentry_raises` — same for grub.
- `test_rewrite_isolinux_custom_volid` — assert `inst.ks=hd:LABEL=WEB01` propagates when `volid="WEB01"`.
- `test_rewrite_grub_custom_volid` — same for grub.

Snapshots land at `tests/golden/__snapshots__/test_bootloader.ambr`.

### `tests/test_iso.py`

Extend the existing mock pattern:

- Existing `test_build_iso_calls_xorriso` — update to expect **three** `subprocess.run` calls (extract isolinux, extract grub, final author) and assert the final author command has all four `-map` pairs.
- Existing `test_build_iso_missing_xorriso_raises` — unchanged.
- New `test_build_iso_extract_fails_raises` — mock `subprocess.run` to return non-zero on the first extract call, assert `IsoBuildError` surfaces with the "source ISO missing …" message.
- New `test_build_iso_rewrite_error_raises` — patch `bootloader.rewrite_isolinux` to raise `BootloaderRewriteError`, assert `IsoBuildError` with the "could not locate boot entries …" message.

No real ISOs in the repo. CI stays fast and deterministic.

## Docs updates

- `MANUAL.md` §5.4 (`ks-gen iso`): remove the "v0.1 limitation" callout and the manual `inst.ks=…` instructions. Replace with: "the new ISO boots the unattended STIG install by default after a 5s timeout; arrow-down to the original 'Install AlmaLinux 9' entry for the interactive flow."
- `MANUAL.md` §8.3 ("Embedded in a custom ISO"): strike the "v0.1 limitation" subtitle and the press-Tab/press-Ctrl-X instructions; describe the new default-entry behavior.
- Memory: update `project_ks_gen.md` to note that the ISO bootloader gap is closed.

## Risks

- **AlmaLinux config format drift across point releases.** The
  rewriter anchors on `label` / `menuentry` keywords, which are
  structural and unlikely to change. The boot path locations
  (`/isolinux/isolinux.cfg`, `/EFI/BOOT/grub.cfg`) are stable across
  the RHEL 9 family. If upstream restructures (e.g., moves to BLS
  config snippets), the rewriter will hard-fail at the extract step,
  which is a loud failure mode, not a silent one.
- **Idempotency marker collision.** If the upstream `isolinux.cfg`
  ever ships a comment containing the literal "ks-gen unattended
  entry — do not edit", we'd no-op on a fresh ISO. Vanishingly
  unlikely given the string, but the marker is specific enough that
  a single grep would reveal a collision before tagging.

## Acceptance

(From the issue:)

- [ ] `ks-gen iso ... && qemu/Hyper-V boot from result` proceeds to unattended install with no keystrokes.
- [ ] Original "Install AlmaLinux" menu entry still available as a fallback (arrow-down once).
- [ ] Both BIOS (isolinux) and UEFI (grub) boot paths exercised in the smoke test.
- [ ] `ruff check && ruff format --check && mypy && pytest -q` green.
- [ ] Snapshot diffs for `tests/golden/__snapshots__/test_bootloader.ambr` reviewed and committed.
