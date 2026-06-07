from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ks_gen.config import HostConfig
from ks_gen.verify.errors import (
    ArfMissingError,
    OscapInvocationError,
    SudoPromptError,
)
from ks_gen.verify.ssh import scp_pull, ssh_exec

REMOTE_CURRENT_ARF = "/tmp/ksgen-verify-current.arf.xml"
REMOTE_INSTALL_ARF = "/root/oscap-remediation-results.xml"
REMOTE_TAILORING = "/root/tailoring.xml"


@dataclass(frozen=True)
class CollectedArfs:
    current_text: str
    install_text: str | None


def probe_sudo(host: str, user: str, *, ssh_extra_opts: list[str]) -> None:
    result = ssh_exec(host, user, "sudo -n true", extra_opts=ssh_extra_opts)
    if result.exit_code != 0:
        raise SudoPromptError(
            f"sudo prompt detected on {host} as {user}: passwordless sudo is required"
        )


def _oscap_command(cfg: HostConfig) -> str:
    return (
        "sudo -n oscap xccdf eval "
        f"--tailoring-file {REMOTE_TAILORING} "
        f"--profile xccdf_org.ssgproject.content_profile_{cfg.meta.profile} "
        "--fetch-remote-resources "
        f"--results-arf {REMOTE_CURRENT_ARF} "
        f"/usr/share/xml/scap/ssg/content/{cfg.meta.scap_content}"
    )


def collect_arfs(
    *,
    cfg: HostConfig,
    host: str,
    user: str,
    workdir: Path,
    no_drift: bool,
    ssh_extra_opts: list[str],
    timeout: int,
) -> CollectedArfs:
    probe_sudo(host, user, ssh_extra_opts=ssh_extra_opts)

    tailoring_check = ssh_exec(
        host, user, f"sudo -n test -r {REMOTE_TAILORING}", extra_opts=ssh_extra_opts
    )
    if tailoring_check.exit_code != 0:
        raise OscapInvocationError(
            f"install-time tailoring not present at {REMOTE_TAILORING} "
            f"— host may not have been provisioned by ks-gen"
        )

    try:
        oscap_result = ssh_exec(
            host,
            user,
            _oscap_command(cfg),
            extra_opts=ssh_extra_opts,
            timeout=timeout,
        )
        if oscap_result.exit_code not in (0, 2):
            stderr_first = (oscap_result.stderr.splitlines() or [""])[0]
            raise OscapInvocationError(f"oscap exit {oscap_result.exit_code}: {stderr_first}")

        local_current = workdir / "current.arf.xml"
        scp_pull(
            host,
            user,
            REMOTE_CURRENT_ARF,
            local_current,
            extra_opts=ssh_extra_opts,
        )
        if not local_current.exists() or local_current.stat().st_size == 0:
            raise ArfMissingError(f"pulled current ARF is empty or missing: {local_current}")
        current_text = local_current.read_text(encoding="utf-8")

        install_text: str | None = None
        if not no_drift:
            check = ssh_exec(
                host,
                user,
                f"sudo -n test -r {REMOTE_INSTALL_ARF}",
                extra_opts=ssh_extra_opts,
            )
            if check.exit_code == 0:
                local_install = workdir / "install.arf.xml"
                scp_pull(
                    host,
                    user,
                    REMOTE_INSTALL_ARF,
                    local_install,
                    extra_opts=ssh_extra_opts,
                )
                if local_install.exists() and local_install.stat().st_size > 0:
                    install_text = local_install.read_text(encoding="utf-8")

        return CollectedArfs(current_text=current_text, install_text=install_text)
    finally:
        try:
            ssh_exec(
                host,
                user,
                f"sudo -n rm -f {REMOTE_CURRENT_ARF}",
                extra_opts=ssh_extra_opts,
            )
        except Exception:
            # Best-effort cleanup; never mask the primary error.
            pass
