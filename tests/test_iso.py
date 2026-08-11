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


# ---------------- alma10 (#58) ----------------
#
# EL10 install media has no /isolinux at all — BIOS boot moved to
# /boot/grub2/grub.cfg. The builder must fall back to it instead of
# aborting, and must not go looking for it on EL8/EL9 media.

ISOLINUX_STUB = "timeout 600\nlabel linux\n  kernel vmlinuz\n"
GRUB_STUB = "set timeout=60\nmenuentry 'foo' { linuxefi vmlinuz\ninitrdefi initrd.img\n}\n"


def _make_fake_run(missing=()):
    """xorriso stub whose -extract fails for the given ISO paths."""

    def fake_run(args, **kwargs):
        result = MagicMock()
        result.returncode = 0
        result.stderr = ""
        if "-extract" in args:
            idx = args.index("-extract")
            iso_path = args[idx + 1]
            if iso_path in missing:
                result.returncode = 1
                result.stderr = "isofs: file not found"
                return result
            dest = Path(args[idx + 2])
            dest.write_text(
                ISOLINUX_STUB if "isolinux" in iso_path else GRUB_STUB, encoding="utf-8"
            )
        return result

    return fake_run


def _iso_inputs(tmp_path):
    src = tmp_path / "src.iso"
    src.write_bytes(b"\0" * 1024)
    ks = tmp_path / "ks.cfg"
    ks.write_text("text\n", encoding="utf-8")
    tail = tmp_path / "tailoring.xml"
    tail.write_text("<x/>", encoding="utf-8")
    return src, ks, tail, tmp_path / "out.iso"


def _author_args(run_mock):
    calls = [c for c in run_mock.call_args_list if "replay" in c.args[0]]
    assert len(calls) == 1
    return calls[0].args[0]


def test_build_iso_falls_back_to_grub2_bios_cfg_when_no_isolinux(tmp_path):
    src, ks, tail, out = _iso_inputs(tmp_path)
    with (
        patch("ks_gen.iso.builder.shutil.which", return_value="/usr/bin/xorriso"),
        patch(
            "ks_gen.iso.builder.subprocess.run",
            side_effect=_make_fake_run(missing={"/isolinux/isolinux.cfg"}),
        ) as run,
    ):
        build_iso(src, ks, tail, out, volid="ALMA10")

    args = _author_args(run)
    assert "/boot/grub2/grub.cfg" in args
    assert "/isolinux/isolinux.cfg" not in args
    assert "/EFI/BOOT/grub.cfg" in args


def test_build_iso_bios_grub_entry_uses_plain_linux_loader(tmp_path):
    src, ks, tail, out = _iso_inputs(tmp_path)
    inner = _make_fake_run(missing={"/isolinux/isolinux.cfg"})
    captured = {}

    def fake_run(args, **kwargs):
        # The staged file only exists until build_iso's tempdir is cleaned up.
        if "replay" in args:
            staged = Path(args[args.index("/boot/grub2/grub.cfg") - 1])
            captured["bios"] = staged.read_text(encoding="utf-8")
        return inner(args, **kwargs)

    with (
        patch("ks_gen.iso.builder.shutil.which", return_value="/usr/bin/xorriso"),
        patch("ks_gen.iso.builder.subprocess.run", side_effect=fake_run),
    ):
        build_iso(src, ks, tail, out, volid="ALMA10")

    assert "  linux /images/pxeboot/vmlinuz" in captured["bios"]
    assert "  initrd /images/pxeboot/initrd.img" in captured["bios"]


def test_build_iso_does_not_probe_grub2_bios_cfg_when_isolinux_present(tmp_path):
    src, ks, tail, out = _iso_inputs(tmp_path)
    with (
        patch("ks_gen.iso.builder.shutil.which", return_value="/usr/bin/xorriso"),
        patch("ks_gen.iso.builder.subprocess.run", side_effect=_make_fake_run()) as run,
    ):
        build_iso(src, ks, tail, out, volid="ALMA9")

    args = _author_args(run)
    assert "/isolinux/isolinux.cfg" in args
    assert "/boot/grub2/grub.cfg" not in args


