"""The Rufus ISO Image mode emulation in the install-regression harness (#134).

tests/install-regression/rufus-iso-stick.py mirrors Rufus v4.15's label
sanitising and config rewriting. These pin that behaviour, and pin that
ks-gen's default volume IDs come through it unchanged: MANUAL §8.6's Rufus
ISO-mode write copies the ISO's label onto a FAT32 stick, and every
`hd:LABEL=` in the boot configs has to match what lands there.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from ks_gen.iso.builder import default_volid, is_fat32_safe

_HELPER = Path(__file__).parent / "install-regression" / "rufus-iso-stick.py"
_spec = importlib.util.spec_from_file_location("rufus_iso_stick", _HELPER)
assert _spec is not None and _spec.loader is not None
rufus = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rufus)


@pytest.mark.parametrize(
    "vendor",
    [
        "AlmaLinux-8-10-x86_64-dvd",
        "AlmaLinux-9-8-x86_64-dvd",
        "AlmaLinux-10-2-x86_64-boot",
        "AlmaLinux-10-10-x86_64-dvd",
    ],
)
def test_default_volid_survives_rufus_iso_mode(vendor):
    """Rufus would otherwise rewrite our labels (fix_config), and a rewrite
    is a path the harness only exercises when the labels differ."""
    volid = default_volid(vendor)
    assert rufus.rufus_fat_label(volid) == volid


@pytest.mark.parametrize(
    ("iso_label", "fat"),
    [
        ("AlmaLinux-10-2-x86_64-dvd", "ALMALINUX-1"),  # upper-cased, cut to 11
        ("web01.ks", "WEB01_KS"),  # '.' -> '_'
        ("a:b*c?d", "ABCD"),  # FAT-illegal characters dropped
        ("café", "CAF_"),  # non-ASCII -> '_'
        ("ALMA9", "ALMA9"),
    ],
)
def test_rufus_fat_label(iso_label, fat):
    assert rufus.rufus_fat_label(iso_label) == fat


def test_rufus_fat_label_mostly_underscores_falls_back_to_disk_size():
    assert rufus.rufus_fat_label("...", 8 << 30) == "8_0 GB"


@pytest.mark.parametrize(
    ("label", "rh8"),
    [
        ("AlmaLinux-9-8-x86_64-dvd", True),
        ("AlmaLinux-8-10-x86_64-dvd", True),
        # Rufus v4.15's list stops at 9, and ks-gen's labels never match it.
        ("AlmaLinux-10-2-x86_64-dvd", False),
        ("KS-AL9-8", False),
        ("ALMA9", False),
    ],
)
def test_is_rh8_derivative(label, rh8):
    assert rufus.is_rh8_derivative(label) is rh8


GRUB = """\
search --no-floppy --set=root -l 'OLD-LABEL'
menuentry 'x' {
  linuxefi /images/pxeboot/vmlinuz inst.stage2=hd:LABEL=OLD-LABEL inst.ks=hd:LABEL=OLD-LABEL:/ks.cfg
\tlinux /vmlinuz root=live:LABEL=OLD-LABEL
  initrdefi /images/pxeboot/initrd.img OLD-LABEL
  linuxefiX OLD-LABEL
}
"""


def test_fix_config_rewrites_the_label_on_token_lines_only():
    out, notes = rufus.fix_config(GRUB, "OLD-LABEL", "NEW", rh8=False)
    lines = out.splitlines()
    assert lines[0] == "search --no-floppy --set=root -l 'NEW'"
    assert "inst.stage2=hd:LABEL=NEW inst.ks=hd:LABEL=NEW:/ks.cfg" in lines[2]
    assert lines[3] == "\tlinux /vmlinuz root=live:LABEL=NEW"
    # Not a token line, and a token prefix without whitespace after it.
    assert lines[4].endswith("OLD-LABEL")
    assert lines[5] == "  linuxefiX OLD-LABEL"
    assert len(notes) == 3


def test_fix_config_caps_replacements_per_line():
    line = "append " + " ".join(["L"] * 6)
    out, _ = rufus.fix_config(line, "L", "M", rh8=False)
    assert out == "append " + " ".join(["M"] * 4 + ["L"] * 2)


def test_fix_config_rh8_rewrites_inst_stage2():
    out, notes = rufus.fix_config(GRUB, "OLD-LABEL", "OLD-LABEL", rh8=True)
    assert "inst.repo=hd:LABEL=OLD-LABEL inst.ks" in out
    assert "inst.stage2" not in out
    assert notes == ["linuxefi: 'inst.stage2' -> 'inst.repo' on 1 line(s)"]


def test_fix_config_escapes_spaces():
    out, _ = rufus.fix_config("linux x LABEL=My\\x20Disk", "My Disk", "MY_DISK", rh8=False)
    assert out == "linux x LABEL=MY_DISK"


@pytest.mark.parametrize(
    ("rel", "patched"),
    [
        ("EFI/BOOT/grub.cfg", True),
        ("boot/grub2/grub.cfg", True),
        ("isolinux/isolinux.cfg", True),
        ("syslinux/extlinux.conf", True),
        ("loader/entries/arch.conf", True),
        ("etc/other.conf", False),
        ("ks.cfg", True),  # any *.cfg, the kickstart included
        ("tailoring.xml", False),
    ],
)
def test_is_patched_config(rel, patched):
    assert rufus.is_patched_config(Path(rel)) is patched


@pytest.mark.parametrize(
    "volid",
    ["KS-AL10-2", "ALMA9", "X" * 11, "X" * 12, "web01", "a.b", "___", "A__", "A_B", "AB__", "W-1"],
)
def test_is_fat32_safe_agrees_with_rufus(volid):
    """The CLI's Rufus warning (is_fat32_safe) must fire exactly when Rufus
    would write a different label than the ISO's."""
    assert is_fat32_safe(volid) is (rufus.rufus_fat_label(volid, 8 << 30) == volid)
