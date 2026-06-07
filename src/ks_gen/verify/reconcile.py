from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ks_gen.verify.arf import RuleResult

Category = Literal["clean", "expected_fail", "new_fail", "regression", "incomplete"]

CLEAN_CURRENT_STATES: frozenset[str] = frozenset(
    {"pass", "fixed", "notapplicable", "notselected", "informational"}
)
INCOMPLETE_STATES: frozenset[str] = frozenset({"error", "notchecked", "unknown"})


def categorize(current: str, install: str | None, expected: bool) -> Category:
    """Single-rule reconciliation logic. See spec §7.3."""
    if current in CLEAN_CURRENT_STATES:
        return "clean"
    if current in INCOMPLETE_STATES:
        return "incomplete"
    # current is fail (or any other non-clean, non-incomplete state)
    if expected:
        return "expected_fail"
    if install is None or install in INCOMPLETE_STATES:
        return "new_fail"
    if install in CLEAN_CURRENT_STATES:
        return "regression"
    # install is fail
    return "new_fail"


@dataclass(frozen=True)
class VerifyRow:
    rule_id: str
    current: str
    install: str | None
    expected: bool
    category: Category


@dataclass(frozen=True)
class VerifyReport:
    host: str
    user: str
    timestamp_utc: str
    rows: tuple[VerifyRow, ...]
    install_baseline_available: bool

    @property
    def is_clean(self) -> bool:
        return not any(r.category in ("new_fail", "regression") for r in self.rows)


def build_report(
    *,
    current: dict[str, RuleResult],
    install: dict[str, RuleResult] | None,
    expected_failures: set[str],
    host: str,
    user: str,
    timestamp_utc: str,
) -> VerifyReport:
    rows: list[VerifyRow] = []
    for rule_id in sorted(current):
        cur_state = current[rule_id].result
        inst_state = install[rule_id].result if install and rule_id in install else None
        is_expected = rule_id in expected_failures
        rows.append(
            VerifyRow(
                rule_id=rule_id,
                current=cur_state,
                install=inst_state,
                expected=is_expected,
                category=categorize(cur_state, inst_state, is_expected),
            )
        )
    return VerifyReport(
        host=host,
        user=user,
        timestamp_utc=timestamp_utc,
        rows=tuple(rows),
        install_baseline_available=install is not None,
    )
