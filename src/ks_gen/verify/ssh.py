from __future__ import annotations

import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ks_gen.verify.auth import SudoAuth, sudo_command
from ks_gen.verify.errors import SshConnectError, ToolMissingError


@dataclass(frozen=True)
class SshResult:
    stdout: str
    stderr: str
    exit_code: int


def check_tools() -> None:
    if not shutil.which("ssh"):
        raise ToolMissingError("required tool not on PATH: ssh")


def _first_stderr_line(stderr: str) -> str:
    for line in stderr.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _ssh_argv(host: str, user: str, remote_cmd: str, extra_opts: list[str] | None) -> list[str]:
    """Build the ssh argv list shared by ssh_exec and sudo_pull."""
    argv: list[str] = ["ssh", "-o", "BatchMode=yes"]
    if extra_opts:
        argv.extend(extra_opts)
    argv.append(f"{user}@{host}")
    argv.append(remote_cmd)
    return argv


def ssh_exec(
    host: str,
    user: str,
    remote_cmd: str,
    *,
    extra_opts: list[str] | None = None,
    timeout: float | None = None,
    stdin_input: str | None = None,
) -> SshResult:
    cmd = _ssh_argv(host, user, remote_cmd, extra_opts)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            input=stdin_input,
        )
    except subprocess.TimeoutExpired as e:
        raise SshConnectError(f"ssh timed out after {timeout}s") from e
    except FileNotFoundError as e:
        raise ToolMissingError("ssh not on PATH") from e

    if proc.returncode == 255:
        raise SshConnectError(f"ssh exit 255: {_first_stderr_line(proc.stderr)}")

    return SshResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)


def sudo_pull(
    host: str,
    user: str,
    remote_path: str,
    local_path: Path,
    *,
    auth: SudoAuth,
    extra_opts: list[str] | None = None,
    timeout: float | None = None,
) -> None:
    """Retrieve a root-owned remote file via `sudo cat`, byte-for-byte.

    Runs the transfer in binary mode (no text decoding) so the local copy is
    an exact byte image of the on-host file — ARFs/tailoring may contain
    non-ASCII and must not be transcoded through the operator's locale codec.
    """
    remote_cmd, stdin_text = sudo_command(auth, f"cat {shlex.quote(remote_path)}")
    argv = _ssh_argv(host, user, remote_cmd, extra_opts)
    stdin_bytes = stdin_text.encode("utf-8") if stdin_text is not None else None
    try:
        proc = subprocess.run(
            argv, capture_output=True, timeout=timeout, check=False, input=stdin_bytes
        )
    except subprocess.TimeoutExpired as e:
        raise SshConnectError(f"sudo cat {remote_path} timed out after {timeout}s") from e
    except FileNotFoundError as e:
        raise ToolMissingError("ssh not on PATH") from e
    if proc.returncode != 0:
        stderr_text = proc.stderr.decode("utf-8", "replace")
        raise SshConnectError(
            f"sudo cat {remote_path} exit {proc.returncode}: {_first_stderr_line(stderr_text)}"
        )
    local_path.write_bytes(proc.stdout)