def test_build_iso_missing_efi_grub_raises(tmp_path):
    src, ks, tail, out = _iso_inputs(tmp_path)
    with (
        patch("ks_gen.iso.builder.shutil.which", return_value="/usr/bin/xorriso"),
        patch(
            "ks_gen.iso.builder.subprocess.run",
            side_effect=_make_fake_run(missing={"/EFI/BOOT/grub.cfg"}),
        ),
        pytest.raises(IsoBuildError, match=r"/EFI/BOOT/grub\.cfg"),
    ):
        build_iso(src, ks, tail, out, volid="ALMA10")


def test_build_iso_efi_only_media_authors_without_bios_entry(tmp_path):
    src, ks, tail, out = _iso_inputs(tmp_path)
    missing = {"/isolinux/isolinux.cfg", "/boot/grub2/grub.cfg"}
    with (
        patch("ks_gen.iso.builder.shutil.which", return_value="/usr/bin/xorriso"),
        patch("ks_gen.iso.builder.subprocess.run", side_effect=_make_fake_run(missing)) as run,
    ):
        patched = build_iso(src, ks, tail, out, volid="ALMA10")

    assert patched == ["/EFI/BOOT/grub.cfg"]
    args = _author_args(run)
    assert "/isolinux/isolinux.cfg" not in args
    assert "/boot/grub2/grub.cfg" not in args


def test_build_iso_reports_patched_bootloader_configs(tmp_path):
    src, ks, tail, out = _iso_inputs(tmp_path)
    with (
        patch("ks_gen.iso.builder.shutil.which", return_value="/usr/bin/xorriso"),
        patch(
            "ks_gen.iso.builder.subprocess.run",
            side_effect=_make_fake_run(missing={"/isolinux/isolinux.cfg"}),
        ),
    ):
        patched = build_iso(src, ks, tail, out, volid="ALMA10")

    assert patched == ["/boot/grub2/grub.cfg", "/EFI/BOOT/grub.cfg"]


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


def _iso_cmd_args(src, ks, tail, out):
    return ["iso", "--src", str(src), "--ks", str(ks), "--tailoring", str(tail), "--out", str(out)]


def test_iso_cmd_reports_patched_bootloader_configs(tmp_path):
    src, ks, tail, out = _make_iso_cli_files(tmp_path, ks_has_url=False)
    with patch("ks_gen.cli.build_iso", return_value=["/boot/grub2/grub.cfg", "/EFI/BOOT/grub.cfg"]):
        result = runner.invoke(app, _iso_cmd_args(src, ks, tail, out))
    assert result.exit_code == 0, result.output
    assert "/boot/grub2/grub.cfg" in result.output
    assert "/EFI/BOOT/grub.cfg" in result.output


def test_iso_cmd_warns_when_no_bios_bootloader_patched(tmp_path):
    src, ks, tail, out = _make_iso_cli_files(tmp_path, ks_has_url=False)
    with patch("ks_gen.cli.build_iso", return_value=["/EFI/BOOT/grub.cfg"]):
        result = runner.invoke(app, _iso_cmd_args(src, ks, tail, out))
    assert result.exit_code == 0, result.output
    assert "UEFI" in result.output


def test_iso_cmd_does_not_warn_when_bios_bootloader_patched(tmp_path):
    src, ks, tail, out = _make_iso_cli_files(tmp_path, ks_has_url=False)
    with patch(
        "ks_gen.cli.build_iso", return_value=["/isolinux/isolinux.cfg", "/EFI/BOOT/grub.cfg"]
    ):
        result = runner.invoke(app, _iso_cmd_args(src, ks, tail, out))
    assert result.exit_code == 0, result.output
    assert "UEFI" not in result.output


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
