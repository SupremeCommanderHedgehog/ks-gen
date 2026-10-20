from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from ks_gen.cli import app
from ks_gen.iso import IsoBuild, IsoBuildError, KickstartReadError, VolidError, build_iso
from ks_gen.loader import ExitCode

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
        result.stdout = "Volume Id    : VENDOR\n"
        result.returncode = 0
        result.stderr = ""
        return result

    with (
        patch("ks_gen.iso.builder.shutil.which", return_value="/usr/bin/xorriso"),
        patch("ks_gen.iso.builder.subprocess.run", side_effect=fake_run) as run,
    ):
        build_iso(src, ks, tail, out, volid="ALMA9")

    # Four xorriso passes: extract isolinux, extract grub, report El Torito
    # (no EFI image in this stub, so no ESP patch), final author
    assert run.call_count == 4
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
        result.stdout = "Volume Id    : VENDOR\n"
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
        result.stdout = "Volume Id    : VENDOR\n"
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
        result.stdout = "Volume Id    : VENDOR\n"
        result.returncode = 0
        result.stderr = ""
        return result

    with (
        patch("ks_gen.iso.builder.shutil.which", return_value="/usr/bin/xorriso"),
        patch("ks_gen.iso.builder.subprocess.run", side_effect=fake_run),
        pytest.raises(IsoBuildError, match="bootloader rewrite aborted"),
    ):
        build_iso(src, ks, tail, out, volid="ALMA9")


@pytest.mark.parametrize(
    ("network_install", "ks_text", "expected"),
    [
        (True, "text\n", True),
        (False, 'url --url="https://m/"\n', False),
        # Unset: follows the kickstart, so a caller can't forget it (#136).
        (None, 'url --url="https://m/"\n', True),
        (None, "text\n", False),
    ],
)
def test_build_iso_forwards_network_install(tmp_path, network_install, ks_text, expected):
    src = tmp_path / "src.iso"
    src.write_bytes(b"\0" * 1024)
    ks = tmp_path / "ks.cfg"
    ks.write_text(ks_text, encoding="utf-8")
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
        result.stdout = "Volume Id    : VENDOR\n"
        result.returncode = 0
        result.stderr = ""
        return result

    with (
        patch("ks_gen.iso.builder.shutil.which", return_value="/usr/bin/xorriso"),
        patch("ks_gen.iso.builder.subprocess.run", side_effect=fake_run),
        patch("ks_gen.iso.builder.rewrite_isolinux", return_value="x") as ri,
        patch("ks_gen.iso.builder.rewrite_grub", return_value="x") as rg,
    ):
        build_iso(src, ks, tail, out, volid="DEV0", network_install=network_install)

    assert ri.call_args.kwargs["network_install"] is expected
    assert rg.call_args.kwargs["network_install"] is expected


@pytest.mark.parametrize("bad", ["missing", "latin-1"])
def test_build_iso_reports_an_unreadable_ks_cfg(tmp_path, bad):
    ks = tmp_path / "ks.cfg"
    if bad == "latin-1":
        ks.write_bytes("# caf\xe9\n".encode("latin-1"))
    match = "isn't valid UTF-8" if bad == "latin-1" else "cannot read"
    with pytest.raises(KickstartReadError, match=match):
        build_iso(tmp_path / "src.iso", ks, tmp_path / "t.xml", tmp_path / "o.iso")
    # Validated even when the caller decides network_install itself.
    with pytest.raises(KickstartReadError):
        build_iso(
            tmp_path / "src.iso", ks, tmp_path / "t.xml", tmp_path / "o.iso", network_install=True
        )


# ---------------- alma10 (#58) ----------------
#
# EL10 install media has no /isolinux at all — BIOS boot moved to
# /boot/grub2/grub.cfg. The builder must fall back to it instead of
# aborting, and must not go looking for it on EL8/EL9 media.

ISOLINUX_STUB = "timeout 600\nlabel linux\n  kernel vmlinuz\n"
GRUB_STUB = "set timeout=60\nmenuentry 'foo' { linuxefi vmlinuz\ninitrdefi initrd.img\n}\n"


