"""Override matrix prompts.

Two checkbox prompts driven by a small static mapping. The mapping is
the cost of the schema asymmetry: not every Cfg block on Overrides has
a uniform `.enable: bool` field.
"""

from __future__ import annotations

from typing import Any

from ks_gen.wizard import _prompts

# cfg-field-name -> (toggle-attr, default-value, one-line operator label)
_OVERRIDE_TOGGLES: dict[str, tuple[str, bool, str]] = {
    "faillock": ("enable", True, "account lockout policy"),
    "kernel_module_blacklist": ("enable", True, "blacklist USB-storage, cramfs, etc."),
    "package_purge": ("enable", True, "remove telnet-server, rsh-server, etc."),
    "unattended_updates": ("enable", True, "nightly + monthly + reboot timers"),
    "usbguard": ("enable", False, "USB device control daemon"),
    "dod_root_ca": ("install", False, "install DoD root CA bundle"),
}


def prompts() -> dict[str, Any]:
    """Run the override-matrix prompts. Returns a HostConfig.overrides fragment.

    Empty selections on both checkboxes return {}, omitting the overrides
    key from the final payload so schema defaults stay in effect.
    """
    on_choices = [
        (key, label)
        for key, (_attr, default, label) in _OVERRIDE_TOGGLES.items()
        if default is True
    ]
    off_choices = [
        (key, label)
        for key, (_attr, default, label) in _OVERRIDE_TOGGLES.items()
        if default is False
    ]

    to_disable: list[str] = _prompts.ask_checkbox("Default-on rules to DISABLE:", on_choices)
    to_enable: list[str] = _prompts.ask_checkbox("Default-off rules to ENABLE:", off_choices)

    payload: dict[str, Any] = {}
    for key in to_disable:
        attr, default, _label = _OVERRIDE_TOGGLES[key]
        # default=True -> set False to disable
        payload[key] = {attr: not default}
    for key in to_enable:
        attr, default, _label = _OVERRIDE_TOGGLES[key]
        # default=False -> set True to enable
        payload[key] = {attr: not default}
    return payload
