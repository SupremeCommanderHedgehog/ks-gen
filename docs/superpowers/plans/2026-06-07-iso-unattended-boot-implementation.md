# ISO unattended boot — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `ks-gen iso` so the output ISO boots unattended by default on both BIOS (isolinux) and UEFI (grub) paths, with the upstream AlmaLinux entries preserved below as fallback. Closes #6.

**Architecture:** Promote `src/ks_gen/iso.py` to a package. Add `iso/bootloader.py` with pure `str -> str` rewriters that prepend a new unattended entry, flip the default-entry directive, and hardcode timeout 5s. `iso/builder.py` orchestrates xorriso in three passes (extract isolinux.cfg + grub.cfg, rewrite in Python, author the output ISO).

**Tech Stack:** Python 3.11+, `re` stdlib (no parsing library), `xorriso` binary (already a dep), syrupy for golden snapshots (already in test deps).

**Spec:** [`docs/superpowers/specs/2026-06-07-iso-unattended-boot-design.md`](../specs/2026-06-07-iso-unattended-boot-design.md)

**Branch:** `feat/iso-unattended-boot` (already cut; spec committed as `f102914`)

---

## File map

| File | What | Status |
|---|---|---|
| `src/ks_gen/iso/__init__.py` | Re-exports `build_iso`, `IsoBuildError` | Create |
| `src/ks_gen/iso/builder.py` | xorriso orchestration (was `iso.py`) | Move from `iso.py`, then extend |
| `src/ks_gen/iso/bootloader.py` | Pure rewriters + `BootloaderRewriteError` | Create |
| `src/ks_gen/iso/_menu.py` | Entry-template string constants | Create |
| `tests/fixtures/alma9-bootloader/isolinux.cfg` | Hand-crafted AlmaLinux 9.6-style fixture | Create |
| `tests/fixtures/alma9-bootloader/grub.cfg` | Hand-crafted AlmaLinux 9.6-style fixture | Create |
| `tests/test_bootloader.py` | Golden snapshot + error-path tests | Create |
| `tests/test_iso.py` | Extend to cover three-pass orchestration | Modify |
| `tests/__snapshots__/test_bootloader.ambr` | syrupy snapshot (sibling of the test file) | Generated, committed |

**Note on snapshot location:** syrupy auto-creates snapshots in `<test_dir>/__snapshots__/<test_module>.ambr`. Since `test_bootloader.py` lives at `tests/test_bootloader.py`, snapshots land at `tests/__snapshots__/test_bootloader.ambr`. This matches the existing module-test pattern at `tests/__snapshots__/test_verify_report.ambr`. The `tests/golden/__snapshots__/` directory is reserved for full-pipeline scenario tests like `tests/golden/test_stig_strict.py`.
| `MANUAL.md` | Strike v0.1 ISO limitation notes | Modify §5.4, §8.3 |

---

## Conventions

- All new code uses `from __future__ import annotations` per repo style.
- Commit messages: conventional commits with scope, e.g. `feat(iso):`, `test(golden):`, `refactor(iso):`, `docs(manual):`.
- Every commit signed: prefix `git commit` calls with `-c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478` and pass `-S`. Per `~/.claude/CLAUDE.md`.
- Before pushing, run the full CI parity chain: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`. Per `CLAUDE.md`.
- Snapshot tests use syrupy; regenerate with `pytest tests/test_bootloader.py --snapshot-update`. Inspect the `.ambr` diff before committing.

---

## Task 1: Promote `iso.py` to a package (no behavior change)

**Files:**
- Create: `src/ks_gen/iso/__init__.py`
- Move: `src/ks_gen/iso.py` → `src/ks_gen/iso/builder.py`

- [ ] **Step 1: Move the file**

```bash
git mv src/ks_gen/iso.py src/ks_gen/iso/builder.py
```

- [ ] **Step 2: Create `src/ks_gen/iso/__init__.py`**

```python
from __future__ import annotations

from ks_gen.iso.builder import IsoBuildError, build_iso

__all__ = ["IsoBuildError", "build_iso"]
```

- [ ] **Step 3: Run existing tests to verify the rename was transparent**

Run: `pytest tests/test_iso.py -v`
Expected: both existing tests pass — `test_build_iso_calls_xorriso` PASS, `test_build_iso_missing_xorriso_raises` PASS.

- [ ] **Step 4: Run the full ks-gen test suite to verify no other imports broke**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/iso/
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "refactor(iso): promote iso.py to a package"
```