def _make_fake_run(missing=(), *, volid="VENDOR", grub=None):
    """xorriso stub whose -extract fails for the given ISO paths. The source
    is labelled `volid`, and its grub configs read `grub` if given."""

    def fake_run(args, **kwargs):
        result = MagicMock()
        result.stdout = f"Volume Id    : {volid}\n"
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
            text = ISOLINUX_STUB if "isolinux" in iso_path else (grub or GRUB_STUB)
            dest.write_text(text, encoding="utf-8")
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
        patched = build_iso(src, ks, tail, out, volid="ALMA10").patched

    assert patched == ("/EFI/BOOT/grub.cfg",)
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
        patched = build_iso(src, ks, tail, out, volid="ALMA10").patched

    assert patched == ("/boot/grub2/grub.cfg", "/EFI/BOOT/grub.cfg")


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
    with patch("ks_gen.cli.build_iso", return_value=_built()) as mock_build:
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
    with patch("ks_gen.cli.build_iso", return_value=_built()) as mock_build:
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


def _built(patched=("/isolinux/isolinux.cfg", "/EFI/BOOT/grub.cfg"), volid="KS-AL9-8"):
    return IsoBuild(volid=volid, patched=tuple(patched))


def _iso_cmd_args(src, ks, tail, out):
    return ["iso", "--src", str(src), "--ks", str(ks), "--tailoring", str(tail), "--out", str(out)]


def test_iso_cmd_reports_patched_bootloader_configs(tmp_path):
    src, ks, tail, out = _make_iso_cli_files(tmp_path, ks_has_url=False)
    with patch(
        "ks_gen.cli.build_iso", return_value=_built(["/boot/grub2/grub.cfg", "/EFI/BOOT/grub.cfg"])
    ):
        result = runner.invoke(app, _iso_cmd_args(src, ks, tail, out))
    assert result.exit_code == 0, result.output
    assert "/boot/grub2/grub.cfg" in result.output
    assert "/EFI/BOOT/grub.cfg" in result.output


def test_iso_cmd_warns_when_no_bios_bootloader_patched(tmp_path):
    src, ks, tail, out = _make_iso_cli_files(tmp_path, ks_has_url=False)
    with patch("ks_gen.cli.build_iso", return_value=_built(["/EFI/BOOT/grub.cfg"])):
        result = runner.invoke(app, _iso_cmd_args(src, ks, tail, out))
    assert result.exit_code == 0, result.output
    assert "UEFI" in result.output


def test_iso_cmd_does_not_warn_when_bios_bootloader_patched(tmp_path):
    src, ks, tail, out = _make_iso_cli_files(tmp_path, ks_has_url=False)
    with patch("ks_gen.cli.build_iso", return_value=_built()):
        result = runner.invoke(app, _iso_cmd_args(src, ks, tail, out))
    assert result.exit_code == 0, result.output
    assert "UEFI" not in result.output


def test_iso_cmd_rejects_no_network_install_flag_when_ks_has_url(tmp_path):
    src, ks, tail, out = _make_iso_cli_files(tmp_path, ks_has_url=True)
    with patch("ks_gen.cli.build_iso", return_value=_built()) as mock_build:
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
    with patch("ks_gen.cli.build_iso", return_value=_built()) as mock_build:
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
    assert "it has no `url` install source" in result.output
    mock_build.assert_not_called()


def test_iso_cmd_rejects_a_non_utf8_ks_cfg(tmp_path):
    """Anaconda reads ks.cfg as UTF-8; refuse it at build time, not install."""
    src, ks, tail, out = _make_iso_cli_files(tmp_path, ks_has_url=True)
    ks.write_bytes("# caf\xe9\n".encode("latin-1") + ks.read_bytes())
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
    assert result.exit_code == int(ExitCode.USAGE), result.output
    assert "isn't valid UTF-8" in result.output
    mock_build.assert_not_called()


# --- #128: the volume ID is derived from the source, not hardcoded ALMA9 ----

_AL10_VENDOR = "AlmaLinux-10-2-x86_64-dvd"
_AL10_GRUB = (
    f"search --no-floppy --set=root -l '{_AL10_VENDOR}'\n"
    "set timeout=60\n"
    f"menuentry 'Install' {{ linuxefi vmlinuz inst.stage2=hd:LABEL={_AL10_VENDOR}\n"
    "initrdefi initrd.img\n}\n"
)


