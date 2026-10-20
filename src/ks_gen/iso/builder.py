from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ks_gen.iso._menu import IDEMPOTENCY_MARKER
from ks_gen.iso.bootloader import (
    BootloaderRewriteError,
    rewrite_grub,
    rewrite_isolinux,
)


class IsoBuildError(Exception):
    pass


class VolidError(IsoBuildError):
    """The volume ID is unusable, or none can be derived: a usage error."""


ISOLINUX_CFG = "/isolinux/isolinux.cfg"
# EL10 dropped /isolinux — BIOS boot is grub2 there.
GRUB_BIOS_CFG = "/boot/grub2/grub.cfg"
GRUB_EFI_CFG = "/EFI/BOOT/grub.cfg"
# The same config inside the EFI system partition image. GRUB booted from a
# USB stick reads this one, not the ISO9660 tree's (#116).
ESP_GRUB_CFG = "::/EFI/BOOT/grub.cfg"

_VOLID_RE = re.compile(r"^Volume Id\s*: (.*)$", re.MULTILINE)
# What every `hd:LABEL=` / `search -l` reference can carry unescaped (no
# spaces: those need \x20), within ISO9660's 32-byte volume ID.
_VOLID_OK_RE = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
# What also survives Rufus's ISO Image mode, which formats the stick FAT32 and
# copies the label over: at most 11 characters, which Windows upper-cases.
_FAT32_LABEL_RE = re.compile(r"^[A-Z0-9_-]{1,11}$")
_ALMA_VOLID_RE = re.compile(r"^AlmaLinux-(\d+)-(\d+)-")
_EFI_PATH_RE = re.compile(r"^-boot_image any efi_path='(.*)'$", re.MULTILINE)
_APPENDED_EFI_RE = re.compile(r"^--interval:appended_partition_(\d+)_")
# xorriso's "d" unit is a 512-byte block, and the range is inclusive.
_BLOCK = 512


def build_iso(
    src_iso: Path,
    ks_cfg: Path,
    tailoring_xml: Path,
    out_iso: Path,
    *,
    volid: str | None = None,
    network_install: bool = False,
) -> IsoBuild:
    """Repack `src_iso` with ks.cfg + tailoring.xml and an unattended boot
    entry, labelled `volid` or, by default, `default_volid` of the source's
    own volume ID.
    """
    if volid is not None:
        validate_volid(volid)
    if shutil.which("xorriso") is None:
        raise IsoBuildError(
            "xorriso not on PATH (install: dnf install xorriso / brew install xorriso)"
        )

    with tempfile.TemporaryDirectory(prefix="ks-gen-iso-") as tmp:
        tmp_path = Path(tmp)
        staged: list[tuple[Path, str]] = []
        report = _report_boot(src_iso)
        vendor_volid = _vendor_volid(report)

        # BIOS: isolinux on EL8/EL9, grub2 on EL10. Neither is fatal on its
        # own — media may legitimately be EFI-only.
        bios_isolinux = tmp_path / "isolinux.cfg"
        bios_grub = tmp_path / "bios-grub.cfg"
        if _try_extract(src_iso, ISOLINUX_CFG, bios_isolinux):
            staged.append((bios_isolinux, ISOLINUX_CFG))
        elif _try_extract(src_iso, GRUB_BIOS_CFG, bios_grub):
            staged.append((bios_grub, GRUB_BIOS_CFG))

        efi_grub = tmp_path / "grub.cfg"
        _extract(src_iso, GRUB_EFI_CFG, efi_grub)
        staged.append((efi_grub, GRUB_EFI_CFG))

        if volid is None:
            # A source that is already a ks-gen installer keeps its label,
            # whatever it is: its unattended entry is left as is (see
            # rewrite_grub), and it looks the media up by that label.
            if IDEMPOTENCY_MARKER in efi_grub.read_text(encoding="utf-8"):
                volid = vendor_volid
            else:
                volid = default_volid(vendor_volid)

        for local, iso_path in staged:
            local.chmod(0o644)
            _rewrite_cfg(
                local, iso_path, iso_path,
                volid=volid, vendor_volid=vendor_volid, network_install=network_install,
            )  # fmt: skip

        esp = _extract_esp(src_iso, report, tmp_path)
        if esp is not None:
            _patch_esp(
                esp, tmp_path, volid=volid, vendor_volid=vendor_volid,
                network_install=network_install,
            )  # fmt: skip

        _author(src_iso, out_iso, volid, ks_cfg, tailoring_xml, staged, esp)

    reported = [iso_path for _, iso_path in staged]
    if esp is not None:
        reported.append(f"{esp.label}:{GRUB_EFI_CFG}")
    return IsoBuild(volid=volid, patched=tuple(reported))


