"""Suggest ExceptionDecl entries for verify failures.

Pure-function building blocks plus the (file-touching) apply path.
The apply path is the only file mutation surface — see `apply_to_host_yaml`
for the validate-before-write invariant.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

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


def render_yaml(suggestions: list[Suggestion], report: VerifyReport) -> str:
    """Paste-friendly YAML block. Empty string when suggestions=[].

    Uses yaml.safe_dump with sort_keys=False so the per-decl field order
    matches the schema (id -> reason -> stig_rules_disabled).
    """
    if not suggestions:
        return ""
    n = len(suggestions)
    plural = "suggestion" if n == 1 else "suggestions"
    header = (
        "## Suggested exception entries — copy into host.yaml's `exceptions:` list\n"
        f"## verify host={report.host} user={report.user} "
        f"at={report.timestamp_utc} ({n} {plural})\n"
        "\n"
    )
    body_parts: list[str] = []
    for suggestion in suggestions:
        block = yaml.safe_dump(
            [suggestion.decl.model_dump()],
            sort_keys=False,
            default_flow_style=False,
        )
        body_parts.append(block)
    return header + "\n".join(body_parts)


@dataclass(frozen=True)
class AppendResult:
    added: tuple[str, ...]  # decl ids written this call
    skipped_existing: tuple[str, ...]  # decl ids already present in host.yaml
    skipped_regression: tuple[str, ...]  # regression decl ids gated out
    path: Path  # the host.yaml that was written
    backup_path: Path  # host.yaml.bak


def apply_to_host_yaml(
    *,
    suggestions: list[Suggestion],
    host_yaml_path: Path,
    allow_regression: bool,
) -> AppendResult:
    """Idempotent append-only write to host.yaml's exceptions list.

    Writes <path>.bak before modifying. Round-trips the candidate through
    `HostConfig.model_validate` and only writes if validation passes.
    Raises `SuggestApplyError` on read/parse/validate/IO failure with
    host.yaml byte-identical to its pre-call state.
    """
    # Local import to avoid circular: verify/__init__.py imports suggest,
    # config doesn't depend on verify but pulling it in at module load
    # adds startup cost to verify/__init__.
    from ks_gen.config import HostConfig
    from ks_gen.verify.errors import SuggestApplyError

    # Step 1: filter by allow_regression
    to_consider: list[Suggestion] = []
    skipped_regression: list[str] = []
    for suggestion in suggestions:
        if suggestion.category == "regression" and not allow_regression:
            skipped_regression.append(suggestion.decl.id)
        else:
            to_consider.append(suggestion)

    # Step 2: read & parse
    try:
        raw = host_yaml_path.read_text(encoding="utf-8")
    except OSError as e:
        raise SuggestApplyError(f"cannot read {host_yaml_path}: {e}") from e
    try:
        data: Any = yaml.safe_load(raw) or {}
    except yaml.YAMLError as e:
        raise SuggestApplyError(f"host.yaml is not valid YAML: {e}; refusing to modify.") from e
    if not isinstance(data, dict):
        raise SuggestApplyError(
            f"host.yaml is not a YAML mapping (got {type(data).__name__}); refusing to modify."
        )

    # Step 3: compute existing ids
    raw_exceptions = data.get("exceptions") or []
    existing_ids = {
        entry["id"] for entry in raw_exceptions if isinstance(entry, dict) and "id" in entry
    }

    # Step 4: filter idempotent
    to_apply: list[Suggestion] = []
    skipped_existing: list[str] = []
    for suggestion in to_consider:
        if suggestion.decl.id in existing_ids:
            skipped_existing.append(suggestion.decl.id)
        else:
            to_apply.append(suggestion)

    backup_path = host_yaml_path.with_suffix(host_yaml_path.suffix + ".bak")

    if not to_apply:
        # Idempotent no-op: skip all I/O including backup.
        return AppendResult(
            added=(),
            skipped_existing=tuple(skipped_existing),
            skipped_regression=tuple(skipped_regression),
            path=host_yaml_path,
            backup_path=backup_path,
        )

    # Step 5: build candidate
    candidate = dict(data)
    candidate["exceptions"] = list(raw_exceptions) + [s.decl.model_dump() for s in to_apply]

    # Step 6: validate via pydantic — refuse to write a candidate that
    # wouldn't load. Order: validate -> backup -> write.
    try:
        HostConfig.model_validate(candidate)
    except Exception as e:
        raise SuggestApplyError(
            f"applied host.yaml would fail validation: {e}; original untouched."
        ) from e

    # Step 7: backup (after validation passes)
    try:
        shutil.copy2(host_yaml_path, backup_path)
    except OSError as e:
        raise SuggestApplyError(
            f"cannot write backup {backup_path}: {e}; original untouched."
        ) from e

    # Step 8: atomic write
    tmp = host_yaml_path.with_suffix(host_yaml_path.suffix + ".tmp")
    try:
        tmp.write_text(
            yaml.safe_dump(candidate, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
            newline="\n",
        )
        tmp.replace(host_yaml_path)
    except OSError as e:
        raise SuggestApplyError(f"cannot write {host_yaml_path}: {e}") from e

    return AppendResult(
        added=tuple(s.decl.id for s in to_apply),
        skipped_existing=tuple(skipped_existing),
        skipped_regression=tuple(skipped_regression),
        path=host_yaml_path,
        backup_path=backup_path,
    )
