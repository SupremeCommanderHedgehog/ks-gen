"""The EFI system partition's grub.cfg is patched too (#116).

GRUB booted from a USB stick reads the ESP image's EFI/BOOT/grub.cfg, not the
ISO9660 tree's. `-boot_image any replay` reinstates the vendor ESP verbatim, so
unless build_iso patches it the stick boots the vendor menu, whose label search
no longer matches the renamed volume, and every entry fails.

The integration tests author tiny source ISOs in the two layouts AlmaLinux
ships — EL8/EL9's /images/efiboot.img file and EL10's appended GPT partition —
and run the real xorriso + mtools pipeline over them.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ks_gen.iso import IsoBuildError, build_iso
from ks_gen.iso._menu import IDEMPOTENCY_MARKER
from ks_gen.iso.builder import _retarget, _vendor_volid

VENDOR_GRUB = (
    'set default="1"\n'
    "set timeout=60\n"
    "search --no-floppy --set=root -l 'VENDOR'\n"
    "menuentry 'Install' {\n"
    "\tlinuxefi /images/pxeboot/vmlinuz inst.stage2=hd:LABEL=VENDOR\n"
    "}\n"
)
MTOOLS_ENV = {**os.environ, "MTOOLS_SKIP_CHECK": "1"}

needs_tools = pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("xorriso", "mformat", "mmd", "mcopy")),
    reason="needs xorriso and mtools",
)


def _sh(*args: str | Path) -> str:
    result = subprocess.run(
        [str(a) for a in args], capture_output=True, text=True, env=MTOOLS_ENV, check=True
    )
    return result.stdout


def _make_esp(path: Path, grub_cfg: Path | None) -> None:
    _sh("mformat", "-C", "-i", path, "-T", "2880", "-h", "2", "-s", "18", "::")
    _sh("mmd", "-i", path, "::/EFI", "::/EFI/BOOT")
    if grub_cfg is not None:
        _sh("mcopy", "-i", path, grub_cfg, "::/EFI/BOOT/grub.cfg")


def _make_source_iso(tmp_path: Path, layout: str) -> Path:
    tree = tmp_path / "tree"
    (tree / "EFI/BOOT").mkdir(parents=True)
    (tree / "images").mkdir()
    cfg = tree / "EFI/BOOT/grub.cfg"
    cfg.write_text(VENDOR_GRUB, encoding="utf-8")
    esp = tmp_path / "vendor-esp.img"
    _make_esp(esp, cfg)
    src = tmp_path / f"{layout}.iso"
    mkisofs = ["xorriso", "-as", "mkisofs", "-quiet", "-V", "VENDOR"]
    if layout == "tree":
        shutil.copy(esp, tree / "images/efiboot.img")
        _sh(*mkisofs, "-e", "images/efiboot.img", "-no-emul-boot", "-o", src, tree)
    else:
        _sh(
            *mkisofs,
            "-append_partition", "2", "0xef", esp, "-appended_part_as_gpt",
            "-e", "--interval:appended_partition_2:all::", "-no-emul-boot",
            "-o", src, tree,
        )  # fmt: skip
    return src


def _inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    ks = tmp_path / "ks.cfg"
    ks.write_text("text\n", encoding="utf-8")
    tail = tmp_path / "tailoring.xml"
    tail.write_text("<x/>", encoding="utf-8")
    return ks, tail, tmp_path / "out.iso"


def _out_esp(out: Path, layout: str, tmp_path: Path) -> Path:
    """Copy the built ISO's ESP image out, the way firmware would find it."""
    dest = tmp_path / "out-esp.img"
    if layout == "tree":
        _sh("xorriso", "-osirrox", "on", "-indev", out, "-extract", "/images/efiboot.img", dest)
        return dest
    report = _sh("xorriso", "-indev", out, "-report_el_torito", "plain")
    lba = next(
        int(ln.split()[-1]) for ln in report.splitlines() if "boot img" in ln and "UEFI" in ln
    )
    size = 2880 * 512
    with out.open("rb") as f:
        f.seek(lba * 2048)  # El Torito LBAs are 2048-byte blocks
        dest.write_bytes(f.read(size))
    return dest


@needs_tools
@pytest.mark.parametrize("layout", ["tree", "appended"])
def test_esp_grub_cfg_carries_the_unattended_entry(tmp_path: Path, layout: str) -> None:
    src = _make_source_iso(tmp_path, layout)
    ks, tail, out = _inputs(tmp_path)

    patched = build_iso(src, ks, tail, out, volid="KSGEN")

    label = "/images/efiboot.img" if layout == "tree" else "EFI partition 2"
    assert patched[-1] == f"{label}:/EFI/BOOT/grub.cfg"
    esp_cfg = _sh("mtype", "-i", _out_esp(out, layout, tmp_path), "::/EFI/BOOT/grub.cfg")
    assert IDEMPOTENCY_MARKER in esp_cfg
    assert 'set default="0"' in esp_cfg
    assert "-l 'KSGEN'" in esp_cfg
    assert "inst.ks=hd:LABEL=KSGEN:/ks.cfg" in esp_cfg


