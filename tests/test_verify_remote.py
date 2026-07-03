from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from ks_gen.verify.auth import SudoAuth
from ks_gen.verify.errors import (
    ArfMissingError,
    OscapInvocationError,
    SudoPromptError,
)
from ks_gen.verify.remote import CollectedArfs, collect_arfs, collect_deployed_tailoring
from ks_gen.verify.ssh import SshResult, probe_sudo
from ks_gen.verify.transport import SshTransport

# --- probe_sudo --------------------------------------------------------------


def test_probe_sudo_passwordless_passes_and_uses_sudo_n() -> None:
    with patch("ks_gen.verify.ssh.ssh_exec", return_value=SshResult("", "", 0)) as ssh:
        probe_sudo("h", "u", sudo_auth=SudoAuth(), ssh_extra_opts=[])
    assert ssh.call_args.args[2] == "sudo -n true"
    assert ssh.call_args.kwargs["stdin_input"] is None


def test_probe_sudo_password_uses_sudo_s_and_sends_stdin() -> None:
    with patch("ks_gen.verify.ssh.ssh_exec", return_value=SshResult("", "", 0)) as ssh:
        probe_sudo("h", "u", sudo_auth=SudoAuth(password="pw"), ssh_extra_opts=[])
    assert ssh.call_args.args[2] == "sudo -S -p '' true"
    assert ssh.call_args.kwargs["stdin_input"] == "pw\n"


def test_probe_sudo_passwordless_failure_says_passwordless() -> None:
    with (
        patch("ks_gen.verify.ssh.ssh_exec", return_value=SshResult("", "", 1)),
        pytest.raises(SudoPromptError, match="passwordless"),
    ):
        probe_sudo("h", "u", sudo_auth=SudoAuth(), ssh_extra_opts=[])


def test_probe_sudo_password_failure_says_wrong_password() -> None:
    with (
        patch("ks_gen.verify.ssh.ssh_exec", return_value=SshResult("", "", 1)),
        pytest.raises(SudoPromptError, match="wrong password or user not in sudoers"),
    ):
        probe_sudo("h", "u", sudo_auth=SudoAuth(password="pw"), ssh_extra_opts=[])


# --- collect_arfs ------------------------------------------------------------


def _build_cfg():
    from ks_gen.config import AdminUser, HostConfig, System, User

    return HostConfig(
        system=System(hostname="h"),
        user=User(admin=AdminUser(name="u", authorized_keys=["k a@b"], sudo="nopasswd_yes")),
    )


def test_collect_arfs_runs_oscap_pulls_current_and_install(tmp_path: Path) -> None:
    cfg = _build_cfg()
    transport = SshTransport(host="h", user="u", ssh_extra_opts=[], sudo_auth=SudoAuth())
    reads: list[str] = []

    def fake_ssh(host: str, user: str, cmd: str, **kw: object) -> SshResult:
        if cmd == "sudo -n true":
            return SshResult("", "", 0)
        if cmd == "sudo -n test -r /root/tailoring.xml":
            return SshResult("", "", 0)
        if "oscap xccdf eval" in cmd:
            return SshResult("", "", 2)  # rules failed = normal
        if cmd == "sudo -n test -r /root/oscap-remediation-results.xml":
            return SshResult("", "", 0)
        if cmd.startswith("sudo -n rm"):
            return SshResult("", "", 0)
        raise AssertionError(f"unexpected ssh cmd: {cmd}")

    def fake_read(host: str, user: str, remote: str, **kw: object) -> bytes:
        reads.append(remote)
        return b"<TestResult/>"

    with (
        patch("ks_gen.verify.ssh.ssh_exec", side_effect=fake_ssh),
        patch("ks_gen.verify.transport.sudo_read", side_effect=fake_read),
    ):
        result = collect_arfs(
            cfg=cfg, transport=transport, workdir=tmp_path, no_drift=False, timeout=600
        )

    assert isinstance(result, CollectedArfs)
    assert "<TestResult/>" in result.current_text
    assert result.install_text == "<TestResult/>"
    assert "/tmp/ksgen-verify-current.arf.xml" in reads
    assert "/root/oscap-remediation-results.xml" in reads


