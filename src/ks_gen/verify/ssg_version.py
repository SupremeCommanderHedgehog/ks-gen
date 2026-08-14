"""Does the host's SSG content match what ks-gen was validated against? (#90)

ks-gen decides which rules to disable, what crypto policy to apply and which
rules are FIPS-dependent from extracts of specific SSG releases (see
`docs/audit-story/SSG-VERSIONS.md`). When a host runs different content those
decisions can be wrong, and to the operator the failures look inexplicable —
that was #90 on AlmaLinux 8.

Reported, never gated. A host installed months ago legitimately ships newer
content, so an exit code here would only train people to ignore it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Manager = Literal["rpm", "dpkg"]
SsgVersionStatus = Literal["match", "older", "newer", "differs", "unknown"]


@dataclass(frozen=True)
class ExpectedSsg:
    """The SSG package ks-gen's checked-in extracts were taken from."""

    package: str
    version: str
    manager: Manager


# Machine-readable twin of the table in docs/audit-story/SSG-VERSIONS.md.
# tests/test_verify_ssg_version.py fails if the two disagree.
EXPECTED_SSG_VERSIONS: dict[str, ExpectedSsg] = {
    "alma8": ExpectedSsg("scap-security-guide", "0.1.81-1.el8_10.alma.1", "rpm"),
    "alma9": ExpectedSsg("scap-security-guide", "0.1.81-1.el9_8.alma.1", "rpm"),
    "alma10": ExpectedSsg("scap-security-guide", "0.1.81-1.el10_2.alma.1", "rpm"),
    "ubuntu2404": ExpectedSsg("ssg-debderived", "0.1.80-1", "dpkg"),
}


@dataclass(frozen=True)
class SsgVersionReport:
    """Host SSG content version vs the pinned one. `installed is None` means
    the query didn't answer — explicitly not the same thing as a mismatch."""

    distro: str
    package: str
    expected: str
    installed: str | None
    status: SsgVersionStatus
    detail: str | None = None

    @property
    def is_reportable(self) -> bool:
        """Worth the operator's attention — a match is not."""
        return self.status != "match"


def ssg_version_command(distro: str) -> str | None:
    """Shell command printing the installed SSG version, or None if unpinned.

    Both forms print a bare version string and nothing else, so the output
    parses the same way whichever package manager answered.
    """
    expected = EXPECTED_SSG_VERSIONS.get(distro)
    if expected is None:
        return None
    if expected.manager == "rpm":
        return f"rpm -q --qf '%{{VERSION}}-%{{RELEASE}}\\n' {expected.package}"
    return f"dpkg-query -W -f='${{Version}}' {expected.package}"


_VERSION_TOKEN = re.compile(r"^\d\S*$")


def parse_version_output(stdout: str) -> str | None:
    """First line of the query output, if it looks like a version.

    `rpm -q` on a missing package prints "package X is not installed" on
    stdout, so shape has to be checked rather than trusted.
    """
    for line in stdout.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        return candidate if _VERSION_TOKEN.match(candidate) else None
    return None


_EPOCH = re.compile(r"^\d+:")
_CONTENT_RELEASE = re.compile(r"^(\d+(?:\.\d+)*)")


def _content_release(version: str) -> tuple[int, ...] | None:
    """The leading `X.Y.Z` — the upstream SSG release, sans epoch and suffix."""
    match = _CONTENT_RELEASE.match(_EPOCH.sub("", version))
    if match is None:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def build_ssg_version_report(
    *,
    distro: str,
    installed: str | None,
    error: str | None = None,
) -> SsgVersionReport | None:
    """Compare `installed` against the pin. None when `distro` has no pin.

    A match is upstream-release equality (`0.1.81`), not raw string equality:
    the downstream build suffix (`-1.el8_10.alma.1`) is a rebuild of the same
    rule content, and nagging every host over `.alma.1` -> `.alma.2` would bury
    the signal. Content movement *within* one upstream release is what
    `.github/workflows/ssg-drift.yml` re-extracts weekly to catch.
    """
    expected = EXPECTED_SSG_VERSIONS.get(distro)
    if expected is None:
        return None

    def _report(status: SsgVersionStatus, detail: str | None = None) -> SsgVersionReport:
        return SsgVersionReport(
            distro=distro,
            package=expected.package,
            expected=expected.version,
            installed=installed,
            status=status,
            detail=detail,
        )

    if installed is None:
        return _report("unknown", error)
    if installed == expected.version:
        return _report("match")

    host_release = _content_release(installed)
    pinned_release = _content_release(expected.version)
    if host_release is None or pinned_release is None:
        return _report("differs")
    if host_release == pinned_release:
        return _report("match")
    return _report("older" if host_release < pinned_release else "newer")


_INFORMATIONAL = "  Reported only — this does not affect the exit code.\n"


def render_ssg_version_section(report: SsgVersionReport) -> str:
    """Human-readable section for the verify text report.

    Empty string on a match, so the caller doesn't have to gate on it.
    """
    if report.status == "match":
        return ""

    if report.status == "unknown":
        reason = f" ({report.detail})" if report.detail else ""
        return (
            f"SSG content version: could not determine the installed {report.package} "
            f"on this {report.distro} host{reason}.\n"
            f"  ks-gen's rule decisions were validated against {report.expected}; "
            f"the check was skipped.\n" + _INFORMATIONAL
        )

    direction = {
        "older": "host is older",
        "newer": "host is newer",
        "differs": "versions are not comparable",
    }[report.status]
    lines = [
        f"SSG content drift: this {report.distro} host runs {report.package} "
        f"{report.installed}; ks-gen expects {report.expected} ({direction}).\n"
    ]
    if report.status == "older":
        lines.append(
            "  Older is the dangerous direction: ks-gen may be disabling rules this "
            "version still selects, or naming rules it does not ship.\n"
        )
    elif report.status == "newer":
        lines.append(
            "  ks-gen's checked-in SSG extracts predate this host's content, so its "
            "rule decisions may be stale.\n"
        )
    lines.append(_INFORMATIONAL)
    return "".join(lines)
