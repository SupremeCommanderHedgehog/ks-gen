# alma8 phase 3 — ISO bootloader rewriter verification

**Parent:** #121 (AlmaLinux 8 support tracking issue).
**Previous phases:** phase 1 (schema + dispatch, v0.25.0), phase 2 (rule re-exports, v0.26.0).

## Goal

Verify `src/ks_gen/iso/bootloader.py` correctly rewrites AlmaLinux 8 ISO bootloader configs (`isolinux/isolinux.cfg` + `EFI/BOOT/grub.cfg`) to produce a working unattended-install entry. Phase 3 closes #121's Q5 ("ISO builder bootloader rewriter — verify the existing rewriters handle both, or extend with version-specific anchors").

## Why this is mostly verification (probably no code change)

Inspection of `bootloader.py`'s regexes shows they pin **keywords**, not version strings:

| Site | Pattern | What it matches |
|---|---|---|
| `rewrite_isolinux` entry-presence check | `^label\s+\S+` | Any isolinux label entry |
| `rewrite_isolinux` menu-default cleanup | `^[ \t]*menu\s+default\s*$` | Any `menu default` directive (handles 0-or-1 hits) |
| `rewrite_isolinux` timeout edit | `^timeout\s+\d+\s*$` | Any `timeout NNN` directive (prepended if absent) |
| `rewrite_grub` entry-presence check | `^menuentry\s+` | Any grub menuentry |
| `rewrite_grub` timeout edit | `^set\s+timeout=\d+\s*$` | Any `set timeout=NNN` (prepended if absent) |
| `rewrite_grub` default-entry edit | `^set\s+default=.*$` | Any `set default=...` (prepended if absent) |

None of these depend on AlmaLinux **version** strings. AL8 isolinux/grub configs use the same isolinux/grub2 syntax as AL9 — only the volid labels, version display strings, and product banners differ.

Also distro-agnostic:
- `_menu.py`'s `ISOLINUX_UNATTENDED_ENTRY` and `GRUB_UNATTENDED_ENTRY` templates use `vmlinuz` / `initrd.img` / `/images/pxeboot/vmlinuz` paths — these are stable across AL8 and AL9 ISO layouts.
- `builder.py`'s `volid: str` parameter passes through unchanged — the CLI takes the volid and the bootloader rewriter applies it byte-for-byte.

**Expected outcome:** Existing AL9 tests stay green, new AL8 tests pass against synthetic AL8.10-shaped fixtures, no code changes to `bootloader.py` or `_menu.py`.

**If something breaks:** investigate per-test which anchor failed, narrow the fix to that anchor. Don't preemptively over-generalize.

## Files touched

- **Create:** `tests/fixtures/alma8-bootloader/isolinux.cfg` — synthetic AL8.10-shaped isolinux config.
- **Create:** `tests/fixtures/alma8-bootloader/grub.cfg` — synthetic AL8.10-shaped grub config.
- **Modify:** `tests/test_bootloader.py` — add parallel tests mirroring the existing AL9 happy-path + idempotency + custom-volid coverage, parameterized over the fixture dir.
- **Modify (snapshot):** `tests/__snapshots__/test_bootloader.ambr` — new snapshots for the AL8 happy-path tests.

## Synthetic AL8 fixtures — what differs from AL9

Pattern-level: nothing. Both use isolinux 6.x + grub2.

Surface-level (the differences I'll capture in the fixtures):
- Display strings: `Install AlmaLinux 8.10` instead of `Install AlmaLinux 9.6`.
- Volume ID labels in `inst.stage2=hd:LABEL=...`: `AlmaLinux-8-10-x86_64-dvd` instead of `AlmaLinux-9-6-x86_64-dvd`.
- `menu title` and product banner: `AlmaLinux 8.10` instead of `AlmaLinux 9.6`.
- Otherwise byte-for-byte identical structure to the AL9 fixtures.

The synthetic fixtures are **representative** of AL8 ISO content — real-world validation against a freshly-mounted AL8.10 DVD ISO is part of phase 4 install testing.

## Tests (4 new)

1. `test_rewrite_isolinux_happy_path_al8(snapshot)` — runs `rewrite_isolinux` against the AL8 fixture with `volid="ALMA8"`, syrupy-snapshots the result.
2. `test_rewrite_grub_happy_path_al8(snapshot)` — runs `rewrite_grub` against the AL8 fixture with `volid="ALMA8"`, syrupy-snapshots the result.
3. `test_rewrite_isolinux_al8_idempotent` — runs rewriter twice, asserts second call no-ops.
4. `test_rewrite_grub_al8_idempotent` — runs rewriter twice, asserts second call no-ops.

Existing AL9 tests stay unchanged. The factoring choice: parallel test functions (matches the current file's structure) rather than a single parameterized test — keeps per-fixture snapshots distinct and failure messages clear.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Real AL8.10 ISO has a structural quirk the synthetic fixture doesn't capture | Phase 4 install-regression validation surfaces it; if found, add a real-fixture-based test then. |
| `linuxefi`/`initrdefi` keywords in the unattended entry template are deprecated on newer grub2 | The unattended entry's `linuxefi` is the same on AL8 and AL9 — if either deprecates it, that's a separate issue affecting both distros, not an alma8-specific phase-3 concern. |
| Fixture maintenance burden grows as ISO content drifts | Acceptable: bootloader configs evolve slowly (years between meaningful drift). Replace fixtures when a regression surfaces. |
| Custom-volid case for AL8 not separately tested | The existing AL9 custom-volid test covers the volid plumbing through to the entry — the volid is the same `str` parameter regardless of distro. Adding a redundant AL8 custom-volid test would be ceremonial. |

## CI parity check before push

```bash
ruff check src tests \
  && ruff format --check src tests \
  && mypy \
  && pytest -q
```

Expected new test count: 929 + 4 = 933 (4 new bootloader tests, no other changes).

## Out of scope (phase 3 only)

- Real-world validation against a mounted AL8.10 DVD ISO — phase 4 work.
- `ks-gen iso --distro` flag — not needed; `volid` is the only per-ISO-version variable and it's already configurable via the CLI flag.
- Custom-volid AL8 test — redundant with existing AL9 coverage.
- AL10 bootloader fixture work — file a separate issue when AL10 lands.
- Refactoring the rewriter to be more distro-aware — the current keyword-based regexes are correctly distro-agnostic; no refactor needed.