def test_collect_arfs_skips_install_baseline_when_no_drift(tmp_path: Path) -> None:
    cfg = _build_cfg()
    transport = SshTransport(host="h", user="u", ssh_extra_opts=[], sudo_auth=SudoAuth())

    def fake_ssh(host: str, user: str, cmd: str, **kw: object) -> SshResult:
        if cmd == "sudo -n true":
            return SshResult("", "", 0)
        if cmd == "sudo -n test -r /root/tailoring.xml":
            return SshResult("", "", 0)
        if "oscap xccdf eval" in cmd:
            return SshResult("", "", 0)
        if cmd.startswith("sudo -n rm"):
            return SshResult("", "", 0)
        if "oscap-remediation-results" in cmd:
            raise AssertionError("install baseline should not be probed when no_drift=True")
        return SshResult("", "", 0)

    def fake_read(host: str, user: str, remote: str, **kw: object) -> bytes:
        if "oscap-remediation-results" in remote:
            raise AssertionError("install baseline should not be read when no_drift=True")
        return b"<TestResult/>"

    with (
        patch("ks_gen.verify.ssh.ssh_exec", side_effect=fake_ssh),
        patch("ks_gen.verify.transport.sudo_read", side_effect=fake_read),
    ):
        result = collect_arfs(
            cfg=cfg, transport=transport, workdir=tmp_path, no_drift=True, timeout=600
        )
    assert result.install_text is None


def test_collect_arfs_install_baseline_missing_is_soft_fail(tmp_path: Path) -> None:
    cfg = _build_cfg()
    transport = SshTransport(host="h", user="u", ssh_extra_opts=[], sudo_auth=SudoAuth())

    def fake_ssh(host: str, user: str, cmd: str, **kw: object) -> SshResult:
        if cmd == "sudo -n true":
            return SshResult("", "", 0)
        if cmd == "sudo -n test -r /root/tailoring.xml":
            return SshResult("", "", 0)
        if "oscap xccdf eval" in cmd:
            return SshResult("", "", 0)
        if cmd == "sudo -n test -r /root/oscap-remediation-results.xml":
            return SshResult("", "", 1)
        if cmd.startswith("sudo -n rm"):
            return SshResult("", "", 0)
        return SshResult("", "", 0)

    def fake_read(host: str, user: str, remote: str, **kw: object) -> bytes:
        return b"<TestResult/>"

    with (
        patch("ks_gen.verify.ssh.ssh_exec", side_effect=fake_ssh),
        patch("ks_gen.verify.transport.sudo_read", side_effect=fake_read),
    ):
        result = collect_arfs(
            cfg=cfg, transport=transport, workdir=tmp_path, no_drift=False, timeout=600
        )
    assert result.install_text is None


def test_collect_arfs_raises_when_tailoring_missing(tmp_path: Path) -> None:
    cfg = _build_cfg()
    transport = SshTransport(host="h", user="u", ssh_extra_opts=[], sudo_auth=SudoAuth())

    def fake_ssh(host: str, user: str, cmd: str, **kw: object) -> SshResult:
        if cmd == "sudo -n true":
            return SshResult("", "", 0)
        if cmd == "sudo -n test -r /root/tailoring.xml":
            return SshResult("", "", 1)
        return SshResult("", "", 0)

    with (
        patch("ks_gen.verify.ssh.ssh_exec", side_effect=fake_ssh),
        pytest.raises(OscapInvocationError, match="tailoring"),
    ):
        collect_arfs(cfg=cfg, transport=transport, workdir=tmp_path, no_drift=False, timeout=600)


def test_collect_arfs_raises_when_oscap_exit_not_in_0_or_2(tmp_path: Path) -> None:
    cfg = _build_cfg()
    transport = SshTransport(host="h", user="u", ssh_extra_opts=[], sudo_auth=SudoAuth())

    def fake_ssh(host: str, user: str, cmd: str, **kw: object) -> SshResult:
        if cmd == "sudo -n true":
            return SshResult("", "", 0)
        if cmd == "sudo -n test -r /root/tailoring.xml":
            return SshResult("", "", 0)
        if "oscap xccdf eval" in cmd:
            return SshResult("", "scap-security-guide not installed", 127)
        if cmd.startswith("sudo -n rm"):
            return SshResult("", "", 0)
        return SshResult("", "", 0)

    with (
        patch("ks_gen.verify.ssh.ssh_exec", side_effect=fake_ssh),
        pytest.raises(OscapInvocationError, match="127"),
    ):
        collect_arfs(cfg=cfg, transport=transport, workdir=tmp_path, no_drift=False, timeout=600)


def test_collect_arfs_raises_when_current_arf_is_empty(tmp_path: Path) -> None:
    cfg = _build_cfg()
    transport = SshTransport(host="h", user="u", ssh_extra_opts=[], sudo_auth=SudoAuth())

    def fake_ssh(host: str, user: str, cmd: str, **kw: object) -> SshResult:
        if cmd == "sudo -n true":
            return SshResult("", "", 0)
        if cmd == "sudo -n test -r /root/tailoring.xml":
            return SshResult("", "", 0)
        if "oscap xccdf eval" in cmd:
            return SshResult("", "", 0)
        if cmd.startswith("sudo -n rm"):
            return SshResult("", "", 0)
        return SshResult("", "", 0)

    def fake_read(host: str, user: str, remote: str, **kw: object) -> bytes:
        return b""  # empty

    with (
        patch("ks_gen.verify.ssh.ssh_exec", side_effect=fake_ssh),
        patch("ks_gen.verify.transport.sudo_read", side_effect=fake_read),
        pytest.raises(ArfMissingError),
    ):
        collect_arfs(cfg=cfg, transport=transport, workdir=tmp_path, no_drift=False, timeout=600)


