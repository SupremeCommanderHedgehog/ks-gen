from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable

from ks_gen.rules._types import Rule


def load_rules() -> list[Rule]:
    import ks_gen.rules as pkg

    discovered: list[Rule] = []
    for info in pkgutil.iter_modules(pkg.__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"ks_gen.rules.{info.name}")
        rule = getattr(module, "RULE", None)
        if rule is None:
            raise RuntimeError(
                f"ks_gen.rules.{info.name} does not export a module-level RULE binding"
            )
        discovered.append(rule)
    return discovered


def rule_ids(rules: Iterable[Rule]) -> list[str]:
    return [r.id for r in rules]