def default_volid(vendor_volid: str) -> str:
    """The installer's label for a source labelled `vendor_volid`:
    `KS-AL<major>-<minor>` (#128). It differs from the vendor's own label,
    so a stock vendor stick plugged in alongside can't answer the
    installer's `hd:LABEL=` lookups, and it fits FAT32 (see
    `is_fat32_safe`). It names the release, not the host: installers for
    two hosts on one release share it unless given their own --volid."""
    found = _ALMA_VOLID_RE.match(vendor_volid)
    if found is None:
        raise VolidError(
            f"cannot derive a volume ID from the source ISO's {vendor_volid!r} "
            "(expected an AlmaLinux-<major>-<minor>-... label); pass --volid"
        )
    return f"KS-AL{found.group(1)}-{found.group(2)}"


def validate_volid(volid: str) -> None:
    """Reject a volume ID the boot configs can't reference: over ISO9660's
    32 bytes, or with characters `hd:LABEL=` would need escaped."""
    if not _VOLID_OK_RE.match(volid):
        raise VolidError(f"invalid volume ID {volid!r}: use 1-32 characters from A-Z a-z 0-9 _ . -")


def is_fat32_safe(volid: str) -> bool:
    """Whether `volid` survives Rufus's ISO Image mode unchanged, which the
    MANUAL recommends for Windows: 11 characters at most, upper-case."""
    return _FAT32_LABEL_RE.match(volid) is not None


