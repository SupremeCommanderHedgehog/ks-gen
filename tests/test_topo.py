from dataclasses import dataclass, field

import pytest

from ks_gen.topo import CycleError, topo_sort


@dataclass(frozen=True)
class _R:
    id: str
    depends_on: list[str] = field(default_factory=list)


def test_topo_preserves_order_when_independent():
    rules = [_R("a"), _R("b"), _R("c")]
    assert [r.id for r in topo_sort(rules)] == ["a", "b", "c"]


def test_topo_orders_dependencies():
    rules = [
        _R("c", ["a", "b"]),
        _R("b", ["a"]),
        _R("a"),
    ]
    out = [r.id for r in topo_sort(rules)]
    assert out.index("a") < out.index("b") < out.index("c")


def test_topo_detects_cycles():
    rules = [_R("a", ["b"]), _R("b", ["a"])]
    with pytest.raises(CycleError, match="cycle"):
        topo_sort(rules)


def test_topo_detects_missing_dep():
    rules = [_R("a", ["ghost"])]
    with pytest.raises(KeyError, match="ghost"):
        topo_sort(rules)
