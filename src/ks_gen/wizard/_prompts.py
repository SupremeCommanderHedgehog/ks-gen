"""Typed adapter over `questionary`.

This is the only file in the wizard package that imports questionary;
keeping the dependency surface here makes the import boundary explicit.
Outward-facing functions are typed strictly and used by the group helpers.
"""

from __future__ import annotations

from collections.abc import Iterable

import questionary as _questionary


def select_one(message: str, choices: Iterable[str]) -> str:
    """Single-select menu; returns the chosen string."""
    answer = _questionary.select(message, choices=list(choices)).ask()
    if answer is None:
        raise KeyboardInterrupt
    return str(answer)


def ask_text(
    message: str,
    *,
    default: str = "",
    validate: object | None = None,
) -> str:
    """Free-form text input; returns stripped value.

    `validate` accepts questionary's validator protocol — a callable
    returning True for valid input or a str error message.
    """
    answer = _questionary.text(message, default=default, validate=validate).ask()
    if answer is None:
        raise KeyboardInterrupt
    return str(answer).strip()


def ask_confirm(message: str, *, default: bool) -> bool:
    """Yes/no confirm; returns bool."""
    answer = _questionary.confirm(message, default=default).ask()
    if answer is None:
        raise KeyboardInterrupt
    return bool(answer)


def ask_password(message: str) -> str:
    """Hidden-input prompt for secrets; returns string (not stripped)."""
    answer = _questionary.password(message).ask()
    if answer is None:
        raise KeyboardInterrupt
    return str(answer)


def ask_checkbox(
    message: str,
    choices: Iterable[tuple[str, str]],
) -> list[str]:
    """Multi-select; `choices` is iterable of (key, label) pairs.

    Returns the list of selected keys (empty list is valid).
    """
    pairs = list(choices)
    q_choices = [_questionary.Choice(title=f"{key:<25}{label}", value=key) for key, label in pairs]
    answer = _questionary.checkbox(message, choices=q_choices).ask()
    if answer is None:
        raise KeyboardInterrupt
    return [str(x) for x in answer]


def loop_until_blank(message: str) -> list[str]:
    """Repeated text prompt; stops on blank input. Returns collected values."""
    collected: list[str] = []
    while True:
        value = ask_text(message, default="")
        if not value:
            return collected
        collected.append(value)
