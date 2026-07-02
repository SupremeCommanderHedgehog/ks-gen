from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ks_gen.config import HostConfig
from ks_gen.verify.auth import PASSWORDLESS, SudoAuth, sudo_command
from ks_gen.verify.errors import (
    ArfMissingError,
    OscapInvocationError,
    SudoPromptError,
)
from ks_gen.verify.ssh import SshResult, _first_stderr_line, ssh_exec, sudo_pull

REMOTE_CURRENT_ARF = "/tmp/ksgen-verify-current.arf.xml"
REMOTE_INSTALL_ARF = "/root/oscap-remediation-results.xml"
REMOTE_TAILORING = "/root/tailoring.xml"


@dataclass(frozen=True)
class CollectedArfs:
    current_text: str
    install_text: str | None


def _sudo_ssh(
    host: str,
    user: str,
    cmd: str,
    *,
    auth: SudoAuth,
    ssh_extra_opts: list[str],
    timeout: float | None = None,
) -> SshResult:
    """Run `cmd` under sudo, feeding the password on stdin in password mode."""
    remote_cmd, stdin_input = sudo_command(auth, cmd)
    return ssh_exec(
        host,
        user,
        remote_cmd,
        extra_opts=ssh_extra_opts,
        stdin_input=stdin_input,
        timeout=timeout,
    )


def probe_sudo(host: str, user: str, *, sudo_auth: SudoAuth, ssh_extra_opts: list[str]) -> None:
    result = _sudo_ssh(host, user, "true", auth=sudo_auth, ssh_extra_opts=ssh_extra_opts)
    if result.exit_code != 0:
        if sudo_auth.is_password:
            raise SudoPromptError(
                f"sudo failed (exit {result.exit_code}) on {host} as {user}: "
                f"wrong password or user not in sudoers"
            )
        raise SudoPromptError(
            f"sudo -n true failed (exit {result.exit_code}) on {host} as {user}: "
            f"passwordless sudo is required"
        )


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
    host: str,
    user: str,
    workdir: Path,
    no_drift: bool,
    ssh_extra_opts: list[str],
    timeout: int,
    sudo_auth: SudoAuth = PASSWORDLESS,
) -> CollectedArfs:
    probe_sudo(host, user, sudo_auth=sudo_auth, ssh_extra_opts=ssh_extra_opts)

    tailoring_check = _sudo_ssh(
        host, user, f"test -r {REMOTE_TAILORING}", auth=sudo_auth, ssh_extra_opts=ssh_extra_opts
    )
    if tailoring_check.exit_code != 0:
        raise OscapInvocationError(
            f"install-time tailoring not present at {REMOTE_TAILORING} "
            f"— host may not have been provisioned by ks-gen"
        )

    try:
        oscap_result = _sudo_ssh(
            host,
            user,
            _oscap_command(cfg),
            auth=sudo_auth,
            ssh_extra_opts=ssh_extra_opts,
            timeout=timeout,
        )
        if oscap_result.exit_code not in (0, 2):
            stderr_first = _first_stderr_line(oscap_result.stderr)
            raise OscapInvocationError(f"oscap exit {oscap_result.exit_code}: {stderr_first}")

        local_current = workdir / "current.arf.xml"
        sudo_pull(
            host, user, REMOTE_CURRENT_ARF, local_current, auth=sudo_auth, extra_opts=ssh_extra_opts
        )
        if not local_current.exists() or local_current.stat().st_size == 0:
            raise ArfMissingError(f"pulled current ARF is empty or missing: {local_current}")
        current_text = local_current.read_text(encoding="utf-8")

        install_text: str | None = None
        if not no_drift:
            check = _sudo_ssh(
                host,
                user,
                f"test -r {REMOTE_INSTALL_ARF}",
                auth=sudo_auth,
                ssh_extra_opts=ssh_extra_opts,
            )
            if check.exit_code == 0:
                local_install = workdir / "install.arf.xml"
                sudo_pull(
                    host,
                    user,
                    REMOTE_INSTALL_ARF,
                    local_install,
                    auth=sudo_auth,
                    extra_opts=ssh_extra_opts,
                )
                if local_install.exists() and local_install.stat().st_size > 0:
                    install_text = local_install.read_text(encoding="utf-8")

        return CollectedArfs(current_text=current_text, install_text=install_text)
    finally:
        try:
            _sudo_ssh(
                host,
                user,
                f"rm -f {REMOTE_CURRENT_ARF}",
                auth=sudo_auth,
                ssh_extra_opts=ssh_extra_opts,
            )
        except Exception:
            # Best-effort cleanup; never mask the primary error.
            pass


def collect_deployed_tailoring(
    *,
    host: str,
    user: str,
    workdir: Path,
    ssh_extra_opts: list[str],
    sudo_auth: SudoAuth = PASSWORDLESS,
) -> str:
    """Pull `/root/tailoring.xml` via sudo cat for drift comparison.

    Sibling to `collect_arfs`. Does not share state with the ARF pull —
    `--check-tailoring` and `--no-drift` are independent axes.

    Returns the file's text contents.

    Raises:
        SudoPromptError: sudo unavailable (passwordless) or wrong password.
        OscapInvocationError: `/root/tailoring.xml` not readable on host.
        ArfMissingError: pull succeeded but the pulled file is 0 bytes.
        SshConnectError: ssh transport failure.
        ToolMissingError: ssh not on PATH.
    """
    probe_sudo(host, user, sudo_auth=sudo_auth, ssh_extra_opts=ssh_extra_opts)

    check = _sudo_ssh(
        host, user, f"test -r {REMOTE_TAILORING}", auth=sudo_auth, ssh_extra_opts=ssh_extra_opts
    )
    if check.exit_code != 0:
        raise OscapInvocationError(
            f"install-time tailoring not present at {REMOTE_TAILORING} "
            f"— host may not have been provisioned by ks-gen"
        )

    local = workdir / "deployed-tailoring.xml"
    sudo_pull(host, user, REMOTE_TAILORING, local, auth=sudo_auth, extra_opts=ssh_extra_opts)
    if not local.exists() or local.stat().st_size == 0:
        raise ArfMissingError(f"pulled tailoring is empty or missing: {local}")
    return local.read_text(encoding="utf-8")
