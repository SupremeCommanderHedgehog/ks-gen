from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, TypeVar


class _HasIdAndDeps(Protocol):
    id: str
    depends_on: list[str]


T = TypeVar("T", bound=_HasIdAndDeps)


class CycleError(Exception):
    pass


def topo_sort(rules: Iterable[T]) -> list[T]:
    by_id: dict[str, T] = {r.id: r for r in rules}
    visited: dict[str, str] = {}  # id -> "in" | "done"
    order: list[T] = []

    def visit(node_id: str) -> None:
        state = visited.get(node_id)
        if state == "done":
            return
        if state == "in":
            raise CycleError(f"cycle detected at rule {node_id!r}")
        if node_id not in by_id:
            raise KeyError(f"unknown dependency rule id: {node_id!r}")
        visited[node_id] = "in"
        for dep in by_id[node_id].depends_on:
            visit(dep)
        visited[node_id] = "done"
        order.append(by_id[node_id])

    for r in by_id.values():
        visit(r.id)
    return order
