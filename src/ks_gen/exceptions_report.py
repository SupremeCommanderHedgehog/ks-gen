from __future__ import annotations

from collections.abc import Iterable

from ks_gen.config import HostConfig
from ks_gen.rules._types import Rule


def render_exceptions_md(cfg: HostConfig, rules: Iterable[Rule]) -> str:
    return "# Exceptions report\n\n(stub; expanded in Task 28)\n"
