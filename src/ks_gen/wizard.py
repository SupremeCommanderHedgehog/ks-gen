from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ks_gen.config import HostConfig


@dataclass
class WizardError(Exception):
    message: str


def _ask(prompt: str, default: str | None, *, interactive: bool) -> str:
    if not interactive:
        if default is None:
            raise WizardError(f"missing required value: {prompt}")
        return default
    suffix = f" [{default}]" if default is not None else ""
    sys.stdout.write(f"{prompt}{suffix}: ")
    sys.stdout.flush()
    line = sys.stdin.readline()
    if line == "":
        raise WizardError("unexpected EOF on stdin")
    answer = line.rstrip("\n")
    if not answer and default is not None:
        return default
    if not answer and default is None:
        raise WizardError(f"missing required value: {prompt}")
    return answer


def _ask_keys(interactive: bool) -> list[str]:
    keys: list[str] = []
    while True:
        line = _ask(
            "SSH public key (blank to stop)" if keys else "SSH public key",
            "" if keys else None,
            interactive=interactive,
        )
        if not line:
            if not keys:
                raise WizardError("at least one SSH key is required")
            return keys
        keys.append(line)


def run_wizard(*, interactive: bool) -> tuple[HostConfig, str]:
    hostname = _ask("Hostname", None, interactive=interactive)
    timezone = _ask("Timezone", "UTC", interactive=interactive)
    locale = _ask("Locale", "en_US.UTF-8", interactive=interactive)
    admin_name = _ask("Admin username", "opsadmin", interactive=interactive)
    sudo = _ask(
        "Admin sudo mode (nopasswd_no/nopasswd_yes)", "nopasswd_yes", interactive=interactive
    )
    keys = _ask_keys(interactive)
    ssh_port_raw = _ask("SSH port", "22", interactive=interactive)
    crypto_policy = _ask("Crypto policy (STIG/MODERN/FUTURE)", "MODERN", interactive=interactive)

    payload: dict[str, Any] = {
        "system": {"hostname": hostname, "timezone": timezone, "locale": locale},
        "user": {
            "admin": {
                "name": admin_name,
                "authorized_keys": keys,
                "sudo": sudo,
            }
        },
        "ssh": {"port": int(ssh_port_raw)},
        "crypto": {"policy": crypto_policy},
    }
    cfg = HostConfig.model_validate(payload)
    yaml_text = yaml.safe_dump(
        cfg.model_dump(mode="json"), sort_keys=False, default_flow_style=False
    )
    return cfg, yaml_text


def write_initial(out_root: Path, cfg: HostConfig, yaml_text: str) -> Path:
    host_dir = out_root / cfg.system.hostname
    host_dir.mkdir(parents=True, exist_ok=True)
    (host_dir / "host.yaml").write_text(yaml_text, encoding="utf-8", newline="\n")
    return host_dir
