from __future__ import annotations

from enum import IntEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ks_gen.config import HostConfig


class ExitCode(IntEnum):
    OK = 0
    USAGE = 1
    CONFIG_INVALID = 2
    RULE_CONFLICT = 3
    LINT_FAIL = 4
    TOOL_MISSING = 5
    VERIFY_FAIL = 6
    TRANSPORT_FAIL = 7


class ConfigError(Exception):
    def __init__(self, message: str, exit_code: ExitCode):
        super().__init__(message)
        self.exit_code = exit_code


def _parse_scalar(raw: str) -> Any:
    """Best-effort YAML-style scalar coercion for --set RHS."""
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    if raw.lower() in ("null", "none", "~"):
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        return raw[1:-1]
    return raw


def _apply_set(data: dict[str, Any], expr: str) -> None:
    if "=" not in expr:
        raise ConfigError(f"--set expression must be KEY=VALUE: got {expr!r}", ExitCode.USAGE)
    key, _, raw = expr.partition("=")
    path = [p for p in key.split(".") if p]
    if not path:
        raise ConfigError(f"--set key is empty: {expr!r}", ExitCode.USAGE)
    cursor = data
    for segment in path[:-1]:
        if segment not in cursor or not isinstance(cursor[segment], dict):
            cursor[segment] = {}
        cursor = cursor[segment]
    cursor[path[-1]] = _parse_scalar(raw)


def load_host_config(path: Path, sets: list[str]) -> HostConfig:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"cannot read {path}: {e}", ExitCode.USAGE) from e
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"YAML parse error: {e}", ExitCode.CONFIG_INVALID) from e
    if not isinstance(data, dict):
        raise ConfigError("host.yaml top level must be a mapping", ExitCode.CONFIG_INVALID)
    for s in sets:
        _apply_set(data, s)
    try:
        return HostConfig.model_validate(data)
    except ValidationError as e:
        msg = str(e)
        code = (
            ExitCode.RULE_CONFLICT
            if ("MODERN" in msg and "fips_mode" in msg)
            else ExitCode.CONFIG_INVALID
        )
        raise ConfigError(msg, code) from e
