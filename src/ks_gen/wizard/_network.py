"""Network group prompts.

Single-interface loop with optional "add another" continuation.
Bond/bridge/VLAN deferred to hand-edit per the design spec.
"""

from __future__ import annotations

import re
from typing import Any

from ks_gen.wizard import _prompts

_DOTTED_QUAD_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")


def _is_dotted_quad(s: str) -> bool:
    return bool(_DOTTED_QUAD_RE.match(s))


def _quad_validator(value: str) -> bool | str:
    """questionary validator: True if valid, else error string."""
    if _is_dotted_quad(value):
        return True
    return "expected dotted-quad (e.g., 10.0.0.1)"


def _ask_one_interface() -> dict[str, Any]:
    device = _prompts.ask_text("Interface device:", default="link")
    bootproto = _prompts.select_one("Bootproto:", ["dhcp", "static"])
    onboot = _prompts.ask_confirm("Bring up on boot?", default=True)

    iface: dict[str, Any] = {
        "device": device,
        "bootproto": bootproto,
        "onboot": onboot,
    }

    if bootproto == "static":
        iface["ip"] = _prompts.ask_text("IPv4 address (e.g., 10.0.0.10):", validate=_quad_validator)
        iface["netmask"] = _prompts.ask_text(
            "Netmask (e.g., 255.255.255.0):", validate=_quad_validator
        )
        iface["gateway"] = _prompts.ask_text("Gateway (e.g., 10.0.0.1):", validate=_quad_validator)
        iface["nameservers"] = _prompts.loop_until_blank("Nameserver (blank to stop):")

    return iface


def prompts() -> dict[str, Any]:
    interfaces: list[dict[str, Any]] = []
    while True:
        interfaces.append(_ask_one_interface())
        if not _prompts.ask_confirm("Configure another interface?", default=False):
            break
    return {"interfaces": interfaces}
