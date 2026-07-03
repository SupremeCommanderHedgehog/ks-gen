from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from ks_gen.verify.auth import SudoAuth
from ks_gen.verify.errors import SshConnectError, ToolMissingError
from ks_gen.verify.ssh import SshResult, check_tools, ssh_exec, sudo_read


def _completed(
    returncode: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_check_tools_passes_when_ssh_present() -> None:
    with patch("ks_gen.verify.ssh.shutil.which", side_effect=lambda t: f"/usr/bin/{t}"):
        check_tools()


def test_check_tools_raises_when_ssh_missing() -> None:
    def which(tool: str) -> str | None:
        return None if tool == "ssh" else f"/usr/bin/{tool}"

    with (
        patch("ks_gen.verify.ssh.shutil.which", side_effect=which),
        pytest.raises(ToolMissingError, match="ssh"),
    ):
        check_tools()


def test_ssh_exec_returns_result_on_zero_exit() -> None:
    with patch("ks_gen.verify.ssh.subprocess.run", return_value=_completed(0, "out", "")) as run:
        result = ssh_exec("host", "user", "ls /", extra_opts=["-o", "StrictHostKeyChecking=yes"])
    assert result == SshResult(stdout="out", stderr="", exit_code=0)
    args = run.call_args.args[0]
    assert args[0] == "ssh"
    assert "-o" in args and "BatchMode=yes" in args
    assert "StrictHostKeyChecking=yes" in args
    assert args[-2] == "user@host"
    assert args[-1] == "ls /"


def test_ssh_exec_exit_255_raises_ssh_connect_error() -> None:
    stderr = "ssh: connect to host h port 22: Connection refused\n"
    with (
        patch("ks_gen.verify.ssh.subprocess.run", return_value=_completed(255, "", stderr)),
        pytest.raises(SshConnectError, match="Connection refused"),
    ):
        ssh_exec("host", "user", "ls /")


def test_ssh_exec_timeout_raises_ssh_connect_error() -> None:
    with (
        patch(
            "ks_gen.verify.ssh.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["ssh"], timeout=1),
        ),
        pytest.raises(SshConnectError, match="timed out"),
    ):
        ssh_exec("host", "user", "ls /", timeout=1)


def test_ssh_exec_file_not_found_raises_tool_missing() -> None:
    with (
        patch("ks_gen.verify.ssh.subprocess.run", side_effect=FileNotFoundError()),
        pytest.raises(ToolMissingError, match="ssh"),
    ):
        ssh_exec("host", "user", "ls /")


def test_ssh_exec_returns_nonzero_exit_without_raising() -> None:
    # nonzero != 255 (e.g. oscap exit 2) is the remote command's exit, not transport
    with patch("ks_gen.verify.ssh.subprocess.run", return_value=_completed(2, "", "rules failed")):
        result = ssh_exec("host", "user", "oscap ...")
    assert result.exit_code == 2


def test_ssh_exec_forwards_stdin_input() -> None:
    with patch("ks_gen.verify.ssh.subprocess.run", return_value=_completed(0)) as run:
        ssh_exec("host", "user", "sudo -S -p '' true", stdin_input="pw\n")
    assert run.call_args.kwargs["input"] == "pw\n"


def test_ssh_exec_stdin_input_defaults_to_none() -> None:
    with patch("ks_gen.verify.ssh.subprocess.run", return_value=_completed(0)) as run:
        ssh_exec("host", "user", "ls /")
    assert run.call_args.kwargs["input"] is None


def test_sudo_read_passwordless_returns_raw_bytes() -> None:
    completed = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=b"\xff\xfe<TestResult/>", stderr=b""
    )
    with patch("ks_gen.verify.ssh.subprocess.run", return_value=completed) as run:
        data = sudo_read("host", "user", "/root/f.xml", auth=SudoAuth(), extra_opts=["-q"])
    assert data == b"\xff\xfe<TestResult/>"
    argv = run.call_args.args[0]
    assert argv[-1] == "sudo -n cat /root/f.xml"
    assert run.call_args.kwargs["input"] is None


def test_sudo_read_password_sends_stdin_and_uses_dash_s() -> None:
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=b"x", stderr=b"")
    with patch("ks_gen.verify.ssh.subprocess.run", return_value=completed) as run:
        sudo_read("host", "user", "/root/f.xml", auth=SudoAuth(password="pw"))
    argv = run.call_args.args[0]
    assert argv[-1] == "sudo -S -p '' cat /root/f.xml"
    assert run.call_args.kwargs["input"] == b"pw\n"


def test_sudo_read_nonzero_exit_raises() -> None:
    completed = subprocess.CompletedProcess(args=[], returncode=1, stdout=b"", stderr=b"denied")
    with (
        patch("ks_gen.verify.ssh.subprocess.run", return_value=completed),
        pytest.raises(SshConnectError, match="sudo cat"),
    ):
        sudo_read("host", "user", "/root/f.xml", auth=SudoAuth())
