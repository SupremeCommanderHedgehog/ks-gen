from __future__ import annotations

from ks_gen.verify.auth import SudoAuth, sudo_prefix


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
