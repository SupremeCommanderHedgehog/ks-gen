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
    network_install: bool = False,
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
        iso_isolinux.chmod(0o644)
        _extract(src_iso, "/EFI/BOOT/grub.cfg", iso_grub)
        iso_grub.chmod(0o644)

        try:
            iso_isolinux.write_text(
                rewrite_isolinux(
                    iso_isolinux.read_text(encoding="utf-8"),
                    volid=volid,
                    network_install=network_install,
                ),
                encoding="utf-8",
            )
            iso_grub.write_text(
                rewrite_grub(
                    iso_grub.read_text(encoding="utf-8"),
                    volid=volid,
                    network_install=network_install,
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
    # xorriso refuses `-outdev` against a non-empty file when it differs from
    # `-indev`. We treat `--out` as a writable target, so unlink any prior ISO
    # before authoring.
    out_iso.unlink(missing_ok=True)
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
