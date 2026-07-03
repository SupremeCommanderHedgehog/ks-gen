from __future__ import annotations

import shutil
from unittest.mock import patch

import pytest

from ks_gen.loader import ConfigError
from ks_gen.verify.auth import SudoAuth
from ks_gen.verify.errors import ArfMissingError, OscapInvocationError, ToolMissingError
from ks_gen.verify.ssh import SshResult
from ks_gen.verify.transport import CmdResult, LocalTransport, SshTransport


def _t() -> SshTransport:
    return SshTransport(host="h", user="u", ssh_extra_opts=["-q"], sudo_auth=SudoAuth())


def test_ssh_transport_run_delegates_to_sudo_ssh_and_maps_result() -> None:
    with patch("ks_gen.verify.transport._sudo_ssh", return_value=SshResult("out", "err", 2)) as m:
        res = _t().run("oscap xccdf eval", timeout=600)
    assert res == CmdResult(stdout="out", stderr="err", exit_code=2)
    assert m.call_args.args[:3] == ("h", "u", "oscap xccdf eval")
    assert m.call_args.kwargs["timeout"] == 600
    assert m.call_args.kwargs["auth"] == SudoAuth()
    assert m.call_args.kwargs["ssh_extra_opts"] == ["-q"]


def test_ssh_transport_read_root_file_delegates_to_sudo_read() -> None:
    with patch("ks_gen.verify.transport.sudo_read", return_value=b"<x/>") as m:
        data = _t().read_root_file("/root/tailoring.xml")
    assert data == b"<x/>"
    assert m.call_args.args[:3] == ("h", "u", "/root/tailoring.xml")
    assert m.call_args.kwargs["auth"] == SudoAuth()
    assert m.call_args.kwargs["extra_opts"] == ["-q"]


def test_ssh_transport_preflight_delegates_to_probe_sudo() -> None:
    with patch("ks_gen.verify.transport.probe_sudo") as m:
        _t().preflight()
    assert m.call_args.args[:2] == ("h", "u")
    assert m.call_args.kwargs["sudo_auth"] == SudoAuth()
    assert m.call_args.kwargs["ssh_extra_opts"] == ["-q"]


@pytest.mark.skipif(shutil.which("echo") is None, reason="needs echo binary on PATH")
def test_local_transport_run_executes_real_subprocess() -> None:
    res = LocalTransport().run("echo hello")
    assert res.exit_code == 0
    assert res.stdout.strip() == "hello"


@pytest.mark.skipif(shutil.which("test") is None, reason="needs coreutils test on PATH")
def test_local_transport_run_nonzero_exit_is_returned_not_raised() -> None:
    res = LocalTransport().run("test -r /nonexistent/definitely/not/here")
    assert res.exit_code == 1


def test_local_transport_run_missing_binary_raises_tool_missing() -> None:
    with pytest.raises(ToolMissingError):
        LocalTransport().run("ksgen-no-such-binary-xyz --nope")


@pytest.mark.skipif(shutil.which("sleep") is None, reason="needs sleep binary on PATH")
def test_local_transport_run_timeout_raises_oscap_invocation() -> None:
    with pytest.raises(OscapInvocationError, match="timed out"):
        LocalTransport().run("sleep 5", timeout=0.01)


def test_local_transport_read_root_file_returns_bytes(tmp_path) -> None:
    f = tmp_path / "f.bin"
    f.write_bytes(b"\xff\xfe<x/>")
    assert LocalTransport().read_root_file(str(f)) == b"\xff\xfe<x/>"


def test_local_transport_read_root_file_missing_raises_arf_missing(tmp_path) -> None:
    with pytest.raises(ArfMissingError):
        LocalTransport().read_root_file(str(tmp_path / "gone.xml"))


def test_local_transport_preflight_passes_when_root_and_oscap_present() -> None:
    with (
        patch("ks_gen.verify.transport.os.geteuid", return_value=0, create=True),
        patch("ks_gen.verify.transport.shutil.which", return_value="/usr/bin/oscap"),
    ):
        LocalTransport().preflight()  # no raise


def test_local_transport_preflight_non_root_raises_config_error() -> None:
    with (
        patch("ks_gen.verify.transport.os.geteuid", return_value=1000, create=True),
        pytest.raises(ConfigError, match="root"),
    ):
        LocalTransport().preflight()


def test_local_transport_preflight_missing_oscap_raises_tool_missing() -> None:
    with (
        patch("ks_gen.verify.transport.os.geteuid", return_value=0, create=True),
        patch("ks_gen.verify.transport.shutil.which", return_value=None),
        pytest.raises(ToolMissingError, match="oscap"),
    ):
        LocalTransport().preflight()
