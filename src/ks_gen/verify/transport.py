"""Execution transports for verify — swap ssh+sudo for local subprocess.

Every host-facing operation in verify reduces to two primitives: run a
command and read a root-owned file. `SshTransport` runs them over ssh with
sudo elevation (identical to the historical path); `LocalTransport` (added
later) runs them directly on the box. `collect_arfs`/`collect_deployed_tailoring`
will be ported to the `Transport` protocol so their orchestration is
transport-agnostic.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ks_gen.loader import ConfigError, ExitCode
from ks_gen.verify.auth import SudoAuth
from ks_gen.verify.errors import ArfMissingError, OscapInvocationError, ToolMissingError
from ks_gen.verify.ssh import _sudo_ssh, probe_sudo, sudo_read


@dataclass(frozen=True)
class CmdResult:
    stdout: str
    stderr: str
    exit_code: int


class Transport(Protocol):
    def preflight(self) -> None:
        """Raise if the host isn't ready (sudo/auth for ssh; root+oscap for local)."""

    def run(self, cmd: str, *, timeout: float | None = None) -> CmdResult:
        """Run `cmd` with root privileges and capture stdout/stderr/exit code."""

    def read_root_file(self, path: str) -> bytes:
        """Return the raw bytes of a root-owned file."""


@dataclass(frozen=True)
class SshTransport:
    """Run over ssh, elevating each command with sudo (per `sudo_auth`)."""

    host: str
    user: str
    ssh_extra_opts: list[str]
    sudo_auth: SudoAuth

    def preflight(self) -> None:
        probe_sudo(
            self.host, self.user, sudo_auth=self.sudo_auth, ssh_extra_opts=self.ssh_extra_opts
        )

    def run(self, cmd: str, *, timeout: float | None = None) -> CmdResult:
        r = _sudo_ssh(
            self.host,
            self.user,
            cmd,
            auth=self.sudo_auth,
            ssh_extra_opts=self.ssh_extra_opts,
            timeout=timeout,
        )
        return CmdResult(stdout=r.stdout, stderr=r.stderr, exit_code=r.exit_code)

    def read_root_file(self, path: str) -> bytes:
        return sudo_read(
            self.host, self.user, path, auth=self.sudo_auth, extra_opts=self.ssh_extra_opts
        )


class LocalTransport:
    """Run directly on the target as root — no ssh, no sudo.

    `preflight()` is the readiness gate: it requires EUID 0 (guarded so it
    fails cleanly on non-Linux dev machines) and `oscap` on PATH. Commands are
    run without a shell (`shlex.split`); the verify command strings
    (`test -r …`, `rm -f …`, `oscap xccdf eval …`) all split to real binaries.
    """

    def preflight(self) -> None:
        geteuid = getattr(os, "geteuid", None)
        if geteuid is None or geteuid() != 0:
            raise ConfigError(
                "verify --local must run as root (EUID 0); re-run under sudo",
                ExitCode.USAGE,
            )
        if shutil.which("oscap") is None:
            raise ToolMissingError("required tool not on PATH: oscap")

    def run(self, cmd: str, *, timeout: float | None = None) -> CmdResult:
        argv = shlex.split(cmd)
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            raise OscapInvocationError(f"local command timed out after {timeout}s: {cmd}") from e
        except FileNotFoundError as e:
            raise ToolMissingError(f"command not found: {argv[0]}") from e
        return CmdResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)

    def read_root_file(self, path: str) -> bytes:
        try:
            return Path(path).read_bytes()
        except FileNotFoundError as e:
            raise ArfMissingError(f"expected file not present: {path}") from e
