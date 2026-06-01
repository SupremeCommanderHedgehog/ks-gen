from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class IsoBuildError(Exception):
    pass


def build_iso(
    src_iso: Path,
    ks_cfg: Path,
    tailoring_xml: Path,
    out_iso: Path,
    *,
    volid: str,
    keep_original_default: bool = False,
) -> None:
    # v0.1 limitation: injects ks.cfg + tailoring.xml at ISO root but does NOT
    # rewrite isolinux/grub configs. Operator must type
    # `inst.ks=hd:LABEL=<volid>:/ks.cfg` at the boot prompt. Bootloader
    # rewriting is tracked for v0.2.
    if shutil.which("xorriso") is None:
        raise IsoBuildError(
            "xorriso not on PATH (install: dnf install xorriso / brew install xorriso)"
        )
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
        str(ks_cfg),
        "/ks.cfg",
        "-map",
        str(tailoring_xml),
        "/tailoring.xml",
        "-chmod",
        "0444",
        "/ks.cfg",
        "/tailoring.xml",
        "--",
    ]
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise IsoBuildError(f"xorriso failed: {result.stderr}")