---

## Task 2: Add `_menu.py` constants

**Files:**
- Create: `src/ks_gen/iso/_menu.py`

- [ ] **Step 1: Write the constants**

```python
from __future__ import annotations

IDEMPOTENCY_MARKER = "# ks-gen unattended entry — do not edit"

ISOLINUX_UNATTENDED_ENTRY = """\
{marker}
label ksgen-unattended
  menu label ^Unattended STIG install (ks-gen)
  menu default
  kernel vmlinuz
  append initrd=initrd.img inst.stage2=hd:LABEL={volid} inst.ks=hd:LABEL={volid}:/ks.cfg quiet
"""

GRUB_UNATTENDED_ENTRY = """\
{marker}
menuentry 'Unattended STIG install (ks-gen)' --class fedora --class gnu-linux --class gnu --class os {{
  linuxefi /images/pxeboot/vmlinuz inst.stage2=hd:LABEL={volid} inst.ks=hd:LABEL={volid}:/ks.cfg quiet
  initrdefi /images/pxeboot/initrd.img
}}
"""
```

The `{{` / `}}` in the grub block are escaped braces for `.format()`. The `{marker}` placeholder lets the rewriter inject the idempotency marker without duplicating the literal.

- [ ] **Step 2: Sanity-check format substitution**

Run:
```bash
python -c "from ks_gen.iso._menu import ISOLINUX_UNATTENDED_ENTRY, GRUB_UNATTENDED_ENTRY, IDEMPOTENCY_MARKER; print(ISOLINUX_UNATTENDED_ENTRY.format(marker=IDEMPOTENCY_MARKER, volid='ALMA9')); print('---'); print(GRUB_UNATTENDED_ENTRY.format(marker=IDEMPOTENCY_MARKER, volid='ALMA9'))"
```

Expected: clean output with `LABEL=ALMA9` substituted; the grub block contains literal `{` and `}` around the menuentry body.

- [ ] **Step 3: Commit**

```bash
git add src/ks_gen/iso/_menu.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(iso): add unattended boot entry templates"
```

---

## Task 3: Bootloader-fixture files

**Files:**
- Create: `tests/fixtures/alma9-bootloader/isolinux.cfg`
- Create: `tests/fixtures/alma9-bootloader/grub.cfg`

These are hand-crafted AlmaLinux 9.6-style fixtures that exercise every code path of the rewriters (timeout to replace, existing `set default=`, multiple label/menuentry blocks, one block with existing `menu default`).

- [ ] **Step 1: Create the isolinux fixture**

Write `tests/fixtures/alma9-bootloader/isolinux.cfg` with **LF line endings** (`\n`, not `\r\n`):

```
default vesamenu.c32
timeout 600
display boot.msg

menu background splash.png
menu title AlmaLinux 9.6
menu vshift 8
menu rows 18
menu margin 8

label linux
  menu label ^Install AlmaLinux 9.6
  menu default
  kernel vmlinuz
  append initrd=initrd.img inst.stage2=hd:LABEL=AlmaLinux-9-6-x86_64-dvd quiet

label check
  menu label Test this ^media & install AlmaLinux 9.6
  kernel vmlinuz
  append initrd=initrd.img inst.stage2=hd:LABEL=AlmaLinux-9-6-x86_64-dvd rd.live.check quiet

menu separator

label rescue
  menu label ^Rescue an AlmaLinux system
  kernel vmlinuz
  append initrd=initrd.img inst.stage2=hd:LABEL=AlmaLinux-9-6-x86_64-dvd rescue
```

- [ ] **Step 2: Create the grub fixture**

Write `tests/fixtures/alma9-bootloader/grub.cfg` with **LF line endings**:

