from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from ks_gen.cli import app
from ks_gen.iso import IsoBuildError, build_iso

runner = CliRunner()


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


def test_build_iso_overwrites_existing_out(tmp_path):
    src = tmp_path / "src.iso"
    src.write_bytes(b"\0" * 1024)
    ks = tmp_path / "ks.cfg"
    ks.write_text("text\n", encoding="utf-8")
    tail = tmp_path / "tailoring.xml"
    tail.write_text("<x/>", encoding="utf-8")
    out = tmp_path / "out.iso"
    out.write_bytes(b"stale" * 1024)

    def fake_run(args, **kwargs):
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
        if "-outdev" in args:
            # xorriso would refuse if `out` still existed with non-zero data —
            # builder must unlink it first.
            assert not out.exists(), "builder must unlink -outdev target before xorriso runs"
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        return result

    with (
        patch("ks_gen.iso.builder.shutil.which", return_value="/usr/bin/xorriso"),
        patch("ks_gen.iso.builder.subprocess.run", side_effect=fake_run),
    ):
        build_iso(src, ks, tail, out, volid="ALMA9")


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


def test_build_iso_forwards_network_install(tmp_path):
    src = tmp_path / "src.iso"
    src.write_bytes(b"\0" * 1024)
    ks = tmp_path / "ks.cfg"
    ks.write_text("text\n", encoding="utf-8")
    tail = tmp_path / "tailoring.xml"
    tail.write_text("<x/>", encoding="utf-8")
    out = tmp_path / "out.iso"

    def fake_run(args, **kwargs):
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
        patch("ks_gen.iso.builder.subprocess.run", side_effect=fake_run),
        patch("ks_gen.iso.builder.rewrite_isolinux", return_value="x") as ri,
        patch("ks_gen.iso.builder.rewrite_grub", return_value="x") as rg,
    ):
        build_iso(src, ks, tail, out, volid="DEV0", network_install=True)

    assert ri.call_args.kwargs["network_install"] is True
    assert rg.call_args.kwargs["network_install"] is True


def _make_iso_cli_files(tmp_path, *, ks_has_url: bool):
    src = tmp_path / "src.iso"
    src.write_bytes(b"\0" * 1024)
    ks = tmp_path / "ks.cfg"
    if ks_has_url:
        ks.write_text('url --url="https://x/BaseOS/"\n', encoding="utf-8")
    else:
        ks.write_text("cmdline\n", encoding="utf-8")
    tail = tmp_path / "tailoring.xml"
    tail.write_text("<x/>", encoding="utf-8")
    out = tmp_path / "out.iso"
    return src, ks, tail, out


def test_iso_cmd_autodetects_network_install_from_url_line(tmp_path):
    src, ks, tail, out = _make_iso_cli_files(tmp_path, ks_has_url=True)
    with patch("ks_gen.cli.build_iso") as mock_build:
        result = runner.invoke(
            app,
            [
                "iso",
                "--src",
                str(src),
                "--ks",
                str(ks),
                "--tailoring",
                str(tail),
                "--out",
                str(out),
            ],
        )
    assert result.exit_code == 0, result.output
    mock_build.assert_called_once()
    assert mock_build.call_args.kwargs["network_install"] is True


def test_iso_cmd_autodetects_media_install_when_no_url_line(tmp_path):
    src, ks, tail, out = _make_iso_cli_files(tmp_path, ks_has_url=False)
    with patch("ks_gen.cli.build_iso") as mock_build:
        result = runner.invoke(
            app,
            [
                "iso",
                "--src",
                str(src),
                "--ks",
                str(ks),
                "--tailoring",
                str(tail),
                "--out",
                str(out),
            ],
        )
    assert result.exit_code == 0, result.output
    mock_build.assert_called_once()
    assert mock_build.call_args.kwargs["network_install"] is False


def test_iso_cmd_rejects_no_network_install_flag_when_ks_has_url(tmp_path):
    src, ks, tail, out = _make_iso_cli_files(tmp_path, ks_has_url=True)
    with patch("ks_gen.cli.build_iso") as mock_build:
        result = runner.invoke(
            app,
            [
                "iso",
                "--src",
                str(src),
                "--ks",
                str(ks),
                "--tailoring",
                str(tail),
                "--out",
                str(out),
                "--no-network-install",
            ],
        )
    assert result.exit_code != 0
    mock_build.assert_not_called()


def test_iso_cmd_rejects_network_install_flag_when_ks_has_no_url(tmp_path):
    src, ks, tail, out = _make_iso_cli_files(tmp_path, ks_has_url=False)
    with patch("ks_gen.cli.build_iso") as mock_build:
        result = runner.invoke(
            app,
            [
                "iso",
                "--src",
                str(src),
                "--ks",
                str(ks),
                "--tailoring",
                str(tail),
                "--out",
                str(out),
                "--network-install",
            ],
        )
    assert result.exit_code != 0
    mock_build.assert_not_called()
