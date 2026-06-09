"""Tailoring drift detection — compare expected (re-rendered from host.yaml)
against deployed (`/root/tailoring.xml` pulled from the host).

Pure parse/compare/render functions. Re-uses `TailoringOp` from
`ks_gen.rules._types` as the comparison unit; both sides round-trip through
the same dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass

from ks_gen.rules._types import TailoringOp


@dataclass(frozen=True)
class ParsedTailoring:
    """A tailoring.xml decoded into its profile_id + ordered op list."""

    profile_id: str
    ops: list[TailoringOp]


@dataclass(frozen=True)
class OpChange:
    """A set-value op whose value differs between expected and deployed.

    `action` is always `"set_value"`. select/disable transitions can't be
    `changed` because action is part of the op identity — a select-to-disable
    flip surfaces as one `removed` + one `added`.
    """

    rule_id: str
    action: str
    expected_value: str
    deployed_value: str


@dataclass(frozen=True)
class TailoringDriftReport:
    """Drift between expected and deployed tailorings.

    Empty `added`/`removed`/`changed` lists *with matching profile_ids*
    means the check ran and found no drift. `verify.reconcile.VerifyReport`
    exposes `has_tailoring_drift` for the convenience predicate.
    """

    profile_id_expected: str
    profile_id_deployed: str
    added: list[TailoringOp]
    removed: list[TailoringOp]
    changed: list[OpChange]
