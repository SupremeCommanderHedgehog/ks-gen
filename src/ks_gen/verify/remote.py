from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ks_gen.config import HostConfig
from ks_gen.verify.errors import ArfMissingError, OscapInvocationError
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


def _oscap_command(cfg: HostConfig) -> str:
    return (
        "oscap xccdf eval "
        f"--tailoring-file {REMOTE_TAILORING} "
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

    try:
        oscap_result = transport.run(_oscap_command(cfg), timeout=timeout)
        if oscap_result.exit_code not in (0, 2):
            stderr_first = _first_stderr_line(oscap_result.stderr)
            raise OscapInvocationError(f"oscap exit {oscap_result.exit_code}: {stderr_first}")

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

        return CollectedArfs(current_text=current_text, install_text=install_text)
    finally:
        try:
            transport.run(f"rm -f {REMOTE_CURRENT_ARF}")
        except Exception:
            # Best-effort cleanup; never mask the primary error.
            pass


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
