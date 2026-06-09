"""Network group prompts.

Single-interface loop with optional "add another" continuation.
Bond/bridge/VLAN deferred to hand-edit per the design spec.
"""

from __future__ import annotations

from typing import Any

from ks_gen.wizard import _prompts


def _ask_one_interface() -> dict[str, Any]:
    device = _prompts.ask_text("Interface device:", default="link")
    bootproto = _prompts.select_one("Bootproto:", ["dhcp", "static"])
    onboot = _prompts.ask_confirm("Bring up on boot?", default=True)

    iface: dict[str, Any] = {
        "device": device,
        "bootproto": bootproto,
        "onboot": onboot,
    }
    # static fields added in Task 10
    return iface


def prompts() -> dict[str, Any]:
    interfaces: list[dict[str, Any]] = []
    while True:
        interfaces.append(_ask_one_interface())
        if not _prompts.ask_confirm("Configure another interface?", default=False):
            break
    return {"interfaces": interfaces}