def test_collect_arfs_password_mode_sends_password_to_every_call(tmp_path: Path) -> None:
    cfg = _build_cfg()
    transport = SshTransport(
        host="h", user="u", ssh_extra_opts=[], sudo_auth=SudoAuth(password="pw")
    )
    ssh_stdins: list[object] = []
    read_auths: list[object] = []

    def fake_ssh(host: str, user: str, cmd: str, **kw: object) -> SshResult:
        ssh_stdins.append(kw.get("stdin_input"))
        if "oscap xccdf eval" in cmd:
            return SshResult("", "", 0)
        return SshResult("", "", 0)  # true, test -r, rm all succeed

    def fake_read(host: str, user: str, remote: str, **kw: object) -> bytes:
        read_auths.append(kw["auth"])
        return b"<TestResult/>"

    with (
        patch("ks_gen.verify.ssh.ssh_exec", side_effect=fake_ssh),
        patch("ks_gen.verify.transport.sudo_read", side_effect=fake_read),
    ):
        collect_arfs(cfg=cfg, transport=transport, workdir=tmp_path, no_drift=True, timeout=600)

    assert ssh_stdins  # sanity: calls happened
    assert all(s == "pw\n" for s in ssh_stdins)
    assert read_auths  # sanity: read happened
    assert all(a.password == "pw" for a in read_auths)


# --- collect_deployed_tailoring ----------------------------------------------


def test_collect_deployed_tailoring_pulls_and_returns_text(tmp_path: Path) -> None:
    transport = SshTransport(host="h", user="u", ssh_extra_opts=[], sudo_auth=SudoAuth())
    pulled: dict[str, object] = {}

    def fake_ssh(host: str, user: str, cmd: str, **kw: object) -> SshResult:
        if cmd == "sudo -n true":
            return SshResult("", "", 0)
        if cmd == "sudo -n test -r /root/tailoring.xml":
            return SshResult("", "", 0)
        raise AssertionError(f"unexpected ssh cmd: {cmd}")

    def fake_read(host: str, user: str, remote: str, **kw: object) -> bytes:
        pulled["remote"] = remote
        return b"<xccdf:Tailoring/>"

    with (
        patch("ks_gen.verify.ssh.ssh_exec", side_effect=fake_ssh),
        patch("ks_gen.verify.transport.sudo_read", side_effect=fake_read),
    ):
        text = collect_deployed_tailoring(transport=transport, workdir=tmp_path)

    assert pulled["remote"] == "/root/tailoring.xml"
    assert text == "<xccdf:Tailoring/>"


def test_collect_deployed_tailoring_raises_when_file_missing(tmp_path: Path) -> None:
    transport = SshTransport(host="h", user="u", ssh_extra_opts=[], sudo_auth=SudoAuth())

    def fake_ssh(host: str, user: str, cmd: str, **kw: object) -> SshResult:
        if cmd == "sudo -n true":
            return SshResult("", "", 0)
        if cmd == "sudo -n test -r /root/tailoring.xml":
            return SshResult("", "", 1)
        raise AssertionError(f"unexpected ssh cmd: {cmd}")

    with (
        patch("ks_gen.verify.ssh.ssh_exec", side_effect=fake_ssh),
        pytest.raises(OscapInvocationError, match="install-time tailoring"),
    ):
        collect_deployed_tailoring(transport=transport, workdir=tmp_path)


def test_collect_deployed_tailoring_raises_when_pulled_file_empty(tmp_path: Path) -> None:
    transport = SshTransport(host="h", user="u", ssh_extra_opts=[], sudo_auth=SudoAuth())

    def fake_ssh(host: str, user: str, cmd: str, **kw: object) -> SshResult:
        if cmd == "sudo -n true":
            return SshResult("", "", 0)
        if cmd == "sudo -n test -r /root/tailoring.xml":
            return SshResult("", "", 0)
        raise AssertionError(f"unexpected ssh cmd: {cmd}")

    def fake_read(host: str, user: str, remote: str, **kw: object) -> bytes:
        return b""

    with (
        patch("ks_gen.verify.ssh.ssh_exec", side_effect=fake_ssh),
        patch("ks_gen.verify.transport.sudo_read", side_effect=fake_read),
        pytest.raises(ArfMissingError, match="empty"),
    ):
        collect_deployed_tailoring(transport=transport, workdir=tmp_path)
