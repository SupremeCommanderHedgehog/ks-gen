from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ks_gen.config import HostConfig
from ks_gen.verify.errors import ArfMissingError, OscapInvocationError, VerifyError
from ks_gen.verify.ssg_version import (
    SsgVersionReport,
    build_ssg_version_report,
    parse_version_output,
    ssg_version_command,
)
from ks_gen.verify.ssh import _first_stderr_line

if TYPE_CHECKING:
    from ks_gen.verify.transport import Transport

REMOTE_CURRENT_ARF = "/tmp/ksgen-verify-current.arf.xml"
REMOTE_INSTALL_ARF = "/root/oscap-remediation-results.xml"
REMOTE_TAILORING = "/root/tailoring.xml"


@dataclass(frozen=True)
class CollectedArfs:
    current_text: str
    install_text: str | None
    ssg_version: SsgVersionReport | None = None


def _oscap_command(cfg: HostConfig) -> str:
    return (
        "oscap xccdf eval "
        f"--tailoring-file {REMOTE_TAILORING} "
        # Deliberately the BASE profile, unlike the install-time call in
        # ks.cfg.j2 which must name the tailored one (#65). verify's job is to
        # police the host against host.yaml, so it has to see the full rule
        # set: a deselected rule returns `notselected`, which reconcile buckets
        # as clean, so scoping the scan with the host's own tailoring would let
        # a stale or hand-edited tailoring shrink the very scan meant to catch
        # it. Exceptions are reconciled from host.yaml instead, and tailoring
        # drift is what --check-tailoring is for.
        f"--profile xccdf_org.ssgproject.content_profile_{cfg.meta.profile} "
        "--fetch-remote-resources "
        f"--results-arf {REMOTE_CURRENT_ARF} "
        f"/usr/share/xml/scap/ssg/content/{cfg.meta.scap_content}"
    )


def collect_arfs(
    *,
    cfg: HostConfig,
    transport: Transport,
    workdir: Path,
    no_drift: bool,
    timeout: int,
) -> CollectedArfs:
    transport.preflight()

    tailoring_check = transport.run(f"test -r {REMOTE_TAILORING}")
    if tailoring_check.exit_code != 0:
        raise OscapInvocationError(
            f"install-time tailoring not present at {REMOTE_TAILORING} "
            f"— host may not have been provisioned by ks-gen"
        )

    # Before the scan, not after: content drift is a leading explanation for
    # oscap failing outright (a profile that moved out of the host's content
    # exits non-zero), and a report collected after the eval would be missing
    # from exactly the failure it exists to explain (#90).
    ssg_version = collect_ssg_version(distro=cfg.distro, transport=transport, timeout=timeout)

    try:
        oscap_result = transport.run(_oscap_command(cfg), timeout=timeout)
        if oscap_result.exit_code not in (0, 2):
            stderr_first = _first_stderr_line(oscap_result.stderr)
            raise OscapInvocationError(
                f"oscap exit {oscap_result.exit_code}: {stderr_first}"
                f"{_ssg_version_hint(ssg_version)}"
            )

        local_current = workdir / "current.arf.xml"
        local_current.write_bytes(transport.read_root_file(REMOTE_CURRENT_ARF))
        if not local_current.exists() or local_current.stat().st_size == 0:
            raise ArfMissingError(f"pulled current ARF is empty or missing: {local_current}")
        current_text = local_current.read_text(encoding="utf-8")

        install_text: str | None = None
        if not no_drift:
            check = transport.run(f"test -r {REMOTE_INSTALL_ARF}")
            if check.exit_code == 0:
                local_install = workdir / "install.arf.xml"
                local_install.write_bytes(transport.read_root_file(REMOTE_INSTALL_ARF))
                if local_install.exists() and local_install.stat().st_size > 0:
                    install_text = local_install.read_text(encoding="utf-8")

        return CollectedArfs(
            current_text=current_text,
            install_text=install_text,
            ssg_version=ssg_version,
        )
    finally:
        try:
            transport.run(f"rm -f {REMOTE_CURRENT_ARF}")
        except Exception:
            # Best-effort cleanup; never mask the primary error.
            pass


def _ssg_version_hint(report: SsgVersionReport | None) -> str:
    """Name the content mismatch inline when oscap fails, if there is one."""
    if report is None or report.status in ("match", "unknown"):
        return ""
    return (
        f" (host runs {report.package} {report.installed}; "
        f"ks-gen expects {report.expected} — content drift can move a profile ID)"
    )


def collect_ssg_version(
    *,
    distro: str,
    transport: Transport,
    timeout: int | None = None,
) -> SsgVersionReport | None:
    """Ask the host which SSG package it has and compare against ks-gen's pin.

    Never raises: a failed query yields an `unknown` report, so it can't take
    down a verify run that has already produced results. Returns None when
    `distro` has no pinned expectation.

    Assumes the caller already ran `transport.preflight()`.
    """
    cmd = ssg_version_command(distro)
    if cmd is None:
        return None

    try:
        # Capped like every other remote call: an rpmdb lock or a stalled
        # channel would otherwise hang the run indefinitely, and this one is
        # informational — never worth blocking results for.
        result = transport.run(cmd, timeout=timeout) if timeout else transport.run(cmd)
    except (VerifyError, OSError) as e:
        return build_ssg_version_report(distro=distro, installed=None, error=str(e))

    if result.exit_code != 0:
        detail = _first_stderr_line(result.stderr) or _first_stderr_line(result.stdout)
        reason = f"query exited {result.exit_code}"
        return build_ssg_version_report(
            distro=distro,
            installed=None,
            error=f"{reason}: {detail}" if detail else reason,
        )

    installed = parse_version_output(result.stdout)
    if installed is None:
        return build_ssg_version_report(
            distro=distro, installed=None, error="query returned no version"
        )
    return build_ssg_version_report(distro=distro, installed=installed)


def collect_deployed_tailoring(
    *,
    transport: Transport,
    workdir: Path,
) -> str:
    """Read `/root/tailoring.xml` for drift comparison. Returns its text.

    Raises:
        SudoPromptError / ConfigError: preflight (sudo unavailable, or not root in local mode).
        OscapInvocationError: `/root/tailoring.xml` not readable on host.
        ArfMissingError: read succeeded but the file is 0 bytes.
        SshConnectError / ToolMissingError: transport failure.
    """
    transport.preflight()

    check = transport.run(f"test -r {REMOTE_TAILORING}")
    if check.exit_code != 0:
        raise OscapInvocationError(
            f"install-time tailoring not present at {REMOTE_TAILORING} "
            f"— host may not have been provisioned by ks-gen"
        )

    local = workdir / "deployed-tailoring.xml"
    local.write_bytes(transport.read_root_file(REMOTE_TAILORING))
    if not local.exists() or local.stat().st_size == 0:
        raise ArfMissingError(f"pulled tailoring is empty or missing: {local}")
    return local.read_text(encoding="utf-8")
