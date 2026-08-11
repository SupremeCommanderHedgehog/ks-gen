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


ISOLINUX_CFG = "/isolinux/isolinux.cfg"
# EL10 dropped /isolinux — BIOS boot is grub2 there.
GRUB_BIOS_CFG = "/boot/grub2/grub.cfg"
GRUB_EFI_CFG = "/EFI/BOOT/grub.cfg"


def build_iso(
    src_iso: Path,
    ks_cfg: Path,
    tailoring_xml: Path,
    out_iso: Path,
    *,
    volid: str,
    network_install: bool = False,
) -> list[str]:
    """Repack `src_iso` with ks.cfg + tailoring.xml and an unattended boot
    entry. Returns the ISO paths of the bootloader configs that were patched.
    """
    if shutil.which("xorriso") is None:
        raise IsoBuildError(
            "xorriso not on PATH (install: dnf install xorriso / brew install xorriso)"
        )

    with tempfile.TemporaryDirectory(prefix="ks-gen-iso-") as tmp:
        tmp_path = Path(tmp)
        staged: list[tuple[Path, str]] = []

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

        try:
            for local, iso_path in staged:
                local.chmod(0o644)
                text = local.read_text(encoding="utf-8")
                if iso_path == ISOLINUX_CFG:
                    patched = rewrite_isolinux(text, volid=volid, network_install=network_install)
                else:
                    patched = rewrite_grub(
                        text,
                        volid=volid,
                        network_install=network_install,
                        bios=iso_path == GRUB_BIOS_CFG,
                    )
                local.write_text(patched, encoding="utf-8")
        except BootloaderRewriteError as e:
            raise IsoBuildError(f"bootloader rewrite aborted: {e}") from e

        _author(src_iso, out_iso, volid, ks_cfg, tailoring_xml, staged)

    return [iso_path for _, iso_path in staged]


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
    for local, iso_path in mapped:
        args += ["-map", str(local), iso_path]
    args += ["-chmod", "0444", *[iso_path for _, iso_path in mapped], "--"]
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise IsoBuildError(f"xorriso failed: {result.stderr}")
