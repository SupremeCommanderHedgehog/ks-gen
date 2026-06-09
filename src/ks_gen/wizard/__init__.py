from __future__ import annotations

import yaml

from ks_gen.config import HostConfig
from ks_gen.wizard import _core, _disk, _network, _overrides, _prompts
from ks_gen.wizard._core import WizardError as WizardError
from ks_gen.wizard._core import write_initial as write_initial

__all__ = ["WizardError", "run_wizard", "write_initial"]

_GROUP_CHOICES: list[tuple[str, str]] = [
    ("disk", "Disk layout (preset, LUKS)"),
    ("network", "Network (interfaces)"),
    ("overrides", "Override matrix (per-rule toggles)"),
]


def _ask_groups() -> set[str]:
    return set(_prompts.ask_checkbox("Configure which optional sections?", _GROUP_CHOICES))


def run_wizard(*, interactive: bool) -> tuple[HostConfig, str]:
    payload = _core.prompts(interactive)
    selected: set[str] = _ask_groups() if interactive else set()
    if "disk" in selected:
        payload["disk"] = _disk.prompts()
    if "network" in selected:
        payload["network"] = _network.prompts()
    if "overrides" in selected:
        overrides_fragment = _overrides.prompts()
        if overrides_fragment:  # omit empty dict so schema defaults apply
            payload["overrides"] = overrides_fragment
    cfg = HostConfig.model_validate(payload)
    yaml_text = yaml.safe_dump(
        cfg.model_dump(mode="json"), sort_keys=False, default_flow_style=False
    )
    return cfg, yaml_text