def _build_capturing_grub(tmp_path, fake_run, **kwargs):
    """build_iso with `fake_run` as xorriso; returns the result and the EFI
    grub.cfg as authored (the staged copy is gone once build_iso returns)."""
    src, ks, tail, out = _iso_inputs(tmp_path)
    authored = {}

    def run(args, **kw):
        if "replay" in args:
            i = args.index("/EFI/BOOT/grub.cfg")
            authored["grub"] = Path(args[i - 1]).read_text(encoding="utf-8")
        return fake_run(args, **kw)

    with (
        patch("ks_gen.iso.builder.shutil.which", return_value="/usr/bin/xorriso"),
        patch("ks_gen.iso.builder.subprocess.run", side_effect=run) as mock_run,
    ):
        built = build_iso(src, ks, tail, out, **kwargs)
    return built, authored["grub"], _author_args(mock_run)


def test_build_iso_defaults_to_the_derived_volid(tmp_path):
    """Our entry and the vendor's kept entries all look the media up by
    KS-AL<major>-<minor>, and the ISO is authored with that label."""
    built, grub, args = _build_capturing_grub(
        tmp_path, _make_fake_run(volid=_AL10_VENDOR, grub=_AL10_GRUB)
    )
    assert built.volid == "KS-AL10-2"
    assert args[args.index("-volid") + 1] == "KS-AL10-2"
    assert _AL10_VENDOR not in grub
    assert "-l 'KS-AL10-2'" in grub
    assert "inst.ks=hd:LABEL=KS-AL10-2:/ks.cfg" in grub


def test_build_iso_from_a_ks_gen_installer_keeps_its_label(tmp_path):
    """Rebuilding from a ks-gen ISO, even one given a custom --volid, keeps
    that label rather than deriving (WEB01 matches no AlmaLinux pattern)."""
    first, grub, _ = _build_capturing_grub(
        tmp_path, _make_fake_run(volid=_AL10_VENDOR, grub=_AL10_GRUB), volid="WEB01"
    )
    rebuilt, regrub, args = _build_capturing_grub(
        tmp_path, _make_fake_run(volid=first.volid, grub=grub)
    )
    assert rebuilt.volid == "WEB01"
    assert args[args.index("-volid") + 1] == "WEB01"
    assert regrub == grub


def test_build_iso_rejects_an_invalid_volid_before_running_xorriso(tmp_path):
    src, ks, tail, out = _iso_inputs(tmp_path)
    with (
        patch("ks_gen.iso.builder.shutil.which", return_value="/usr/bin/xorriso"),
        patch("ks_gen.iso.builder.subprocess.run") as run,
        pytest.raises(VolidError),
    ):
        build_iso(src, ks, tail, out, volid="MY LABEL")
    run.assert_not_called()


def test_iso_cmd_defaults_volid_and_reports_it(tmp_path):
    src, ks, tail, out = _make_iso_cli_files(tmp_path, ks_has_url=False)
    with patch("ks_gen.cli.build_iso", return_value=_built()) as mock_build:
        result = runner.invoke(app, _iso_cmd_args(src, ks, tail, out))
    assert result.exit_code == 0, result.output
    assert mock_build.call_args.kwargs["volid"] is None
    assert "volume ID KS-AL9-8" in result.output
    assert "Rufus" not in result.output


def test_iso_cmd_warns_when_the_volid_wont_survive_rufus_iso_mode(tmp_path):
    src, ks, tail, out = _make_iso_cli_files(tmp_path, ks_has_url=False)
    args = [*_iso_cmd_args(src, ks, tail, out), "--volid", "web01-installer"]
    with patch("ks_gen.cli.build_iso", return_value=_built(volid="web01-installer")):
        result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "Rufus" in result.output


def test_iso_cmd_invalid_volid_is_a_usage_error(tmp_path):
    src, ks, tail, out = _make_iso_cli_files(tmp_path, ks_has_url=False)
    args = [*_iso_cmd_args(src, ks, tail, out), "--volid", "a b"]
    with patch("ks_gen.cli.build_iso", side_effect=VolidError("invalid volume ID 'a b'")):
        result = runner.invoke(app, args)
    assert result.exit_code == int(ExitCode.USAGE)
    assert "invalid volume ID" in result.output
