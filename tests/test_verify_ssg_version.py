"""#90 step 4b — verify tells the operator when the host's SSG content differs.

Two things are guarded here: the comparison/rendering logic, and the agreement
between the pin in `ks_gen.verify.ssg_version` and the prose table in
`docs/audit-story/SSG-VERSIONS.md`. #90 was a fact recorded in two places that
drifted; recording it in two places again without a mechanical guard would be
the same mistake.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

from ks_gen.config import HostConfig
from ks_gen.verify.ssg_version import (
    EXPECTED_SSG_VERSIONS,
    build_ssg_version_report,
    parse_version_output,
    render_ssg_version_section,
    ssg_version_command,
)

# --- query construction ------------------------------------------------------


def test_rhel_family_queries_rpm() -> None:
    for distro in ("alma8", "alma9", "alma10"):
        cmd = ssg_version_command(distro)
        assert cmd is not None
        assert cmd.startswith("rpm -q ")
        assert "scap-security-guide" in cmd


def test_ubuntu_queries_dpkg_for_the_deb_derived_package() -> None:
    cmd = ssg_version_command("ubuntu2404")
    assert cmd is not None
    assert cmd.startswith("dpkg-query ")
    assert "ssg-debderived" in cmd


def test_unknown_distro_has_no_query() -> None:
    assert ssg_version_command("plan9") is None


# --- output parsing ----------------------------------------------------------


def test_parse_takes_the_version_release_string() -> None:
    assert parse_version_output("0.1.81-1.el8_10.alma.1\n") == "0.1.81-1.el8_10.alma.1"


def test_parse_accepts_a_bare_deb_version() -> None:
    assert parse_version_output("0.1.80-1") == "0.1.80-1"


def test_parse_rejects_the_rpm_not_installed_message() -> None:
    assert parse_version_output("package scap-security-guide is not installed\n") is None


def test_parse_rejects_empty_output() -> None:
    assert parse_version_output("  \n") is None


# --- comparison --------------------------------------------------------------


def _pin(distro: str) -> str:
    return EXPECTED_SSG_VERSIONS[distro].version


def test_exact_match_is_quiet() -> None:
    report = build_ssg_version_report(distro="alma8", installed=_pin("alma8"))
    assert report is not None
    assert report.status == "match"
    assert report.is_reportable is False
    assert render_ssg_version_section(report) == ""


def test_downstream_rebuild_of_the_same_content_release_is_a_match() -> None:
    """`0.1.81-2.el8_10.alma.2` carries the same upstream rule content."""
    report = build_ssg_version_report(distro="alma8", installed="0.1.81-2.el8_10.alma.2")
    assert report is not None
    assert report.status == "match"
    assert render_ssg_version_section(report) == ""


def test_older_content_names_both_versions_and_the_distro() -> None:
    report = build_ssg_version_report(distro="alma8", installed="0.1.74-1.el8.alma.1")
    assert report is not None
    assert report.status == "older"
    assert report.is_reportable is True
    out = render_ssg_version_section(report)
    assert "0.1.74-1.el8.alma.1" in out
    assert _pin("alma8") in out
    assert "alma8" in out
    assert "scap-security-guide" in out


def test_newer_content_names_both_versions_and_the_distro() -> None:
    report = build_ssg_version_report(distro="alma9", installed="0.1.85-1.el9_8.alma.1")
    assert report is not None
    assert report.status == "newer"
    out = render_ssg_version_section(report)
    assert "0.1.85-1.el9_8.alma.1" in out
    assert _pin("alma9") in out
    assert "alma9" in out


def test_older_and_newer_are_worded_differently() -> None:
    """Older is the dangerous direction and must not read like newer."""
    older = build_ssg_version_report(distro="alma8", installed="0.1.74-1.el8.alma.1")
    newer = build_ssg_version_report(distro="alma8", installed="0.1.99-1.el8_10.alma.1")
    assert older is not None and newer is not None
    older_text = render_ssg_version_section(older)
    newer_text = render_ssg_version_section(newer)
    assert "older" in older_text
    assert "newer" in newer_text
    assert "still selects" in older_text
    assert "still selects" not in newer_text


def test_uncomparable_versions_report_differs_not_a_direction() -> None:
    report = build_ssg_version_report(distro="alma8", installed="snapshot-git")
    assert report is not None
    assert report.status == "differs"
    out = render_ssg_version_section(report)
    assert "snapshot-git" in out
    assert "older" not in out
    assert "newer" not in out


def test_unknown_is_distinct_from_drift() -> None:
    report = build_ssg_version_report(distro="alma9", installed=None, error="rpm not on PATH")
    assert report is not None
    assert report.status == "unknown"
    assert report.installed is None
    out = render_ssg_version_section(report)
    assert "rpm not on PATH" in out
    assert "could not determine" in out
    # Never phrased as a mismatch — a failed query is not evidence of drift.
    assert "drift" not in out
    assert "older" not in out
    assert "newer" not in out


def test_unknown_without_a_reason_still_renders() -> None:
    report = build_ssg_version_report(distro="alma9", installed=None)
    assert report is not None
    assert report.status == "unknown"
    assert render_ssg_version_section(report) != ""


def test_a_distro_with_no_pin_yields_no_report() -> None:
    assert build_ssg_version_report(distro="plan9", installed="1.0") is None


def test_no_status_claims_a_failure() -> None:
    """Every rendered section says it is informational — see #90 step 4b."""
    for installed in ("0.1.74-1.el8.alma.1", "0.1.99-1.el8_10.alma.1", "snapshot-git", None):
        report = build_ssg_version_report(distro="alma8", installed=installed)
        assert report is not None
        assert "exit code" in render_ssg_version_section(report)


# --- code / SSG-VERSIONS.md agreement guard ----------------------------------

_DOC = Path(__file__).resolve().parent.parent / "docs" / "audit-story" / "SSG-VERSIONS.md"

# | AlmaLinux 8.10 | `alma8` | `scap-security-guide` | `0.1.81-1.el8_10.alma.1` | https://... |
_ROW = re.compile(
    r"^\|[^|]+\|\s*`(?P<distro>[a-z0-9]+)`\s*\|\s*`(?P<package>[^`]+)`\s*\|"
    r"\s*`(?P<version>[^`]+)`\s*\|"
)


def _documented_pins() -> dict[str, tuple[str, str]]:
    pins: dict[str, tuple[str, str]] = {}
    for line in _DOC.read_text(encoding="utf-8").splitlines():
        m = _ROW.match(line)
        if m is not None:
            pins[m.group("distro")] = (m.group("package"), m.group("version"))
    return pins


def test_the_doc_table_still_parses() -> None:
    """A reformatted table would silently disarm the agreement guard below."""
    assert _documented_pins(), f"no version rows parsed out of {_DOC.name}"


def test_code_pin_and_doc_table_agree() -> None:
    in_code = {d: (e.package, e.version) for d, e in EXPECTED_SSG_VERSIONS.items()}
    assert in_code == _documented_pins(), (
        "src/ks_gen/verify/ssg_version.py and docs/audit-story/SSG-VERSIONS.md "
        "disagree about the pinned SSG versions. Update both — verify reports "
        "content drift against the code copy, so a stale one lies to operators."
    )


def test_every_supported_distro_has_a_pin() -> None:
    """A new distro without a pin would silently skip the check on that target."""
    supported = set(get_args(HostConfig.model_fields["distro"].annotation))
    assert supported
    assert set(EXPECTED_SSG_VERSIONS) == supported
