"""Tailoring drift detection — compare expected (re-rendered from host.yaml)
against deployed (`/root/tailoring.xml` pulled from the host).

Pure parse/compare/render functions. Re-uses `TailoringOp` from
`ks_gen.rules._types` as the comparison unit; both sides round-trip through
the same dataclass.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

from ks_gen.rules._types import TailoringOp
from ks_gen.verify.errors import TailoringParseError


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


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_tailoring_xml(text: str) -> ParsedTailoring:
    """Parse a tailoring.xml into profile_id + ordered TailoringOp list.

    Uses stdlib xml.etree.ElementTree with local-name matching (same pattern
    as `verify/arf.py`). Recognized op elements:

    - `<xccdf:select idref="..." selected="true"/>`  → action="select"
    - `<xccdf:select idref="..." selected="false"/>` → action="disable"
    - `<xccdf:set-value idref="...">VALUE</xccdf:set-value>` → action="set_value"

    The profile_id returned is the ``extends`` attribute of the ``<Profile>``
    element (the base profile being tailored). Falls back to the ``id``
    attribute when ``extends`` is absent (e.g. in bare fixture XML).

    Unknown child elements inside ``<Profile>`` are dropped, not raised —
    keeps the parser forward-compatible against new XCCDF op kinds.

    Raises:
        TailoringParseError: malformed XML or no ``<Profile>`` element.
    """
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise TailoringParseError(f"tailoring XML is not well-formed: {e}") from e

    profile = None
    for elem in root.iter():
        if _localname(elem.tag) == "Profile":
            profile = elem
            break
    if profile is None:
        raise TailoringParseError("tailoring XML has no <Profile> element")

    profile_id = profile.get("extends") or profile.get("id") or ""
    ops: list[TailoringOp] = []
    for child in profile:
        local = _localname(child.tag)
        if local == "select":
            rule_id = child.get("idref") or ""
            if not rule_id:
                continue
            selected = (child.get("selected") or "").lower()
            if selected == "true":
                ops.append(TailoringOp(rule_id=rule_id, action="select"))
            elif selected == "false":
                ops.append(TailoringOp(rule_id=rule_id, action="disable"))
        elif local == "set-value":
            rule_id = child.get("idref") or ""
            if not rule_id:
                continue
            value = child.text or ""
            ops.append(TailoringOp(rule_id=rule_id, action="set_value", value=value))

    return ParsedTailoring(profile_id=profile_id, ops=ops)


def compare_tailorings(
    expected: ParsedTailoring,
    deployed: ParsedTailoring,
) -> TailoringDriftReport:
    """Pure diff between two parsed tailorings.

    Ops are keyed by `(action, rule_id)`. Same key on both sides with a
    different value → `OpChange` (only set_value carries a meaningful value).
    Key in expected only → `added`. Key in deployed only → `removed`.

    Returned lists are sorted by rule_id for stable rendering.
    """
    expected_map = {(op.action, op.rule_id): op for op in expected.ops}
    deployed_map = {(op.action, op.rule_id): op for op in deployed.ops}

    added: list[TailoringOp] = []
    removed: list[TailoringOp] = []
    changed: list[OpChange] = []

    for key, op in expected_map.items():
        if key not in deployed_map:
            added.append(op)
        else:
            other = deployed_map[key]
            if op.action == "set_value" and (op.value or "") != (other.value or ""):
                changed.append(
                    OpChange(
                        rule_id=op.rule_id,
                        action="set_value",
                        expected_value=op.value or "",
                        deployed_value=other.value or "",
                    )
                )

    for key, op in deployed_map.items():
        if key not in expected_map:
            removed.append(op)

    added.sort(key=lambda o: o.rule_id)
    removed.sort(key=lambda o: o.rule_id)
    changed.sort(key=lambda c: c.rule_id)

    return TailoringDriftReport(
        profile_id_expected=expected.profile_id,
        profile_id_deployed=deployed.profile_id,
        added=added,
        removed=removed,
        changed=changed,
    )