```
set default="1"
set timeout=60
### BEGIN /etc/grub.d/00_header ###
function load_video {
  insmod efi_gop
  insmod efi_uga
  insmod video_bochs
  insmod video_cirrus
  insmod all_video
}
load_video
set gfxpayload=keep
insmod gzio
insmod part_gpt
insmod ext2
### END /etc/grub.d/00_header ###

menuentry 'Install AlmaLinux 9.6' --class fedora --class gnu-linux --class gnu --class os {
	linuxefi /images/pxeboot/vmlinuz inst.stage2=hd:LABEL=AlmaLinux-9-6-x86_64-dvd quiet
	initrdefi /images/pxeboot/initrd.img
}
menuentry 'Test this media & install AlmaLinux 9.6' --class fedora --class gnu-linux --class gnu --class os {
	linuxefi /images/pxeboot/vmlinuz inst.stage2=hd:LABEL=AlmaLinux-9-6-x86_64-dvd rd.live.check quiet
	initrdefi /images/pxeboot/initrd.img
}
submenu 'Troubleshooting -->' {
	menuentry 'Rescue an AlmaLinux system' {
		linuxefi /images/pxeboot/vmlinuz inst.stage2=hd:LABEL=AlmaLinux-9-6-x86_64-dvd rescue
		initrdefi /images/pxeboot/initrd.img
	}
}
```

- [ ] **Step 3: Verify line endings on Windows**

Run:
```bash
python -c "import pathlib; p = pathlib.Path('tests/fixtures/alma9-bootloader/isolinux.cfg'); b = p.read_bytes(); print('CRLF count:', b.count(b'\r\n'), 'LF count:', b.count(b'\n') - b.count(b'\r\n'))"
```

Expected: `CRLF count: 0`. If non-zero, re-save with LF endings (most editors have a status-bar setting; `dos2unix` works if installed).

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/alma9-bootloader/
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(fixtures): AlmaLinux 9.6-style isolinux + grub config fixtures"
```

---

## Task 4: `bootloader.rewrite_isolinux` — happy path

**Files:**
- Create: `src/ks_gen/iso/bootloader.py`
- Create: `tests/test_bootloader.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bootloader.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from ks_gen.iso.bootloader import BootloaderRewriteError, rewrite_grub, rewrite_isolinux

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "alma9-bootloader"


def _read_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_rewrite_isolinux_happy_path(snapshot):
    result = rewrite_isolinux(_read_fixture("isolinux.cfg"), volid="ALMA9")
    assert result == snapshot
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_bootloader.py::test_rewrite_isolinux_happy_path -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ks_gen.iso.bootloader'`.

- [ ] **Step 3: Write the minimal `bootloader.py` implementation**

Create `src/ks_gen/iso/bootloader.py`:

```python
from __future__ import annotations

import re

from ks_gen.iso._menu import (
    GRUB_UNATTENDED_ENTRY,
    IDEMPOTENCY_MARKER,
    ISOLINUX_UNATTENDED_ENTRY,
)


class BootloaderRewriteError(ValueError):
    pass


def rewrite_isolinux(text: str, *, volid: str, timeout: int = 5) -> str:
    if IDEMPOTENCY_MARKER in text:
        return text

    if not re.search(r"^label\s+\S+", text, flags=re.MULTILINE):
        raise BootloaderRewriteError("no `label` keyword found in isolinux.cfg")

    text = re.sub(r"^[ \t]*menu\s+default\s*$\r?\n?", "", text, flags=re.MULTILINE)

    timeout_units = timeout * 10
    text, n = re.subn(
        r"^timeout\s+\d+\s*$",
        f"timeout {timeout_units}",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if n == 0:
        text = f"timeout {timeout_units}\n" + text

    match = re.search(r"^label\s+\S+", text, flags=re.MULTILINE)
    assert match is not None  # verified above; edits only delete `menu default`
    entry = ISOLINUX_UNATTENDED_ENTRY.format(marker=IDEMPOTENCY_MARKER, volid=volid)
    return text[: match.start()] + entry + "\n" + text[match.start() :]


def rewrite_grub(text: str, *, volid: str, timeout: int = 5) -> str:
    raise NotImplementedError  # implemented in Task 5
```

- [ ] **Step 4: Generate the initial snapshot**

Run: `pytest tests/test_bootloader.py::test_rewrite_isolinux_happy_path --snapshot-update -v`
Expected: PASS, new snapshot recorded at `tests/__snapshots__/test_bootloader.ambr`.

- [ ] **Step 5: Inspect the snapshot diff before committing**

Run: `git status tests/__snapshots__/ && git diff tests/__snapshots__/`

