from unittest.mock import patch

from ks_gen.iso import IsoBuildError, build_iso


def test_build_iso_calls_xorriso(tmp_path):
    src = tmp_path / "src.iso"
    src.write_bytes(b"\0" * 1024)
    ks = tmp_path / "ks.cfg"
    ks.write_text("text\n", encoding="utf-8")
    tail = tmp_path / "tailoring.xml"
    tail.write_text("<x/>", encoding="utf-8")
    out = tmp_path / "out.iso"
    with (
        patch("ks_gen.iso.shutil.which", return_value="/usr/bin/xorriso"),
        patch("ks_gen.iso.subprocess.run") as run,
    ):
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        build_iso(src, ks, tail, out, volid="ALMA9")
    assert run.called
    args = run.call_args[0][0]
    assert args[0] == "xorriso"
    assert str(out) in args


def test_build_iso_missing_xorriso_raises(tmp_path):
    src = tmp_path / "src.iso"
    src.write_bytes(b"\0")
    ks = tmp_path / "ks.cfg"
    ks.write_text("x", encoding="utf-8")
    tail = tmp_path / "t.xml"
    tail.write_text("x", encoding="utf-8")
    out = tmp_path / "out.iso"
    with patch("ks_gen.iso.shutil.which", return_value=None):
        try:
            build_iso(src, ks, tail, out, volid="ALMA9")
        except IsoBuildError as e:
            assert "xorriso" in str(e)
        else:
            raise AssertionError("expected IsoBuildError")
