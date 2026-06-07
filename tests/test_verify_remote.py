from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from ks_gen.verify.errors import (
    ArfMissingError,
    OscapInvocationError,
    SudoPromptError,
)
from ks_gen.verify.remote import CollectedArfs, collect_arfs, probe_sudo
from ks_gen.verify.ssh import SshResult

# --- probe_sudo --------------------------------------------------------------


def test_probe_sudo_passes_when_sudo_n_true_succeeds() -> None:
    with patch("ks_gen.verify.remote.ssh_exec", return_value=SshResult("", "", 0)) as ssh:
        probe_sudo("h", "u", ssh_extra_opts=[])
    assert ssh.call_args.args[2] == "sudo -n true"


def test_probe_sudo_raises_on_nonzero_sudo_n_true() -> None:
    with (
        patch(
            "ks_gen.verify.remote.ssh_exec",
            return_value=SshResult("", "sudo: a password is required", 1),
        ),
        pytest.raises(SudoPromptError, match="passwordless"),
    ):
        probe_sudo("h", "u", ssh_extra_opts=[])


# --- collect_arfs ------------------------------------------------------------


def _build_cfg():
    from ks_gen.config import AdminUser, HostConfig, System, User

    return HostConfig(
        system=System(hostname="h"),
        user=User(admin=AdminUser(name="u", authorized_keys=["k a@b"], sudo="nopasswd_yes")),
    )


def test_collect_arfs_runs_oscap_pulls_current_and_install(tmp_path: Path) -> None:
    cfg = _build_cfg()
    call_log: list[tuple[str, ...]] = []

    def fake_ssh(host: str, user: str, cmd: str, **kw: object) -> SshResult:
        call_log.append(("ssh", cmd))
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

    def fake_scp(host: str, user: str, remote: str, local: Path, **kw: object) -> None:
        call_log.append(("scp", remote))
        local.write_text("<TestResult/>", encoding="utf-8")

    with (
        patch("ks_gen.verify.remote.ssh_exec", side_effect=fake_ssh),
        patch("ks_gen.verify.remote.scp_pull", side_effect=fake_scp),
    ):
        result = collect_arfs(
            cfg=cfg,
            host="h",
            user="u",
            workdir=tmp_path,
            no_drift=False,
            ssh_extra_opts=[],
            timeout=600,
        )

    assert isinstance(result, CollectedArfs)
    assert "<TestResult/>" in result.current_text
    assert result.install_text == "<TestResult/>"
    assert ("scp", "/tmp/ksgen-verify-current.arf.xml") in call_log
    assert ("scp", "/root/oscap-remediation-results.xml") in call_log


def test_collect_arfs_skips_install_baseline_when_no_drift(tmp_path: Path) -> None:
    cfg = _build_cfg()

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

    def fake_scp(host: str, user: str, remote: str, local: Path, **kw: object) -> None:
        if "oscap-remediation-results" in remote:
            raise AssertionError("install baseline should not be scp'd when no_drift=True")
        local.write_text("<TestResult/>", encoding="utf-8")

    with (
        patch("ks_gen.verify.remote.ssh_exec", side_effect=fake_ssh),
        patch("ks_gen.verify.remote.scp_pull", side_effect=fake_scp),
    ):
        result = collect_arfs(
            cfg=cfg,
            host="h",
            user="u",
            workdir=tmp_path,
            no_drift=True,
            ssh_extra_opts=[],
            timeout=600,
        )
    assert result.install_text is None


def test_collect_arfs_install_baseline_missing_is_soft_fail(tmp_path: Path) -> None:
    cfg = _build_cfg()

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

    def fake_scp(host: str, user: str, remote: str, local: Path, **kw: object) -> None:
        local.write_text("<TestResult/>", encoding="utf-8")

    with (
        patch("ks_gen.verify.remote.ssh_exec", side_effect=fake_ssh),
        patch("ks_gen.verify.remote.scp_pull", side_effect=fake_scp),
    ):
        result = collect_arfs(
            cfg=cfg,
            host="h",
            user="u",
            workdir=tmp_path,
            no_drift=False,
            ssh_extra_opts=[],
            timeout=600,
        )
    assert result.install_text is None


def test_collect_arfs_raises_when_tailoring_missing(tmp_path: Path) -> None:
    cfg = _build_cfg()

    def fake_ssh(host: str, user: str, cmd: str, **kw: object) -> SshResult:
        if cmd == "sudo -n true":
            return SshResult("", "", 0)
        if cmd == "sudo -n test -r /root/tailoring.xml":
            return SshResult("", "", 1)
        return SshResult("", "", 0)

    with (
        patch("ks_gen.verify.remote.ssh_exec", side_effect=fake_ssh),
        patch("ks_gen.verify.remote.scp_pull"),
        pytest.raises(OscapInvocationError, match="tailoring"),
    ):
        collect_arfs(
            cfg=cfg,
            host="h",
            user="u",
            workdir=tmp_path,
            no_drift=False,
            ssh_extra_opts=[],
            timeout=600,
        )


def test_collect_arfs_raises_when_oscap_exit_not_in_0_or_2(tmp_path: Path) -> None:
    cfg = _build_cfg()

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
        patch("ks_gen.verify.remote.ssh_exec", side_effect=fake_ssh),
        patch("ks_gen.verify.remote.scp_pull"),
        pytest.raises(OscapInvocationError, match="127"),
    ):
        collect_arfs(
            cfg=cfg,
            host="h",
            user="u",
            workdir=tmp_path,
            no_drift=False,
            ssh_extra_opts=[],
            timeout=600,
        )


def test_collect_arfs_raises_when_current_arf_is_empty(tmp_path: Path) -> None:
    cfg = _build_cfg()

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

    def fake_scp(host: str, user: str, remote: str, local: Path, **kw: object) -> None:
        local.write_text("", encoding="utf-8")  # empty

    with (
        patch("ks_gen.verify.remote.ssh_exec", side_effect=fake_ssh),
        patch("ks_gen.verify.remote.scp_pull", side_effect=fake_scp),
        pytest.raises(ArfMissingError),
    ):
        collect_arfs(
            cfg=cfg,
            host="h",
            user="u",
            workdir=tmp_path,
            no_drift=False,
            ssh_extra_opts=[],
            timeout=600,
        )