@needs_tools
def test_appended_esp_replaces_the_vendor_partition(tmp_path: Path) -> None:
    """The EFI El Torito entry and GPT partition 2 both point at the patched
    image — replay must not leave a second, vendor copy reachable."""
    src = _make_source_iso(tmp_path, "appended")
    ks, tail, out = _inputs(tmp_path)

    build_iso(src, ks, tail, out, volid="KSGEN")

    report = _sh(
        "xorriso", "-indev", out, "-report_el_torito", "plain", "-report_system_area", "plain"
    )
    lines = report.splitlines()
    lba = next(int(ln.split()[-1]) for ln in lines if "boot img" in ln and "UEFI" in ln)
    gpt2 = next(ln for ln in lines if ln.startswith("GPT start and size :   2"))
    assert int(gpt2.split()[-2]) == lba * 4
    assert sum("Appended" in ln and "partname local" in ln for ln in lines) == 1


@needs_tools
def test_esp_without_grub_cfg_raises(tmp_path: Path) -> None:
    """A USB stick would boot whatever the ESP falls back to; fail the build
    rather than ship media that only installs from CD."""
    src = _make_source_iso(tmp_path, "tree")
    bare = tmp_path / "bare-esp.img"
    _make_esp(bare, None)
    tree = tmp_path / "tree"
    shutil.copy(bare, tree / "images/efiboot.img")
    src.unlink()
    _sh("xorriso", "-as", "mkisofs", "-quiet", "-V", "VENDOR",
        "-e", "images/efiboot.img", "-no-emul-boot", "-o", src, tree)  # fmt: skip
    ks, tail, out = _inputs(tmp_path)

    with pytest.raises(IsoBuildError, match=r"reading /images/efiboot.img:/EFI/BOOT/grub.cfg"):
        build_iso(src, ks, tail, out, volid="KSGEN")


@needs_tools
@pytest.mark.parametrize("layout", ["tree", "appended"])
def test_vendor_entries_follow_the_renamed_volume(tmp_path: Path, layout: str) -> None:
    """The vendor entries kept below ours are the documented fallback; they
    must search for the volume as renamed, not the vendor's label."""
    src = _make_source_iso(tmp_path, layout)
    ks, tail, out = _inputs(tmp_path)

    build_iso(src, ks, tail, out, volid="KSGEN")

    tree_cfg = tmp_path / "tree-grub.cfg"
    _sh("xorriso", "-osirrox", "on", "-indev", out, "-extract", "/EFI/BOOT/grub.cfg", tree_cfg)
    esp_cfg = _sh("mtype", "-i", _out_esp(out, layout, tmp_path), "::/EFI/BOOT/grub.cfg")
    for cfg in (esp_cfg, tree_cfg.read_text(encoding="utf-8")):
        assert "VENDOR" not in cfg
        assert "inst.stage2=hd:LABEL=KSGEN" in cfg


@needs_tools
def test_tree_esp_image_stays_read_only(tmp_path: Path) -> None:
    src = _make_source_iso(tmp_path, "tree")
    ks, tail, out = _inputs(tmp_path)

    build_iso(src, ks, tail, out, volid="KSGEN")

    listing = _sh("xorriso", "-indev", out, "-lsl", "/images/efiboot.img")
    assert listing.lstrip().startswith("-r--r--r--")


def _which(missing: str):
    return lambda name: None if name == missing else f"/usr/bin/{name}"


@needs_tools
def test_missing_mcopy_raises_when_there_is_an_esp_to_patch(tmp_path: Path) -> None:
    src = _make_source_iso(tmp_path, "tree")
    ks, tail, out = _inputs(tmp_path)
    with (
        patch("ks_gen.iso.builder.shutil.which", side_effect=_which("mcopy")),
        pytest.raises(IsoBuildError, match="mtools"),
    ):
        build_iso(src, ks, tail, out, volid="KSGEN")