Verify the snapshot shows:
- A new `# ks-gen unattended entry` block before the `label linux` line.
- `timeout 50` (was `timeout 600`).
- `menu default` removed from the `label linux` block.
- The unattended block contains `inst.ks=hd:LABEL=ALMA9:/ks.cfg`.

- [ ] **Step 6: Run the test to confirm it passes against the recorded snapshot**

Run: `pytest tests/test_bootloader.py::test_rewrite_isolinux_happy_path -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/ks_gen/iso/bootloader.py tests/test_bootloader.py tests/__snapshots__/test_bootloader.ambr
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(iso): rewrite_isolinux pure rewriter + golden snapshot"
```

---

## Task 5: `bootloader.rewrite_grub` — happy path

**Files:**
- Modify: `src/ks_gen/iso/bootloader.py`
- Modify: `tests/test_bootloader.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bootloader.py`:

```python
def test_rewrite_grub_happy_path(snapshot):
    result = rewrite_grub(_read_fixture("grub.cfg"), volid="ALMA9")
    assert result == snapshot
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_bootloader.py::test_rewrite_grub_happy_path -v`
Expected: FAIL with `NotImplementedError`.

- [ ] **Step 3: Implement `rewrite_grub`**

Replace the `raise NotImplementedError` body in `src/ks_gen/iso/bootloader.py` with:

```python
def rewrite_grub(text: str, *, volid: str, timeout: int = 5) -> str:
    if IDEMPOTENCY_MARKER in text:
        return text

    if not re.search(r"^menuentry\s+", text, flags=re.MULTILINE):
        raise BootloaderRewriteError("no `menuentry` keyword found in grub.cfg")

    text, n = re.subn(
        r"^set\s+timeout=\d+\s*$",
        f"set timeout={timeout}",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if n == 0:
        text = f"set timeout={timeout}\n" + text

    text, n = re.subn(
        r'^set\s+default=.*$',
        'set default="0"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if n == 0:
        text = 'set default="0"\n' + text

    match = re.search(r"^menuentry\s+", text, flags=re.MULTILINE)
    assert match is not None  # verified above
    entry = GRUB_UNATTENDED_ENTRY.format(marker=IDEMPOTENCY_MARKER, volid=volid)
    return text[: match.start()] + entry + "\n" + text[match.start() :]
```

- [ ] **Step 4: Generate the snapshot**

Run: `pytest tests/test_bootloader.py::test_rewrite_grub_happy_path --snapshot-update -v`
Expected: PASS.

- [ ] **Step 5: Inspect the snapshot diff**

Run: `git diff tests/__snapshots__/test_bootloader.ambr`

Verify the snapshot shows:
- A new `# ks-gen unattended entry` block before the first `menuentry 'Install AlmaLinux 9.6'` line.
- `set timeout=5` (was `set timeout=60`).
- `set default="0"` (was `set default="1"`).
- The unattended block contains `inst.ks=hd:LABEL=ALMA9:/ks.cfg`.

- [ ] **Step 6: Run to confirm pass**

Run: `pytest tests/test_bootloader.py -v`
Expected: both `test_rewrite_isolinux_happy_path` and `test_rewrite_grub_happy_path` PASS.

- [ ] **Step 7: Commit**

```bash
git add src/ks_gen/iso/bootloader.py tests/test_bootloader.py tests/__snapshots__/test_bootloader.ambr
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(iso): rewrite_grub pure rewriter + golden snapshot"
```

---

## Task 6: Idempotency tests

**Files:**
- Modify: `tests/test_bootloader.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bootloader.py`:

```python
def test_rewrite_isolinux_idempotent():
    original = _read_fixture("isolinux.cfg")
    once = rewrite_isolinux(original, volid="ALMA9")
    twice = rewrite_isolinux(once, volid="ALMA9")
    assert once == twice


def test_rewrite_grub_idempotent():
    original = _read_fixture("grub.cfg")
    once = rewrite_grub(original, volid="ALMA9")
    twice = rewrite_grub(once, volid="ALMA9")
    assert once == twice
```

- [ ] **Step 2: Run to verify they already pass (the marker check is in place)**

