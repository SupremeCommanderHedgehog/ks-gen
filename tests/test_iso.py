from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ks_gen.iso import IsoBuildError, build_iso


def test_build_iso_calls_xorriso(tmp_path):
    src = tmp_path / "src.iso"
    src.write_bytes(b"\0" * 1024)
    ks = tmp_path / "ks.cfg"
    ks.write_text("text\n", encoding="utf-8")
    tail = tmp_path / "tailoring.xml"
    tail.write_text("<x/>", encoding="utf-8")
    out = tmp_path / "out.iso"

    def fake_run(args, **kwargs):
        # Simulate xorriso -extract by writing a tiny config to the dest path.
        if "-extract" in args:
            idx = args.index("-extract")
            dest = Path(args[idx + 2])
            if "isolinux.cfg" in args[idx + 1]:
                dest.write_text("timeout 600\nlabel linux\n  kernel vmlinuz\n", encoding="utf-8")
            else:
                dest.write_text(
                    "set timeout=60\nmenuentry 'foo' { linuxefi vmlinuz\ninitrdefi initrd.img\n}\n",
                    encoding="utf-8",
                )
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        return result

    with (
        patch("ks_gen.iso.builder.shutil.which", return_value="/usr/bin/xorriso"),
        patch("ks_gen.iso.builder.subprocess.run", side_effect=fake_run) as run,
    ):
        build_iso(src, ks, tail, out, volid="ALMA9")

    # Three xorriso passes: extract isolinux, extract grub, final author
    assert run.call_count == 3
    extract_calls = [c for c in run.call_args_list if "-extract" in c.args[0]]
    author_calls = [c for c in run.call_args_list if "replay" in c.args[0]]
    assert len(extract_calls) == 2
    assert len(author_calls) == 1

    # Final author maps all four files
    final_args = author_calls[0].args[0]
    assert "/isolinux/isolinux.cfg" in final_args
    assert "/EFI/BOOT/grub.cfg" in final_args
    assert "/ks.cfg" in final_args
    assert "/tailoring.xml" in final_args


def test_build_iso_missing_xorriso_raises(tmp_path):
    src = tmp_path / "src.iso"
    src.write_bytes(b"\0")
    ks = tmp_path / "ks.cfg"
    ks.write_text("x", encoding="utf-8")
    tail = tmp_path / "t.xml"
    tail.write_text("x", encoding="utf-8")
    out = tmp_path / "out.iso"
    with patch("ks_gen.iso.builder.shutil.which", return_value=None):
        try:
            build_iso(src, ks, tail, out, volid="ALMA9")
        except IsoBuildError as e:
            assert "xorriso" in str(e)
        else:
            raise AssertionError("expected IsoBuildError")


def test_build_iso_extract_fails_raises(tmp_path):
    src = tmp_path / "src.iso"
    src.write_bytes(b"\0")
    ks = tmp_path / "ks.cfg"
    ks.write_text("x", encoding="utf-8")
    tail = tmp_path / "t.xml"
    tail.write_text("x", encoding="utf-8")
    out = tmp_path / "out.iso"

    def fake_run(args, **kwargs):
        result = MagicMock()
        if "-extract" in args:
            result.returncode = 1
            result.stderr = "isofs: file not found"
        else:
            result.returncode = 0
            result.stderr = ""
        return result

    with (
        patch("ks_gen.iso.builder.shutil.which", return_value="/usr/bin/xorriso"),
        patch("ks_gen.iso.builder.subprocess.run", side_effect=fake_run),
        pytest.raises(IsoBuildError, match="source ISO missing"),
    ):
        build_iso(src, ks, tail, out, volid="ALMA9")


def test_build_iso_rewrite_error_raises(tmp_path):
    src = tmp_path / "src.iso"
    src.write_bytes(b"\0")
    ks = tmp_path / "ks.cfg"
    ks.write_text("x", encoding="utf-8")
    tail = tmp_path / "t.xml"
    tail.write_text("x", encoding="utf-8")
    out = tmp_path / "out.iso"

    def fake_run(args, **kwargs):
        if "-extract" in args:
            idx = args.index("-extract")
            dest = Path(args[idx + 2])
            # Write content that has no `label` / `menuentry` keyword
            dest.write_text("timeout 600\n", encoding="utf-8")
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        return result

    with (
        patch("ks_gen.iso.builder.shutil.which", return_value="/usr/bin/xorriso"),
        patch("ks_gen.iso.builder.subprocess.run", side_effect=fake_run),
        pytest.raises(IsoBuildError, match="bootloader rewrite aborted"),
    ):
        build_iso(src, ks, tail, out, volid="ALMA9")
