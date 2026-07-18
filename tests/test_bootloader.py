from __future__ import annotations

from pathlib import Path

import pytest

from ks_gen.iso.bootloader import BootloaderRewriteError, rewrite_grub, rewrite_isolinux

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "alma9-bootloader"
FIXTURE_DIR_AL8 = Path(__file__).parent / "fixtures" / "alma8-bootloader"


def _read_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def _read_fixture_al8(name: str) -> str:
    return (FIXTURE_DIR_AL8 / name).read_text(encoding="utf-8")


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
