from __future__ import annotations

import pytest

from ks_gen.loader import ConfigError, ExitCode
from ks_gen.verify.auth import SudoAuth, resolve_sudo_auth, sudo_command, sudo_prefix, sudo_stdin


def test_sudo_auth_passwordless_by_default() -> None:
    auth = SudoAuth()
    assert auth.password is None
    assert auth.is_password is False


def test_sudo_auth_with_password_is_password() -> None:
    auth = SudoAuth(password="hunter2")
    assert auth.is_password is True


def test_sudo_auth_repr_hides_password() -> None:
    assert "hunter2" not in repr(SudoAuth(password="hunter2"))


def test_sudo_prefix_passwordless() -> None:
    assert sudo_prefix(SudoAuth()) == "sudo -n"


def test_sudo_prefix_password() -> None:
    assert sudo_prefix(SudoAuth(password="x")) == "sudo -S -p ''"


def test_sudo_stdin_passwordless_is_none() -> None:
    assert sudo_stdin(SudoAuth()) is None


def test_sudo_stdin_password_has_trailing_newline() -> None:
    assert sudo_stdin(SudoAuth(password="pw")) == "pw\n"


def test_sudo_command_passwordless() -> None:
    cmd, stdin = sudo_command(SudoAuth(), "true")
    assert cmd == "sudo -n true"
    assert stdin is None


def test_sudo_command_password() -> None:
    cmd, stdin = sudo_command(SudoAuth(password="pw"), "cat /x")
    assert cmd == "sudo -S -p '' cat /x"
    assert stdin == "pw\n"


def test_resolve_not_ask_returns_passwordless(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KSGEN_SUDO_PASSWORD", "ignored")
    auth = resolve_sudo_auth(False, user="u", host="h")
    assert auth.password is None


def test_resolve_ask_reads_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KSGEN_SUDO_PASSWORD", "fromenv")
    auth = resolve_sudo_auth(True, user="u", host="h")
    assert auth.password == "fromenv"


def test_resolve_ask_prompts_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KSGEN_SUDO_PASSWORD", raising=False)
    monkeypatch.setattr("ks_gen.verify.auth.sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("ks_gen.verify.auth.getpass.getpass", lambda prompt: "typed")
    auth = resolve_sudo_auth(True, user="u", host="h")
    assert auth.password == "typed"


def test_resolve_ask_no_tty_no_env_raises_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KSGEN_SUDO_PASSWORD", raising=False)
    monkeypatch.setattr("ks_gen.verify.auth.sys.stdin.isatty", lambda: False)
    with pytest.raises(ConfigError) as ei:
        resolve_sudo_auth(True, user="u", host="h")
    assert ei.value.exit_code == ExitCode.USAGE


def test_resolve_ask_empty_password_raises_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KSGEN_SUDO_PASSWORD", "")
    with pytest.raises(ConfigError) as ei:
        resolve_sudo_auth(True, user="u", host="h")
    assert ei.value.exit_code == ExitCode.USAGE
