from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable

from ks_gen.rules._types import Rule


def load_rules(distro: str) -> list[Rule]:
    """Discover rule modules under ks_gen.rules.<distro>.

    Each module is expected to export a module-level `RULE: Rule` binding.
    Modules whose name starts with `_` are skipped (reserved for shared
    helpers like `_types`, `_meta`).
    """
    pkg_name = f"ks_gen.rules.{distro}"
    try:
        pkg = importlib.import_module(pkg_name)
    except ModuleNotFoundError:
        return []

    discovered: list[Rule] = []
    for info in pkgutil.iter_modules(pkg.__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{pkg_name}.{info.name}")
        rule = getattr(module, "RULE", None)
        if rule is None:
            raise RuntimeError(
                f"{pkg_name}.{info.name} does not export a module-level RULE binding"
            )
        discovered.append(rule)
    return discovered


def rule_ids(rules: Iterable[Rule]) -> list[str]:
    return [r.id for r in rules]
