#!/usr/bin/env python3
"""Emulate a Rufus "ISO Image mode" USB write of a ks-gen installer (#134).

Usage: rufus-iso-stick.py <installer.iso> <out.raw>

MANUAL §8.6 tells Windows operators to write the installer with Rufus in ISO
Image mode: an MBR stick with one FAT32 partition, the ISO9660 tree copied
onto it file by file, and Rufus's own edits to the boot configs. On UEFI the
FAT32 partition is what firmware boots, so `/EFI/BOOT/BOOTX64.EFI` reads the
TREE's `/EFI/BOOT/grub.cfg`. The EFI image the dd/CD paths boot from is never
used. This rebuilds that stick without Windows, following Rufus v4.15
(github.com/pbatard/rufus, tag v4.15, 6d8fbf98). The function docstrings
cite the source each step mirrors. What it does not reproduce:

- BIOS/legacy boot. Rufus installs its own syslinux/GRUB there; this stick
  boots UEFI only.
- The `SizeToHumanReadable` fallback label for labels that come out mostly
  underscores. Approximated, and never reached by a ks-gen default.
- The FreeNAS `set ... cd9660:/dev/iso9660/` grub rewrite, irrelevant to EL.

Requires xorriso, mkfs.fat (dosfstools) and mtools.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SECTOR = 512
PART_START = 2048  # 1 MiB alignment, as Rufus partitions
MAX_OCCURRENCES = 4  # parser.c: replacements per line

# format.c:263 ToValidLabel(), FAT branch.
_UNAUTHORIZED = set('*?,;:/\\|+=<>[]"')
_TO_UNDERSCORE = set("\t.")

# iso.c:482 fix_config(): lines whose first token is one of these get the
# label (and, for RH8+ media, inst.stage2) rewritten.
CFG_TOKENS = ("options", "append", "linux", "linuxefi", "$linux", "search", "for")

# rufus.c:1295 redhat8_derivative[], matched against the ISO's volume ID.
RH8_DERIVATIVE = [
    r"^AlmaLinux-[8-9].*",
    r"^Fedora.*-3[3-9].*",
    r"^CentOS.*-[8-9].*",
    r"^Circle.*-[8-9].*",
    r"^OL-[8-9].*",
    r"^RHEL-[8-9].*",
    r"^Rocky-[8-9].*",
    r"^MIRACLE-LINUX-[8-9].*",
]

# iso.c:117 syslinux_cfg[]: patched wherever they are (all but one end in .cfg).
_SYSLINUX_CFG = {"isolinux.cfg", "syslinux.cfg", "extlinux.conf", "txt.cfg", "live.cfg"}


def rufus_fat_label(label: str, disk_size: int = 0) -> str:
    """The FAT32 label Rufus writes for an ISO labelled `label`: format.c's
    ToValidLabel(bFAT=TRUE). Drops FAT-illegal characters, turns non-ASCII
    into `_`, tab and `.` into `_`, upper-cases, and truncates to 11. A result
    that is mostly underscores is replaced by the disk size (e.g. `8 GB`)."""
    out = []
    for ch in label:
        if ch in _UNAUTHORIZED:
            continue
        if ord(ch) >= 0x80:
            out.append("_")
            continue
        if ch in _TO_UNDERSCORE:
            out.append("_")
            continue
        out.append(ch.upper())
    fat = "".join(out)[:11]
    if len(fat) < 2 * fat.count("_"):
        gib = disk_size / (1 << 30)
        fat = f"{gib:.1f} GB".replace(".", "_")
    return fat


def is_rh8_derivative(iso_label: str) -> bool:
    """rufus.c: whether Rufus treats the media as RHEL 8+ and rewrites
    inst.stage2 -> inst.repo (unless the image's file name has `netinst`)."""
    return any(re.match(rx, iso_label) for rx in RH8_DERIVATIVE)


def replace_in_token_data(text: str, token: str, src: str, rep: str) -> tuple[str, int]:
    """parser.c replace_in_token_data(): on each line whose first word, after
    leading spaces/tabs, starts with `token` (case-insensitive) and is
    followed by at least one space/tab, replace the first MAX_OCCURRENCES
    occurrences of `src` (case-sensitive) after the token. CRs are dropped
    (dos2unix). Returns the new text and the number of lines changed."""
    if src == rep:
        return text, 0
    lines = text.replace("\r", "").split("\n")
    changed = 0
    for n, line in enumerate(lines):
        i = len(line) - len(line.lstrip(" \t"))
        if line[i : i + len(token)].lower() != token.lower():
            continue
        i += len(token)
        ws = len(line[i:]) - len(line[i:].lstrip(" \t"))
        if ws == 0:
            continue
        i += ws
        head, tail = line[:i], line[i:]
        if src not in tail:
            continue
        lines[n] = head + tail.replace(src, rep, MAX_OCCURRENCES)
        changed += 1
    return "\n".join(lines), changed


def fix_config(text: str, iso_label: str, usb_label: str, *, rh8: bool) -> tuple[str, list[str]]:
    """iso.c fix_config(): the label rewrite (spaces as \\x20) for every
    CFG_TOKENS line, then, for RH8+ media, inst.stage2 -> inst.repo."""
    notes = []
    src, rep = iso_label.replace(" ", "\\x20"), usb_label.replace(" ", "\\x20")
    for token in CFG_TOKENS:
        text, n = replace_in_token_data(text, token, src, rep)
        if n:
            notes.append(f"{token}: {src!r} -> {rep!r} on {n} line(s)")
    if rh8:
        for token in CFG_TOKENS:
            text, n = replace_in_token_data(text, token, "inst.stage2", "inst.repo")
            if n:
                notes.append(f"{token}: 'inst.stage2' -> 'inst.repo' on {n} line(s)")
    return text, notes


def is_patched_config(rel: Path) -> bool:
    """iso.c: which files get fix_config at write time: any *.cfg, the
    syslinux names, and archiso's /loader/entries/*.conf."""
    name = rel.name.lower()
    if name.endswith(".cfg") or name in _SYSLINUX_CFG:
        return True
    return rel.parent.as_posix().lower() == "loader/entries" and name.endswith(".conf")


def _iso_volid(iso: Path) -> str:
    out = subprocess.run(
        ["xorriso", "-indev", str(iso), "-pvd_info"], capture_output=True, text=True, check=True
    ).stdout
    found = re.search(r"^Volume Id\s*: (.*)$", out, re.MULTILINE)
    if not found:
        sys.exit(f"no Volume Id in {iso}")
    return found.group(1).strip()


def _mbr(total_sectors: int) -> bytes:
    """One bootable FAT32-LBA (0x0c) partition from PART_START to the end."""
    mbr = bytearray(SECTOR)
    count = total_sectors - PART_START
    entry = bytearray(16)
    entry[0] = 0x80
    entry[1:4] = b"\xfe\xff\xff"  # CHS: use LBA
    entry[4] = 0x0C
    entry[5:8] = b"\xfe\xff\xff"
    entry[8:12] = PART_START.to_bytes(4, "little")
    entry[12:16] = count.to_bytes(4, "little")
    mbr[446:462] = entry
    mbr[510:512] = b"\x55\xaa"
    return bytes(mbr)


def build_stick(iso: Path, out: Path) -> None:
    iso_label = _iso_volid(iso)
    # iso.c checks strstr(image_path, "netinst") on the full path, not the name.
    rh8 = is_rh8_derivative(iso_label) and "netinst" not in str(iso.resolve())
    # Next to the output, not /tmp: a DVD's tree is ~11 GiB, and /tmp is often tmpfs.
    with tempfile.TemporaryDirectory(prefix="rufus-iso-", dir=out.parent) as tmp:
        tree = Path(tmp) / "tree"
        subprocess.run(
            ["xorriso", "-osirrox", "on", "-indev", str(iso), "-extract", "/", str(tree)],
            check=True,
            capture_output=True,
        )
        # xorriso keeps the ISO's read-only modes, but the configs get
        # rewritten and the tree removed afterwards. Owner-only: FAT32 has no
        # modes to carry over. Symlinks are left alone; mcopy copies targets.
        for root, _dirs, names in os.walk(tree):
            for name in names:
                if not (Path(root) / name).is_symlink():
                    os.chmod(Path(root) / name, 0o600)
            os.chmod(root, 0o700)

        files = [f for f in tree.rglob("*") if f.is_file() and not f.is_symlink()]
        payload = sum(f.stat().st_size for f in files)
        # FAT32 overhead plus headroom, rounded to MiB; mkfs.fat wants >= ~33 MiB.
        part_bytes = max(payload * 11 // 10 + (64 << 20), 64 << 20)
        part_sectors = -(-part_bytes // (1 << 20)) * (1 << 20) // SECTOR
        total = PART_START + part_sectors
        usb_label = rufus_fat_label(iso_label, total * SECTOR)
        print(f"rufus-iso: ISO label {iso_label!r} -> FAT32 label {usb_label!r}")
        # run.sh keys on this exact line (its boot-entry check, #136).
        print(f"rufus-iso: rh8_stage2_rewrite={'yes' if rh8 else 'no'}")

        for f in sorted(files):
            rel = f.relative_to(tree)
            if is_patched_config(rel):
                text = f.read_text(encoding="utf-8", errors="surrogateescape")
                new, notes = fix_config(text, iso_label, usb_label, rh8=rh8)
                if new != text:
                    f.write_text(new, encoding="utf-8", errors="surrogateescape")
                for note in notes:
                    print(f"rufus-iso: patched /{rel}: {note}")

        out.unlink(missing_ok=True)
        with out.open("wb") as fh:
            fh.truncate(total * SECTOR)
            fh.write(_mbr(total))
        # An empty label (every character FAT-illegal) is what Rufus would
        # write too; mkfs.fat just can't be given one.
        label_args = ["-n", usb_label] if usb_label else []
        subprocess.run(
            ["mkfs.fat", "-F", "32", *label_args, f"--offset={PART_START}",
             str(out), str(part_sectors * SECTOR // 1024)],
            check=True, capture_output=True,
        )  # fmt: skip
        img = f"{out}@@{PART_START * SECTOR}"
        entries = [str(e) for e in sorted(tree.iterdir())]
        subprocess.run(
            ["mcopy", "-s", "-Q", "-m", "-i", img, *entries, "::/"],
            check=True,
            capture_output=True,
        )
    print(f"rufus-iso: wrote {out} ({total * SECTOR >> 20} MiB)")


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    for tool in ("xorriso", "mkfs.fat", "mcopy"):
        if shutil.which(tool) is None:
            print(f"missing: {tool}", file=sys.stderr)
            return 1
    build_stick(Path(sys.argv[1]), Path(sys.argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
