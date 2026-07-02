from __future__ import annotations

from dataclasses import dataclass, field


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
