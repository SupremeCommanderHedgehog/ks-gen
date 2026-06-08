from __future__ import annotations

from pathlib import Path

from ks_gen.iso.bootloader import rewrite_grub, rewrite_isolinux

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "alma9-bootloader"


def _read_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_rewrite_isolinux_happy_path(snapshot):
    result = rewrite_isolinux(_read_fixture("isolinux.cfg"), volid="ALMA9")
    assert result == snapshot


def test_rewrite_grub_happy_path(snapshot):
    result = rewrite_grub(_read_fixture("grub.cfg"), volid="ALMA9")
    assert result == snapshot
