from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

TailoringAction = Literal["disable", "select", "set_value"]


@dataclass(frozen=True)
class TailoringOp:
    rule_id: str
    action: TailoringAction
    value: str | None = None

    def __post_init__(self) -> None:
        if self.action == "set_value" and self.value is None:
            raise ValueError("set_value requires a value")


@dataclass(frozen=True)
class ExceptionEntry:
    rule_id: str
    summary: str
    stig_rules_disabled: list[str] = field(default_factory=list)
    reason: str = ""


class Rule(Protocol):
    id: str
    summary: str
    depends_on: list[str]
    stig_rules_affected: list[str]

    def applies(self, cfg: HostConfig) -> bool: ...
    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]: ...
    def emit_post(self, cfg: HostConfig) -> str: ...
    def emit_packages(self, cfg: HostConfig) -> list[str]: ...
    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None: ...
