#!/usr/bin/env python3
"""Build a ks-gen installer ISO with serial-console kernel args baked in.

Why this exists
---------------
`ks-gen iso` ships `quiet` on both the BIOS isolinux and EFI grub menu
entries — the right default for a real human installer. The install-
regression harness needs anaconda's TUI log on the serial port so the
harness can watch progress and capture failures.

Rather than mutate src/ks_gen/iso/_menu.py (the documented "debug rebuild"
recipe in project CLAUDE.md), this script monkey-patches the bootloader
module's already-imported constants at runtime. No source edit, no revert
step.

Usage:
    build-debug-iso.py SRC_ISO BUNDLE_DIR OUT_ISO
"""

from __future__ import annotations

import sys
from pathlib import Path

# Import bootloader FIRST so the names exist in its namespace.
from ks_gen.iso import bootloader  # noqa: E402
from ks_gen.iso.builder import build_iso  # noqa: E402

# inst.text       — TUI installer, no GUI
# inst.notmux     — don't wrap the UI in a tmux session; write straight to the
#                   console (tmux on serial without a tty allocator hangs)
# inst.console    — anaconda's own UI output target; without this, anaconda
#                   follows /dev/console which the last `console=` arg sets
# console=ttyS0   — kernel and userspace stdout to the serial port
# Trailing tty0 console must NOT be present: when multiple console= args are
# given, the last one becomes /dev/console — if that's tty0, anaconda writes
# its UI to the (invisible-under-nographic) framebuffer and the install hangs
# waiting for input we can never send. The first end-to-end attempt lost 2h
# of wall-clock to that exact failure mode.
DEBUG_KERNEL_ARGS = "inst.text inst.notmux inst.console=ttyS0,115200n8 console=ttyS0,115200n8"

# Replace `quiet` with the debug-friendly kernel args in both menu templates.
# `quiet` appears at end-of-line in both — substitute textually so the rest
# of the entry is untouched.
bootloader.ISOLINUX_UNATTENDED_ENTRY = bootloader.ISOLINUX_UNATTENDED_ENTRY.replace(
    " quiet\n", f" {DEBUG_KERNEL_ARGS}\n"
)
bootloader.GRUB_UNATTENDED_ENTRY = bootloader.GRUB_UNATTENDED_ENTRY.replace(
    " quiet\n", f" {DEBUG_KERNEL_ARGS}\n"
)

assert "quiet\n" not in bootloader.ISOLINUX_UNATTENDED_ENTRY
assert "quiet\n" not in bootloader.GRUB_UNATTENDED_ENTRY


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    src_iso = Path(sys.argv[1])
    bundle = Path(sys.argv[2])
    out_iso = Path(sys.argv[3])

    build_iso(
        src_iso=src_iso,
        ks_cfg=(bundle / "ks.cfg"),
        tailoring_xml=(bundle / "tailoring.xml"),
        out_iso=out_iso,
        volid="ALMA9",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