Run: `pytest tests/test_bootloader.py -v -k idempotent`
Expected: PASS for both. (If not, the `IDEMPOTENCY_MARKER in text` early-return in `bootloader.py` is broken — debug before continuing.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_bootloader.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(iso): bootloader rewriters are idempotent"
```

---

## Task 7: Error-path tests

**Files:**
- Modify: `tests/test_bootloader.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bootloader.py`:

```python
def test_rewrite_isolinux_no_label_raises():
    with pytest.raises(BootloaderRewriteError, match="label"):
        rewrite_isolinux("default vesamenu.c32\ntimeout 600\n", volid="ALMA9")


def test_rewrite_grub_no_menuentry_raises():
    with pytest.raises(BootloaderRewriteError, match="menuentry"):
        rewrite_grub("set timeout=60\n", volid="ALMA9")
```

- [ ] **Step 2: Run to verify they pass**

Run: `pytest tests/test_bootloader.py -v -k raises`
Expected: both PASS (the implementation already raises `BootloaderRewriteError` when the anchor is missing).

- [ ] **Step 3: Commit**

```bash
git add tests/test_bootloader.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(iso): bootloader rewriters raise on missing anchor"
```

---

## Task 8: Custom-volid propagation tests

**Files:**
- Modify: `tests/test_bootloader.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_bootloader.py`:

```python
def test_rewrite_isolinux_custom_volid():
    result = rewrite_isolinux(_read_fixture("isolinux.cfg"), volid="WEB01")
    assert "inst.ks=hd:LABEL=WEB01:/ks.cfg" in result
    assert "inst.stage2=hd:LABEL=WEB01" in result


def test_rewrite_grub_custom_volid():
    result = rewrite_grub(_read_fixture("grub.cfg"), volid="WEB01")
    assert "inst.ks=hd:LABEL=WEB01:/ks.cfg" in result
    assert "inst.stage2=hd:LABEL=WEB01" in result
```

- [ ] **Step 2: Run to verify they pass**

Run: `pytest tests/test_bootloader.py -v -k custom_volid`
Expected: both PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_bootloader.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(iso): bootloader rewriters propagate custom volid"
```

---

## Task 9: `builder.build_iso` — three-pass xorriso flow

**Files:**
- Modify: `src/ks_gen/iso/builder.py`
- Modify: `tests/test_iso.py`

- [ ] **Step 1: Update the existing happy-path test for the three-pass shape**

Replace the body of `test_build_iso_calls_xorriso` in `tests/test_iso.py` with:

```python
def test_build_iso_calls_xorriso(tmp_path):
    src = tmp_path / "src.iso"
    src.write_bytes(b"\0" * 1024)
    ks = tmp_path / "ks.cfg"
    ks.write_text("text\n", encoding="utf-8")
    tail = tmp_path / "tailoring.xml"
    tail.write_text("<x/>", encoding="utf-8")
    out = tmp_path / "out.iso"

    def fake_run(args, **kwargs):
        # Simulate xorriso -extract by writing a tiny config to the dest path.
        if "-extract" in args:
            idx = args.index("-extract")
            dest = Path(args[idx + 2])
            if "isolinux.cfg" in args[idx + 1]:
                dest.write_text("timeout 600\nlabel linux\n  kernel vmlinuz\n", encoding="utf-8")
            else:
                dest.write_text(
                    "set timeout=60\nmenuentry 'foo' { linuxefi vmlinuz\ninitrdefi initrd.img\n}\n",
                    encoding="utf-8",
                )
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        return result

    with (
        patch("ks_gen.iso.builder.shutil.which", return_value="/usr/bin/xorriso"),
        patch("ks_gen.iso.builder.subprocess.run", side_effect=fake_run) as run,
    ):
        build_iso(src, ks, tail, out, volid="ALMA9")

    # Three xorriso passes: extract isolinux, extract grub, final author
    assert run.call_count == 3
    extract_calls = [c for c in run.call_args_list if "-extract" in c.args[0]]
    author_calls = [c for c in run.call_args_list if "replay" in c.args[0]]
    assert len(extract_calls) == 2
    assert len(author_calls) == 1

    # Final author maps all four files
    final_args = author_calls[0].args[0]
    assert "/isolinux/isolinux.cfg" in final_args
    assert "/EFI/BOOT/grub.cfg" in final_args
    assert "/ks.cfg" in final_args
    assert "/tailoring.xml" in final_args
```

Also add the new imports at the top of `tests/test_iso.py` (above the existing `from unittest.mock import patch`):

```python
from pathlib import Path
from unittest.mock import MagicMock, patch
```

(Remove the old `from unittest.mock import patch` line — replaced by the combined import above.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_iso.py::test_build_iso_calls_xorriso -v`
Expected: FAIL (single xorriso call, not three; no extract calls).

- [ ] **Step 3: Implement the three-pass `build_iso`**

Replace the body of `src/ks_gen/iso/builder.py` with:

```python
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from ks_gen.iso.bootloader import (
    BootloaderRewriteError,
    rewrite_grub,
    rewrite_isolinux,
)


class IsoBuildError(Exception):
    pass


def build_iso(
    src_iso: Path,
    ks_cfg: Path,
    tailoring_xml: Path,
    out_iso: Path,
    *,
    volid: str,
) -> None:
    if shutil.which("xorriso") is None:
        raise IsoBuildError(
            "xorriso not on PATH (install: dnf install xorriso / brew install xorriso)"
        )

    with tempfile.TemporaryDirectory(prefix="ks-gen-iso-") as tmp:
        tmp_path = Path(tmp)
        iso_isolinux = tmp_path / "isolinux.cfg"
        iso_grub = tmp_path / "grub.cfg"

        _extract(src_iso, "/isolinux/isolinux.cfg", iso_isolinux)
        _extract(src_iso, "/EFI/BOOT/grub.cfg", iso_grub)

        try:
            iso_isolinux.write_text(
                rewrite_isolinux(
                    iso_isolinux.read_text(encoding="utf-8"), volid=volid
                ),
                encoding="utf-8",
            )
            iso_grub.write_text(
                rewrite_grub(
                    iso_grub.read_text(encoding="utf-8"), volid=volid
                ),
                encoding="utf-8",
            )
        except BootloaderRewriteError as e:
            raise IsoBuildError(f"bootloader rewrite aborted: {e}") from e

        _author(src_iso, out_iso, volid, ks_cfg, tailoring_xml, iso_isolinux, iso_grub)


def _extract(src_iso: Path, iso_path: str, dest: Path) -> None:
    args = [
        "xorriso",
        "-indev",
        str(src_iso),
        "-osirrox",
        "on",
        "-extract",
        iso_path,
        str(dest),
    ]
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0 or not dest.exists():
        raise IsoBuildError(
            f"source ISO missing {iso_path} — not an AlmaLinux 9 DVD? "
            f"(xorriso: {result.stderr.strip()})"
        )


def _author(
    src_iso: Path,
    out_iso: Path,
    volid: str,
    ks_cfg: Path,
    tailoring_xml: Path,
    isolinux_cfg: Path,
    grub_cfg: Path,
) -> None:
    args = [
        "xorriso",
        "-indev",
        str(src_iso),
        "-outdev",
        str(out_iso),
        "-boot_image",
        "any",
        "replay",
        "-volid",
        volid,
        "-map",
        str(isolinux_cfg),
        "/isolinux/isolinux.cfg",
        "-map",
        str(grub_cfg),
        "/EFI/BOOT/grub.cfg",
        "-map",
        str(ks_cfg),
        "/ks.cfg",
        "-map",
        str(tailoring_xml),
        "/tailoring.xml",
        "-chmod",
        "0444",
        "/ks.cfg",
        "/tailoring.xml",
        "/isolinux/isolinux.cfg",
        "/EFI/BOOT/grub.cfg",
        "--",
    ]
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise IsoBuildError(f"xorriso failed: {result.stderr}")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_iso.py -v`
Expected: both existing tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/iso/builder.py tests/test_iso.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(iso): three-pass xorriso flow (extract, rewrite, author)"
```

---

## Task 10: Builder failure-mode tests

**Files:**
- Modify: `tests/test_iso.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_iso.py`:

```python
def test_build_iso_extract_fails_raises(tmp_path):
    src = tmp_path / "src.iso"
    src.write_bytes(b"\0")
    ks = tmp_path / "ks.cfg"
    ks.write_text("x", encoding="utf-8")
    tail = tmp_path / "t.xml"
    tail.write_text("x", encoding="utf-8")
    out = tmp_path / "out.iso"

    def fake_run(args, **kwargs):
        result = MagicMock()
        if "-extract" in args:
            result.returncode = 1
            result.stderr = "isofs: file not found"
        else:
            result.returncode = 0
            result.stderr = ""
        return result

    with (
        patch("ks_gen.iso.builder.shutil.which", return_value="/usr/bin/xorriso"),
        patch("ks_gen.iso.builder.subprocess.run", side_effect=fake_run),
        pytest.raises(IsoBuildError, match="source ISO missing"),
    ):
        build_iso(src, ks, tail, out, volid="ALMA9")


def test_build_iso_rewrite_error_raises(tmp_path):
    src = tmp_path / "src.iso"
    src.write_bytes(b"\0")
    ks = tmp_path / "ks.cfg"
    ks.write_text("x", encoding="utf-8")
    tail = tmp_path / "t.xml"
    tail.write_text("x", encoding="utf-8")
    out = tmp_path / "out.iso"

    def fake_run(args, **kwargs):
        if "-extract" in args:
            idx = args.index("-extract")
            dest = Path(args[idx + 2])
            # Write content that has no `label` / `menuentry` keyword
            dest.write_text("timeout 600\n", encoding="utf-8")
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        return result

    with (
        patch("ks_gen.iso.builder.shutil.which", return_value="/usr/bin/xorriso"),
        patch("ks_gen.iso.builder.subprocess.run", side_effect=fake_run),
        pytest.raises(IsoBuildError, match="bootloader rewrite aborted"),
    ):
        build_iso(src, ks, tail, out, volid="ALMA9")
```

Also add `import pytest` at the top of `tests/test_iso.py` if not already present.

- [ ] **Step 2: Run the tests to verify they pass**

Run: `pytest tests/test_iso.py -v`
Expected: all four tests PASS — original two + two new failure tests.

- [ ] **Step 3: Commit**

```bash
git add tests/test_iso.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(iso): builder raises IsoBuildError on extract + rewrite failures"
```

---

## Task 11: Update `MANUAL.md`

**Files:**
- Modify: `MANUAL.md` — sections §5.4 and §8.3

- [ ] **Step 1: Locate the v0.1 limitation note in §5.4**

Run: `grep -n "v0.1 limitation" MANUAL.md`

Expected: lines around §5.4 (mentioned at MANUAL.md:705 in current state) and §8.3 (around MANUAL.md:937).

- [ ] **Step 2: Update §5.4**

In `MANUAL.md`, find the block starting `**v0.1 limitation:** the wrapper places the files at the ISO root but does NOT rewrite ...` (approximately lines 705-714). Replace it with:

```
**Unattended boot:** the wrapper rewrites `isolinux/isolinux.cfg` and
`EFI/BOOT/grub.cfg` to add a top-level "Unattended STIG install
(ks-gen)" entry, set it as the default, and shorten the timeout to
5 seconds. The original "Install AlmaLinux 9" entry is preserved
below as a fallback — arrow-down to recover the interactive flow.
Both BIOS (isolinux) and UEFI (grub) paths are rewritten.
```

- [ ] **Step 3: Update §8.3**

In `MANUAL.md` §8.3 ("Embedded in a custom ISO"), find the line `### 8.3 Embedded in a custom ISO (v0.1 limitation)` and the prompt instructions that follow ("press Tab", "press Ctrl-X" — around lines 937-955). Replace the section heading to drop "(v0.1 limitation)" and rewrite the instruction block:

```
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
```

(Preserve the surrounding markdown structure — keep the codefence right, keep section anchors.)

- [ ] **Step 4: Search-replace any remaining `v0.1 limitation` references in MANUAL.md**

Run: `grep -n "v0.1 limitation" MANUAL.md`

Expected: no matches after the edits above. If any remain, address them in-place.

- [ ] **Step 5: Commit**

```bash
git add MANUAL.md
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "docs(manual): document unattended ISO boot, strike v0.1 limitation"
```

---

## Task 12: Update project memory

**Files:**
- Modify: `C:\Users\yizshachuck\.claude\projects\C--Users-yizshachuck-source-alma-linux-security\memory\project_ks_gen.md`

- [ ] **Step 1: Read the current memory file to understand its format**

Read the file. It is project status memory updated over the life of the project.

- [ ] **Step 2: Append (or update) a line noting the ISO bootloader gap closure**

Add a bullet to the file (or update existing v0.1 limitation language) along the lines of:

```
- v0.2.0 closed the ISO bootloader gap (#6, 2026-06-07): `ks-gen iso` now rewrites isolinux.cfg + grub.cfg to add a default "Unattended STIG install" entry, 5s timeout, upstream entries preserved as fallback.
```

Match the existing memory file's bullet style. If the file already references the v0.1 ISO limitation as "open", update that line to "closed in v0.2.0" rather than adding a duplicate.

- [ ] **Step 3: No commit needed**

Memory files live outside the repo and are not tracked by git for this project.

---

## Task 13: Local CI parity check + push + PR

- [ ] **Step 1: Run the CI parity chain**

Run: `ruff check src tests && ruff format --check src tests && mypy && pytest -q`
Expected: all four gates pass. Total test count should be the original 374 plus ~10 new bootloader/iso tests (≈384).

If `ruff format --check` flags anything, fix with `ruff format src tests`, then re-run the check, then commit as `style:`.

- [ ] **Step 2: Verify all commits on the branch are signed**

Run: `git log --format="%h %G? %s" origin/main..HEAD`
Expected: every line starts with the short SHA and `G` (good signature).

- [ ] **Step 3: Push the branch**

```bash
git push -u origin feat/iso-unattended-boot
```

- [ ] **Step 4: Open a PR**

```bash
gh pr create --title "feat(iso): unattended boot — rewrite isolinux + grub" --body "$(cat <<'EOF'
## Summary

- Promote `iso.py` to a package; add `bootloader.py` with pure str -> str rewriters for `isolinux.cfg` and `grub.cfg`.
- `ks-gen iso` now extracts the two boot configs from the source ISO, prepends a default `Unattended STIG install (ks-gen)` entry, shortens the timeout to 5 seconds, and writes the rewritten configs back during the same xorriso author pass.
- Upstream "Install AlmaLinux 9" / "Test this media" entries preserved below as fallback.
- Rewriters are idempotent (re-run on a rewritten ISO is a no-op).

## Test plan

- [ ] CI green (ruff + format + mypy + pytest).
- [ ] Manual smoke: `ks-gen iso ... && qemu-system-x86_64 -boot d -cdrom <out>` proceeds straight to unattended install on BIOS.
- [ ] Manual smoke: `ks-gen iso ... && qemu-system-x86_64 -bios OVMF.fd -cdrom <out>` proceeds straight to unattended install on UEFI.
- [ ] Hyper-V Secure Boot acceptance (one-off): boot the same ISO with SB enabled, confirm unattended path still runs.

Closes #6.
EOF
)"
```

- [ ] **Step 5: Verify CI on the PR**

Wait for the CI runs to complete, then:

Run: `gh pr checks $(gh pr view --json number -q .number)`
Expected: ruff PASS, test (3.11) PASS, test (3.12) PASS, test (3.13) PASS.

If any check fails, investigate, fix, push another commit (signed), repeat.

---

## Out of scope (defer to follow-up issues)

- `--timeout` / `--label` CLI flags. Hardcoded 5s timeout; volid already configurable via `--volid`. Add later if requested.
- `--no-rewrite-bootloader` opt-out flag. Add later if a use case appears.
- Non-Alma RHEL-family ISOs (Rocky, RHEL, CentOS). Rewriters are likely to work but not promised.
- Hyper-V Secure Boot automated test. Worth a one-off manual check before tagging v0.2 but out of scope for CI.

---

## Self-review notes (post-write)

- ✅ Spec coverage: every section of the spec maps to at least one task.
- ✅ No placeholders: every step has concrete code, exact paths, exact commands.
- ✅ Type consistency: `rewrite_isolinux`, `rewrite_grub`, `BootloaderRewriteError`, `IDEMPOTENCY_MARKER`, `ISOLINUX_UNATTENDED_ENTRY`, `GRUB_UNATTENDED_ENTRY`, `IsoBuildError`, `build_iso` are referenced consistently across tasks.
- ✅ Each task ends with a commit.
- ✅ TDD: every code task writes failing test first, runs to confirm failure, implements, runs to confirm pass.
- ⚠ Fixture line endings on Windows: Task 3 includes an explicit byte-count check because git's autocrlf default would otherwise convert `\n` -> `\r\n` and break the snapshot tests. If the team adds `.gitattributes` with `*.cfg text eol=lf` later, the byte-count check becomes redundant but harmless.