def _report_boot(src_iso: Path) -> str:
    """The source's primary volume descriptor plus xorriso's replayable
    description of its boot setup: El Torito entries, appended partitions."""
    result = subprocess.run(
        ["xorriso", "-indev", str(src_iso), "-pvd_info", "-report_el_torito", "cmd"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise IsoBuildError(f"xorriso -report_el_torito failed: {result.stderr.strip()}")
    return result.stdout


def _vendor_volid(report: str) -> str:
    """The source's volume ID, which its bootloader configs search for."""
    found = _VOLID_RE.search(report)
    if found is None or not found.group(1).strip():
        raise IsoBuildError("xorriso -pvd_info printed no Volume Id for the source ISO")
    return found.group(1).strip()


def _retarget(text: str, vendor_volid: str, volid: str) -> str:
    """Point the vendor entries' `search -l` / `hd:LABEL=` at the renamed
    volume, so the fallback entries kept below ours still boot. Whole labels
    only, quoted or not — never a longer label that merely starts with it."""
    if vendor_volid == volid:
        return text
    return re.sub(rf"(?<![\w.-]){re.escape(vendor_volid)}(?![\w.-])", lambda _: volid, text)


def _rewrite_cfg(
    local: Path,
    iso_path: str,
    where: str,
    *,
    volid: str,
    vendor_volid: str,
    network_install: bool,
) -> None:
    """Retarget and add the unattended entry to one bootloader config, in place.
    `where` names it in errors — the ESP copy and the tree copy share a path."""
    text = _retarget(local.read_text(encoding="utf-8"), vendor_volid, volid)
    try:
        if iso_path == ISOLINUX_CFG:
            patched = rewrite_isolinux(text, volid=volid, network_install=network_install)
        else:
            patched = rewrite_grub(
                text,
                volid=volid,
                network_install=network_install,
                bios=iso_path == GRUB_BIOS_CFG,
            )
    except BootloaderRewriteError as e:
        raise IsoBuildError(f"bootloader rewrite aborted in {where}: {e}") from e
    local.write_text(patched, encoding="utf-8")


@dataclass(frozen=True)
class IsoBuild:
    """What `build_iso` did: the volume ID it labelled the ISO with, and the
    bootloader configs it patched (the EFI partition's copy as
    `<image>:/EFI/BOOT/grub.cfg`)."""

    volid: str
    patched: tuple[str, ...]


@dataclass(frozen=True)
class _Esp:
    """A local copy of the source ISO's EFI system partition image.

    `author_args` put the patched copy back where `-boot_image any replay`
    would otherwise reinstate the vendor's original. `iso_path` is set when
    the image is a file in the ISO9660 tree.
    """

    image: Path
    label: str
    author_args: list[str]
    iso_path: str | None = None


def _extract_esp(src_iso: Path, report: str, tmp_path: Path) -> _Esp | None:
    """Copy out the EFI El Torito image, or None if the media has none.

    EL8/EL9 keep it as a file in the tree (/images/efiboot.img). EL10 keeps it
    as a GPT partition appended after the ISO9660 data, which replay copies
    byte-for-byte from the source ISO.
    """
    efi_paths = _EFI_PATH_RE.findall(report)
    if not efi_paths:
        return None
    if len(efi_paths) > 1:
        # Patching one would leave firmware that picks another on the stale
        # vendor menu; no AlmaLinux media does this today.
        raise IsoBuildError(f"source ISO has {len(efi_paths)} EFI boot images; expected one")
    efi_path = efi_paths[0]
    dest = tmp_path / "esp.img"

    appended = _APPENDED_EFI_RE.match(efi_path)
    if appended is None:
        if efi_path.startswith("--"):
            raise IsoBuildError(f"unsupported EFI boot image source: {efi_path!r}")
        failed = _run_extract(src_iso, efi_path, dest)
        if failed is not None:
            raise IsoBuildError(f"extracting EFI boot image {efi_path} failed ({failed})")
        dest.chmod(0o644)
        return _Esp(dest, efi_path, ["-map", str(dest), efi_path], iso_path=efi_path)

    number = appended.group(1)
    part = re.search(
        rf"^-append_partition {number} (\S+) --interval:imported_iso:(\d+)d-(\d+)d::",
        report,
        flags=re.MULTILINE,
    )
    if part is None:
        raise IsoBuildError(
            f"EFI boot image is appended partition {number}, but xorriso reports no "
            "source interval for it"
        )
    type_code, first, last = part.group(1), int(part.group(2)), int(part.group(3))
    size = (last - first + 1) * _BLOCK
    with src_iso.open("rb") as f, dest.open("wb") as out:
        f.seek(first * _BLOCK)
        remaining = size
        while remaining:
            chunk = f.read(min(remaining, 1 << 20))
            if not chunk:
                raise IsoBuildError(f"source ISO truncated inside EFI partition {number}")
            out.write(chunk)
            remaining -= len(chunk)
    return _Esp(
        dest, f"EFI partition {number}", ["-append_partition", number, type_code, str(dest)]
    )


def _mtools(args: list[str]) -> subprocess.CompletedProcess[str]:
    # El Torito EFI images are bare FAT filesystems with no partition table or
    # BIOS geometry, which mtools rejects unless told not to check.
    env = {**os.environ, "MTOOLS_SKIP_CHECK": "1"}
    return subprocess.run(args, capture_output=True, text=True, env=env)


def _patch_esp(
    esp: _Esp, tmp_path: Path, *, volid: str, vendor_volid: str, network_install: bool
) -> None:
    """Rewrite the ESP image's grub.cfg in place.

    Every failure is fatal: an ISO whose ESP still holds the vendor menu
    installs from CD but not from a USB stick (#116), and nothing short of a
    USB boot would reveal it.
    """
    if shutil.which("mcopy") is None:
        raise IsoBuildError(
            "mcopy not on PATH — needed to patch the EFI partition's grub.cfg "
            "(install: dnf install mtools / apt install mtools / brew install mtools)"
        )
    where = f"{esp.label}:{GRUB_EFI_CFG}"
    cfg = tmp_path / "esp-grub.cfg"
    read = _mtools(["mcopy", "-n", "-i", str(esp.image), ESP_GRUB_CFG, str(cfg)])
    if read.returncode != 0:
        raise IsoBuildError(f"reading {where} failed: {read.stderr.strip()}")
    _rewrite_cfg(
        cfg, GRUB_EFI_CFG, where,
        volid=volid, vendor_volid=vendor_volid, network_install=network_install,
    )  # fmt: skip
    write = _mtools(["mcopy", "-o", "-i", str(esp.image), str(cfg), ESP_GRUB_CFG])
    if write.returncode != 0:
        raise IsoBuildError(f"writing {where} failed: {write.stderr.strip()}")


def _run_extract(src_iso: Path, iso_path: str, dest: Path) -> str | None:
    """Extract one file from the ISO. Returns None on success, else xorriso's
    stderr."""
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
        detail = result.stderr.strip() or "no output produced"
        return f"exit {result.returncode}: {detail}"
    return None


def _try_extract(src_iso: Path, iso_path: str, dest: Path) -> bool:
    return _run_extract(src_iso, iso_path, dest) is None


def _extract(src_iso: Path, iso_path: str, dest: Path) -> None:
    stderr = _run_extract(src_iso, iso_path, dest)
    if stderr is not None:
        raise IsoBuildError(
            f"source ISO missing {iso_path} — not an AlmaLinux install ISO? "
            f"(xorriso: {stderr.strip()})"
        )


def _author(
    src_iso: Path,
    out_iso: Path,
    volid: str,
    ks_cfg: Path,
    tailoring_xml: Path,
    bootloader_cfgs: list[tuple[Path, str]],
    esp: _Esp | None = None,
) -> None:
    # xorriso refuses `-outdev` against a non-empty file when it differs from
    # `-indev`. We treat `--out` as a writable target, so unlink any prior ISO
    # before authoring.
    out_iso.unlink(missing_ok=True)
    mapped = [*bootloader_cfgs, (ks_cfg, "/ks.cfg"), (tailoring_xml, "/tailoring.xml")]
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
    ]
    # After replay, so the patched ESP overrides the one replay reinstates.
    if esp is not None:
        args += esp.author_args
    for local, iso_path in mapped:
        args += ["-map", str(local), iso_path]
    read_only = [iso_path for _, iso_path in mapped]
    if esp is not None and esp.iso_path is not None:
        read_only.append(esp.iso_path)
    args += ["-chmod", "0444", *read_only, "--"]
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise IsoBuildError(f"xorriso failed: {result.stderr}")
