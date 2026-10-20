"""The installer's volume ID is derived from the source media (#128).

It used to be a hardcoded ALMA9 on every distro, so an AL10 stick read as an
AL9 one. The derived label names the release and differs from the vendor's,
so a stock vendor stick can't answer `hd:LABEL=`. build_iso and CLI coverage
lives in test_iso.py, next to its xorriso stub.
"""

from __future__ import annotations

import pytest

from ks_gen.iso import VolidError, is_fat32_safe
from ks_gen.iso.builder import default_volid, validate_volid


@pytest.mark.parametrize(
    ("vendor", "expected"),
    [
        ("AlmaLinux-10-2-x86_64-dvd", "KS-AL10-2"),
        ("AlmaLinux-9-8-x86_64-dvd", "KS-AL9-8"),
        ("AlmaLinux-8-10-x86_64-dvd", "KS-AL8-10"),
        ("AlmaLinux-10-10-x86_64-boot", "KS-AL10-10"),
    ],
)
def test_default_volid_names_the_release(vendor, expected):
    assert default_volid(vendor) == expected
    # Rufus's ISO Image mode copies the label onto a FAT32 stick (MANUAL §8.6).
    assert is_fat32_safe(expected)


@pytest.mark.parametrize("vendor", ["CentOS-Stream-9-x86_64-dvd", "ALMA9", "AlmaLinux-10"])
def test_default_volid_refuses_to_guess(vendor):
    with pytest.raises(VolidError, match="pass --volid"):
        default_volid(vendor)


@pytest.mark.parametrize("volid", ["WEB01", "AlmaLinux-10-2-x86_64-dvd", "a.b_c-1", "X" * 32])
def test_validate_volid_accepts(volid):
    validate_volid(volid)


@pytest.mark.parametrize("volid", ["", "MY LABEL", "X" * 33, "web01:ks", "a/b"])
def test_validate_volid_rejects(volid):
    with pytest.raises(VolidError, match="invalid volume ID"):
        validate_volid(volid)


@pytest.mark.parametrize(
    ("volid", "safe"),
    [("KS-AL9-8", True), ("ALMA9", True), ("X" * 11, True), ("X" * 12, False), ("web01", False)],
)
def test_is_fat32_safe(volid, safe):
    assert is_fat32_safe(volid) is safe
