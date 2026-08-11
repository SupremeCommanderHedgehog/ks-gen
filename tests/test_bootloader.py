from __future__ import annotations

from pathlib import Path

import pytest

from ks_gen.iso.bootloader import (
    BootloaderRewriteError,
    _inst_repo_arg,
    rewrite_grub,
    rewrite_isolinux,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "alma9-bootloader"
FIXTURE_DIR_AL8 = Path(__file__).parent / "fixtures" / "alma8-bootloader"
FIXTURE_DIR_AL10 = Path(__file__).parent / "fixtures" / "alma10-bootloader"


def _read_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def _read_fixture_al8(name: str) -> str:
    return (FIXTURE_DIR_AL8 / name).read_text(encoding="utf-8")


def _read_fixture_al10(name: str) -> str:
    return (FIXTURE_DIR_AL10 / name).read_text(encoding="utf-8")


def test_rewrite_isolinux_happy_path(snapshot):
    result = rewrite_isolinux(_read_fixture("isolinux.cfg"), volid="ALMA9")
    assert result == snapshot


def test_rewrite_grub_happy_path(snapshot):
    result = rewrite_grub(_read_fixture("grub.cfg"), volid="ALMA9")
    assert result == snapshot


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


def test_rewrite_isolinux_no_label_raises():
    with pytest.raises(BootloaderRewriteError, match="label"):
        rewrite_isolinux("default vesamenu.c32\ntimeout 600\n", volid="ALMA9")


def test_rewrite_grub_no_menuentry_raises():
    with pytest.raises(BootloaderRewriteError, match="menuentry"):
        rewrite_grub("set timeout=60\n", volid="ALMA9")


def test_inst_repo_arg_media():
    assert _inst_repo_arg("ALMA9", False) == " inst.repo=hd:LABEL=ALMA9"


def test_inst_repo_arg_network():
    assert _inst_repo_arg("ALMA9", True) == ""


def test_rewrite_isolinux_custom_volid():
    result = rewrite_isolinux(_read_fixture("isolinux.cfg"), volid="WEB01")
    assert "inst.ks=hd:LABEL=WEB01:/ks.cfg" in result
    assert "inst.stage2=hd:LABEL=WEB01" in result
    assert "inst.repo=hd:LABEL=WEB01" in result


def test_rewrite_grub_custom_volid():
    result = rewrite_grub(_read_fixture("grub.cfg"), volid="WEB01")
    assert "inst.ks=hd:LABEL=WEB01:/ks.cfg" in result
    assert "inst.stage2=hd:LABEL=WEB01" in result
    assert "inst.repo=hd:LABEL=WEB01" in result


# ---------------- alma8 (#121 phase 3 — verification) ----------------
#
# The rewriter's regex anchors pin isolinux/grub keywords, not AlmaLinux
# version strings. AL8 ISO bootloader configs use the same isolinux 6.x +
# grub2 syntax as AL9. These tests confirm the rewriter works on AL8
# fixtures byte-for-byte the same as AL9 — no rewriter code changes
# expected.


def test_rewrite_isolinux_happy_path_al8(snapshot):
    result = rewrite_isolinux(_read_fixture_al8("isolinux.cfg"), volid="ALMA8")
    assert result == snapshot


def test_rewrite_grub_happy_path_al8(snapshot):
    result = rewrite_grub(_read_fixture_al8("grub.cfg"), volid="ALMA8")
    assert result == snapshot


def test_rewrite_isolinux_al8_idempotent():
    original = _read_fixture_al8("isolinux.cfg")
    once = rewrite_isolinux(original, volid="ALMA8")
    twice = rewrite_isolinux(once, volid="ALMA8")
    assert once == twice


def test_rewrite_grub_al8_idempotent():
    original = _read_fixture_al8("grub.cfg")
    once = rewrite_grub(original, volid="ALMA8")
    twice = rewrite_grub(once, volid="ALMA8")
    assert once == twice


def test_rewrite_isolinux_network_install_omits_repo():
    result = rewrite_isolinux(_read_fixture("isolinux.cfg"), volid="DEV0", network_install=True)
    assert "inst.stage2=hd:LABEL=DEV0" in result
    assert "inst.ks=hd:LABEL=DEV0:/ks.cfg" in result
    assert "inst.repo=" not in result


def test_rewrite_grub_network_install_omits_repo():
    result = rewrite_grub(_read_fixture("grub.cfg"), volid="DEV0", network_install=True)
    assert "inst.stage2=hd:LABEL=DEV0" in result
    assert "inst.ks=hd:LABEL=DEV0:/ks.cfg" in result
    assert "inst.repo=" not in result


def test_rewrite_grub_media_keeps_repo():
    result = rewrite_grub(_read_fixture("grub.cfg"), volid="DEV0")
    assert "inst.repo=hd:LABEL=DEV0" in result


# ---------------- alma10 (#58) ----------------
#
# EL10 install media dropped /isolinux entirely — BIOS boot is grub2 now
# (/boot/grub2/grub.cfg + /images/eltorito.img). The BIOS grub build has no
# `linuxefi`/`initrdefi` commands, so the BIOS menu entry has to use plain
# `linux`/`initrd`.


def test_rewrite_grub_al10_efi_happy_path(snapshot):
    result = rewrite_grub(_read_fixture_al10("grub.cfg"), volid="ALMA10")
    assert result == snapshot


def test_rewrite_grub_al10_bios_happy_path(snapshot):
    result = rewrite_grub(_read_fixture_al10("bios-grub.cfg"), volid="ALMA10", bios=True)
    assert result == snapshot


def test_rewrite_grub_bios_uses_plain_linux_loader():
    result = rewrite_grub(_read_fixture_al10("bios-grub.cfg"), volid="ALMA10", bios=True)
    assert "  linux /images/pxeboot/vmlinuz" in result
    assert "  initrd /images/pxeboot/initrd.img" in result
    # The i386-pc grub build has no linuxefi/initrdefi commands at all.
    assert "linuxefi" not in result
    assert "initrdefi" not in result


def test_rewrite_grub_efi_keeps_efi_loader():
    result = rewrite_grub(_read_fixture_al10("grub.cfg"), volid="ALMA10")
    assert "  linuxefi /images/pxeboot/vmlinuz" in result
    assert "  initrdefi /images/pxeboot/initrd.img" in result


def test_rewrite_grub_bios_idempotent():
    original = _read_fixture_al10("bios-grub.cfg")
    once = rewrite_grub(original, volid="ALMA10", bios=True)
    twice = rewrite_grub(once, volid="ALMA10", bios=True)
    assert once == twice


def test_rewrite_grub_al10_defaults_to_ks_gen_entry():
    result = rewrite_grub(_read_fixture_al10("grub.cfg"), volid="ALMA10")
    assert 'set default="0"' in result
    assert result.index("Unattended STIG install (ks-gen)") < result.index(
        "menuentry 'Install AlmaLinux 10.2'"
    )


def test_rewrite_grub_entry_pins_root_to_new_volid():
    # EL10 grub.cfg carries a file-scope `search --set=root -l '<stock label>'`
    # that no longer matches once we relabel the ISO. Keep our entry
    # self-contained rather than depending on whatever $root is left over.
    result = rewrite_grub(_read_fixture_al10("grub.cfg"), volid="ALMA10")
    entry = result.split("menuentry 'Install AlmaLinux 10.2'")[0]
    assert "search --no-floppy --set=root -l 'ALMA10'" in entry


def test_rewrite_grub_bios_entry_pins_root_to_new_volid():
    result = rewrite_grub(_read_fixture_al10("bios-grub.cfg"), volid="ALMA10", bios=True)
    entry = result.split("menuentry 'Install AlmaLinux 10.2'")[0]
    assert "search --no-floppy --set=root -l 'ALMA10'" in entry


def test_rewrite_grub_bios_network_install_omits_repo():
    result = rewrite_grub(
        _read_fixture_al10("bios-grub.cfg"), volid="DEV0", bios=True, network_install=True
    )
    assert "inst.stage2=hd:LABEL=DEV0" in result
    assert "inst.ks=hd:LABEL=DEV0:/ks.cfg" in result
    assert "inst.repo=" not in result