@needs_tools
def test_mcopy_is_not_required_without_an_efi_image(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    (tree / "EFI/BOOT").mkdir(parents=True)
    (tree / "EFI/BOOT/grub.cfg").write_text(VENDOR_GRUB, encoding="utf-8")
    src = tmp_path / "noefi.iso"
    _sh("xorriso", "-as", "mkisofs", "-quiet", "-V", "VENDOR", "-o", src, tree)
    ks, tail, out = _inputs(tmp_path)
    with patch("ks_gen.iso.builder.shutil.which", side_effect=_which("mcopy")):
        assert build_iso(src, ks, tail, out, volid="KSGEN") == ["/EFI/BOOT/grub.cfg"]


def _report_only_run(report: str):
    """xorriso stub: -extract writes a grub.cfg, -report_el_torito prints `report`."""

    def fake_run(args, **kwargs):
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        if "-extract" in args:
            idx = args.index("-extract")
            if "isolinux" in args[idx + 1]:
                result.returncode = 1
                return result
            Path(args[idx + 2]).write_text(VENDOR_GRUB, encoding="utf-8")
        elif "-report_el_torito" in args:
            result.stdout = "Volume Id    : VENDOR\n" + report
        return result

    return fake_run


@pytest.mark.parametrize(
    ("report", "message"),
    [
        ("-boot_image any efi_path='--interval:imported_iso:10d-20d::'\n", "unsupported"),
        (
            "-boot_image any efi_path='/a.img'\n-boot_image any efi_path='/b.img'\n",
            "2 EFI boot images",
        ),
        (
            "-boot_image any efi_path="
            "'--interval:appended_partition_2_start_35s_size_2880d:all::'\n",
            "no source interval",
        ),
    ],
)
def test_unrecognised_esp_source_raises(tmp_path: Path, report: str, message: str) -> None:
    src = tmp_path / "src.iso"
    src.write_bytes(b"\0" * 1024)
    ks, tail, out = _inputs(tmp_path)
    with (
        patch("ks_gen.iso.builder.shutil.which", return_value="/usr/bin/x"),
        patch("ks_gen.iso.builder.subprocess.run", side_effect=_report_only_run(report)),
        pytest.raises(IsoBuildError, match=message),
    ):
        build_iso(src, ks, tail, out, volid="KSGEN")


def test_appended_esp_is_copied_from_its_interval_and_appended_after_replay(
    tmp_path: Path,
) -> None:
    """Runs without xorriso/mtools (CI): the partition bytes come from the
    reported 512-byte-block interval, and the override follows `replay`."""
    src = tmp_path / "src.iso"
    src.write_bytes(b"\0" * 512 * 4 + b"E" * 512 * 3 + b"\0" * 512)
    ks, tail, out = _inputs(tmp_path)
    report = (
        "-append_partition 2 28732ac11ff8d211ba4b00a0c93ec93b "
        "--interval:imported_iso:4d-6d::'src.iso'\n"
        "-boot_image any efi_path='--interval:appended_partition_2_start_1s_size_3d:all::'\n"
    )
    copied: list[bytes] = []
    base = _report_only_run(report)

    def fake_run(args, **kwargs):
        if args[0] == "mcopy":
            if args[1] == "-n":  # read the ESP's grub.cfg out
                copied.append(Path(args[3]).read_bytes())
                Path(args[5]).write_text(VENDOR_GRUB, encoding="utf-8")
            result = MagicMock()
            result.returncode, result.stdout, result.stderr = 0, "", ""
            return result
        return base(args, **kwargs)

    with (
        patch("ks_gen.iso.builder.shutil.which", return_value="/usr/bin/x"),
        patch("ks_gen.iso.builder.subprocess.run", side_effect=fake_run) as run,
    ):
        patched = build_iso(src, ks, tail, out, volid="KSGEN")

    assert copied == [b"E" * 512 * 3]
    assert patched[-1] == "EFI partition 2:/EFI/BOOT/grub.cfg"
    author = next(c.args[0] for c in run.call_args_list if "replay" in c.args[0])
    i = author.index("-append_partition")
    assert author.index("replay") < i
    assert author[i + 1 : i + 3] == ["2", "28732ac11ff8d211ba4b00a0c93ec93b"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("search -l 'VENDOR'", "search -l 'KSGEN'"),
        ("search -l VENDOR\n", "search -l KSGEN\n"),
        ("inst.stage2=hd:LABEL=VENDOR quiet", "inst.stage2=hd:LABEL=KSGEN quiet"),
        ("inst.ks=hd:LABEL=VENDOR:/ks.cfg", "inst.ks=hd:LABEL=KSGEN:/ks.cfg"),
        ("hd:LABEL=VENDOR-extra", "hd:LABEL=VENDOR-extra"),
        ("hd:LABEL=MYVENDOR", "hd:LABEL=MYVENDOR"),
    ],
)
def test_retarget_rewrites_whole_labels_only(text: str, expected: str) -> None:
    assert _retarget(text, "VENDOR", "KSGEN") == expected


def test_vendor_volid_is_read_from_the_pvd() -> None:
    assert _vendor_volid("Volume Id    : AlmaLinux-9-8-x86_64-dvd\n") == "AlmaLinux-9-8-x86_64-dvd"


def test_missing_vendor_volid_raises() -> None:
    with pytest.raises(IsoBuildError, match="Volume Id"):
        _vendor_volid("-boot_image any efi_path='/x'\n")
