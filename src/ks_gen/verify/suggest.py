"""Suggest ExceptionDecl entries for verify failures.

Pure-function building blocks plus the (file-touching) apply path.
The apply path is the only file mutation surface — see `apply_to_host_yaml`
for the validate-before-write invariant.
"""

from __future__ import annotations

from dataclasses import dataclass

from ks_gen.config import ExceptionDecl
from ks_gen.verify.reconcile import Category, VerifyReport


@dataclass(frozen=True)
class Suggestion:
    decl: ExceptionDecl
    category: Category  # "new_fail" or "regression"


_SUGGESTABLE: frozenset[Category] = frozenset({"new_fail", "regression"})


def _reason_for(
    row_host: str,
    row_date: str,
    row_current: str,
    row_install: str | None,
    category: Category,
) -> str:
    install = row_install if row_install is not None else "-"
    return (
        f"TODO: explain why — auto-suggested {row_date} from {row_host} "
        f"(current={row_current}, install={install}, category={category})"
    )


def build_suggestions(report: VerifyReport) -> list[Suggestion]:
    """Filter the report to rows worth suggesting an exception for.

    Includes `new_fail` and `regression` only. Order matches `report.rows`
    (which is sorted by rule_id at build time).
    """
    date = report.timestamp_utc.split("T", 1)[0]
    suggestions: list[Suggestion] = []
    for row in report.rows:
        if row.category not in _SUGGESTABLE:
            continue
        decl = ExceptionDecl(
            id=f"auto-{row.category}-{row.rule_id}",
            reason=_reason_for(report.host, date, row.current, row.install, row.category),
            stig_rules_disabled=[row.rule_id],
        )
        suggestions.append(Suggestion(decl=decl, category=row.category))
    return suggestions
