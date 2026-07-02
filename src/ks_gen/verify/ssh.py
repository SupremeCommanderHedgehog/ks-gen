from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ks_gen.verify.errors import SshConnectError, ToolMissingError


@dataclass(frozen=True)
class SshResult:
    stdout: str
    stderr: str
    exit_code: int


def check_tools() -> None:
    for tool in ("ssh", "scp"):
        if not shutil.which(tool):
            raise ToolMissingError(f"required tool not on PATH: {tool}")


def _first_stderr_line(stderr: str) -> str:
    for line in stderr.splitlines():
        if line.strip():
            return line.strip()
    return ""


def ssh_exec(
    host: str,
    user: str,
    remote_cmd: str,
    *,
    extra_opts: list[str] | None = None,
    timeout: float | None = None,
    stdin_input: str | None = None,
) -> SshResult:
    cmd: list[str] = ["ssh", "-o", "BatchMode=yes"]
    if extra_opts:
        cmd.extend(extra_opts)
    cmd.append(f"{user}@{host}")
    cmd.append(remote_cmd)

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


def scp_pull(
    host: str,
    user: str,
    remote_path: str,
    local_path: Path,
    *,
    extra_opts: list[str] | None = None,
    timeout: float | None = None,
) -> None:
    cmd: list[str] = ["scp", "-o", "BatchMode=yes"]
    if extra_opts:
        cmd.extend(extra_opts)
    cmd.append(f"{user}@{host}:{remote_path}")
    cmd.append(str(local_path))

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as e:
        raise SshConnectError(f"scp timed out after {timeout}s") from e
    except FileNotFoundError as e:
        raise ToolMissingError("scp not on PATH") from e

    if proc.returncode != 0:
        raise SshConnectError(f"scp exit {proc.returncode}: {_first_stderr_line(proc.stderr)}")
