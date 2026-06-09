from __future__ import annotations

import yaml

from ks_gen.config import HostConfig
from ks_gen.wizard import _core, _prompts
from ks_gen.wizard._core import WizardError as WizardError
from ks_gen.wizard._core import write_initial as write_initial

__all__ = ["WizardError", "run_wizard", "write_initial"]

_GROUP_CHOICES: list[tuple[str, str]] = [
    ("disk", "Disk layout (preset, LUKS)"),
    ("network", "Network (interfaces)"),
    ("overrides", "Override matrix (per-rule toggles)"),
]


def _ask_groups() -> set[str]:
    """Interactive checkbox: which optional groups to configure."""
    return set(_prompts.ask_checkbox("Configure which optional sections?", _GROUP_CHOICES))


def run_wizard(*, interactive: bool) -> tuple[HostConfig, str]:
    payload = _core.prompts(interactive)
    _selected: set[str] = _ask_groups() if interactive else set()
    # Optional groups wired in later tasks; for now the selector is a no-op.
    # if "disk" in _selected: payload["disk"] = _disk.prompts()
    # if "network" in _selected: payload["network"] = _network.prompts()
    # if "overrides" in _selected: payload["overrides"] = _overrides.prompts()
    cfg = HostConfig.model_validate(payload)
    yaml_text = yaml.safe_dump(
        cfg.model_dump(mode="json"), sort_keys=False, default_flow_style=False
    )
    return cfg, yaml_text
