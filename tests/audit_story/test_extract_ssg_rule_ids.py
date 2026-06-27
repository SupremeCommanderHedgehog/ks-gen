from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# scripts/ isn't a Python package (no __init__.py and not on sys.path); load
# the extractor module by file path so the tests don't depend on it being
# importable as `scripts.audit_story.extract_ssg_rule_ids`.
_EXTRACTOR_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "scripts"
    / "audit_story"
    / "extract_ssg_rule_ids.py"
)
_spec = importlib.util.spec_from_file_location("_extract_ssg_rule_ids", _EXTRACTOR_PATH)
assert _spec is not None and _spec.loader is not None
extract_ssg_rule_ids = importlib.util.module_from_spec(_spec)
sys.modules["_extract_ssg_rule_ids"] = extract_ssg_rule_ids
_spec.loader.exec_module(extract_ssg_rule_ids)


def _write_xccdf12(tmp_path: Path, rule_ids: list[str], *, name: str = "ds.xml") -> Path:
    """Write a minimal XCCDF 1.2 datastream-shaped XML with the given Rule ids."""
    rules = "\n".join(f'  <xccdf:Rule id="{rid}" selected="true"/>' for rid in rule_ids)
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<xccdf:Benchmark xmlns:xccdf="http://checklists.nist.gov/xccdf/1.2" id="xccdf_x_test">\n'
        f"{rules}\n"
        "</xccdf:Benchmark>\n"
    )
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def test_extract_rule_ids_from_known_xml(tmp_path):
    ids = ["xccdf_org.ssgproject.content_rule_a", "xccdf_org.ssgproject.content_rule_b"]
    path = _write_xccdf12(tmp_path, ids)
    assert extract_ssg_rule_ids.extract_rule_ids(path) == set(ids)


def test_extract_handles_rule_without_id_attribute(tmp_path):
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<xccdf:Benchmark xmlns:xccdf="http://checklists.nist.gov/xccdf/1.2" id="xccdf_x_test">\n'
        '  <xccdf:Rule id="xccdf_org.ssgproject.content_rule_has_id"/>\n'
        '  <xccdf:Rule selected="true"/>\n'  # no id= — should be silently skipped
        "</xccdf:Benchmark>\n"
    )
    p = tmp_path / "ds.xml"
    p.write_text(body, encoding="utf-8")
    assert extract_ssg_rule_ids.extract_rule_ids(p) == {"xccdf_org.ssgproject.content_rule_has_id"}


def test_extract_ignores_non_xccdf12_namespace(tmp_path):
    # A <Rule> outside the XCCDF 1.2 namespace must be skipped — extractor
    # pins to the SSG namespace so it doesn't pick up unrelated XML payloads
    # that happen to use a <Rule> tag.
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<other xmlns="http://example.invalid/other">\n'
        '  <Rule id="not_an_ssg_rule"/>\n'
        "</other>\n"
    )
    p = tmp_path / "ds.xml"
    p.write_text(body, encoding="utf-8")
    assert extract_ssg_rule_ids.extract_rule_ids(p) == set()


def test_write_rule_id_list_sorts_and_newline_terminates(tmp_path):
    out = tmp_path / "dist-rule-ids.txt"
    extract_ssg_rule_ids.write_rule_id_list({"c", "a", "b"}, out)
    assert out.read_text(encoding="utf-8") == "a\nb\nc\n"


def test_cross_distro_diff_emits_intersections_and_only_sets(tmp_path):
    per_distro = {
        "alma9": {"shared", "alma9_only"},
        "alma8": {"shared", "alma8_only"},
        "ubuntu2404": {"shared", "ubuntu_only"},
    }
    out = tmp_path / "diff.md"
    extract_ssg_rule_ids.write_cross_distro_diff(per_distro, out)
    text = out.read_text(encoding="utf-8")
    # Totals
    assert "`alma9`: 2 rules" in text
    assert "`alma8`: 2 rules" in text
    assert "`ubuntu2404`: 2 rules" in text
    # All-three intersection
    assert "1 rules shared across" in text
    # Per-distro-only callouts
    assert "`alma9_only`" in text
    assert "`alma8_only`" in text
    assert "`ubuntu_only`" in text


def test_cli_writes_per_distro_files_and_diff(tmp_path):
    a_xml = _write_xccdf12(tmp_path, ["x_shared", "x_a_only"], name="a.xml")
    b_xml = _write_xccdf12(tmp_path, ["x_shared", "x_b_only"], name="b.xml")
    out_dir = tmp_path / "out"
    rc = extract_ssg_rule_ids.main(
        [
            "--datastream",
            f"a={a_xml}",
            "--datastream",
            f"b={b_xml}",
            "--out-dir",
            str(out_dir),
        ]
    )
    assert rc == 0
    assert (out_dir / "a-rule-ids.txt").read_text(encoding="utf-8").splitlines() == [
        "x_a_only",
        "x_shared",
    ]
    assert (out_dir / "b-rule-ids.txt").read_text(encoding="utf-8").splitlines() == [
        "x_b_only",
        "x_shared",
    ]
    assert (out_dir / "cross-distro-rule-id-diff.md").is_file()


def test_cli_errors_on_missing_datastream(tmp_path, capsys):
    out_dir = tmp_path / "out"
    rc = extract_ssg_rule_ids.main(
        ["--datastream", f"a={tmp_path / 'missing.xml'}", "--out-dir", str(out_dir)]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "not found" in err


def test_cli_requires_label_equals_path_format():
    with pytest.raises(SystemExit):
        extract_ssg_rule_ids.main(["--datastream", "no-equals-here", "--out-dir", "/tmp"])
