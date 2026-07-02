from __future__ import annotations

import getpass
import os
from dataclasses import dataclass, field

from ks_gen.loader import ConfigError, ExitCode


@dataclass(frozen=True)
class SudoAuth:
    """Sudo credential for verify's remote commands.

    `password is None` selects passwordless mode (`sudo -n`); a string selects
    password mode (`sudo -S`, fed over stdin). `repr=False` on the field keeps
    the secret out of tracebacks and log lines.
    """

    password: str | None = field(default=None, repr=False)

    @property
    def is_password(self) -> bool:
        return self.password is not None


def sudo_prefix(auth: SudoAuth) -> str:
    """Return the sudo invocation prefix for `auth`'s mode."""
    return "sudo -S -p ''" if auth.is_password else "sudo -n"


def sudo_stdin(auth: SudoAuth) -> str | None:
    """Return the stdin payload for a `sudo -S` invocation, or None for -n mode."""
    return f"{auth.password}\n" if auth.is_password else None


_ENV_VAR = "KSGEN_SUDO_PASSWORD"


def resolve_sudo_auth(ask: bool, *, user: str, host: str) -> SudoAuth:
    """Resolve the sudo credential for a verify run.

    `ask=False` (the default CLI path) returns a passwordless `SudoAuth`.
    `ask=True` reads `KSGEN_SUDO_PASSWORD`, falling back to a no-echo prompt.
    An empty resolved password is a usage error, never a silent fallback to
    passwordless mode.
    """
    if not ask:
        return SudoAuth()
    password = os.environ.get(_ENV_VAR)
    if password is None:
        password = getpass.getpass(f"sudo password for {user}@{host}: ")
    if not password:
        raise ConfigError(
            f"--ask-sudo-pass given but no password supplied (set {_ENV_VAR} "
            "or enter one at the prompt)",
            ExitCode.USAGE,
        )
    return SudoAuth(password=password)
