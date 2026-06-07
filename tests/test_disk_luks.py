from pathlib import Path

import pytest

from ks_gen.config import DiskLuks
from ks_gen.disk_luks import resolve_passphrase


def test_resolve_passphrase_none_preset_returns_none():
    luks = DiskLuks()  # preset=NONE, no passphrase
    assert resolve_passphrase(luks) is None


def test_resolve_passphrase_inline():
    luks = DiskLuks.model_validate({"preset": "partial", "passphrase": "hunter2"})
    assert resolve_passphrase(luks) == "hunter2"


def test_resolve_passphrase_from_file(tmp_path: Path):
    keyfile = tmp_path / "key"
    keyfile.write_text("hunter2\n", encoding="utf-8")
    luks = DiskLuks.model_validate({"preset": "partial", "passphrase_file": str(keyfile)})
    assert resolve_passphrase(luks) == "hunter2"


def test_resolve_passphrase_from_file_strips_whitespace(tmp_path: Path):
    keyfile = tmp_path / "key"
    keyfile.write_text("  hunter2  \n\n", encoding="utf-8")
    luks = DiskLuks.model_validate({"preset": "partial", "passphrase_file": str(keyfile)})
    assert resolve_passphrase(luks) == "hunter2"


def test_resolve_passphrase_from_missing_file_raises(tmp_path: Path):
    missing = tmp_path / "does-not-exist"
    luks = DiskLuks.model_validate({"preset": "partial", "passphrase_file": str(missing)})
    with pytest.raises(FileNotFoundError):
        resolve_passphrase(luks)


def test_resolve_passphrase_from_empty_file_raises(tmp_path: Path):
    keyfile = tmp_path / "empty"
    keyfile.write_text("   \n\n  ", encoding="utf-8")
    luks = DiskLuks.model_validate({"preset": "partial", "passphrase_file": str(keyfile)})
    with pytest.raises(ValueError, match=r"empty after whitespace strip"):
        resolve_passphrase(luks)
