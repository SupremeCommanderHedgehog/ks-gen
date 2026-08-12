"""Every SSG rule ID a rule references must exist in that distro's datastream.

The per-distro rule-ID lists under docs/audit-story/ are extracted from the
pinned downstream scap-security-guide packages (see SSG-VERSIONS.md). A rule
that disables an ID the datastream doesn't have is a silent no-op: the
install still succeeds, but the STIG rule it was meant to moot stays
enabled and oscap reverts the operator's choice.

This is the mechanical guard for that whole class — it fails on the next SSG
bump that moves an ID out from under us, rather than waiting for someone to
notice on a live host.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ks_gen.registry import load_rules

_DOCS = Path(__file__).resolve().parent.parent / "docs" / "audit-story"
_DISTROS = ["alma8", "alma9", "alma10", "ubuntu2404"]


def _known_ids(distro: str) -> set[str]:
    path = _DOCS / f"{distro}-rule-ids.txt"
    if not path.is_file():
        pytest.skip(f"no extracted rule-id list for {distro}")
    return set(path.read_text(encoding="utf-8").split())


@pytest.mark.parametrize("distro", _DISTROS)
def test_referenced_rule_ids_exist_in_that_distros_datastream(distro):
    known = _known_ids(distro)
    offenders = {
        rule.id: sorted(set(getattr(rule, "stig_rules_affected", []) or []) - known)
        for rule in load_rules(distro)
    }
    offenders = {rid: missing for rid, missing in offenders.items() if missing}
    assert not offenders, (
        f"{distro} rules reference SSG rule IDs absent from "
        f"{distro}-rule-ids.txt: {offenders}. Either the rule needs a "
        f"per-distro divergence, or the extracted list is stale (see "
        f"docs/audit-story/SSG-VERSIONS.md)."
    )


def test_alma10_dropped_ids_are_genuinely_absent():
    """Pins the two alma10 divergences to the datastream, not to prose."""
    known = _known_ids("alma10")
    prefix = "xccdf_org.ssgproject.content_rule_"
    assert f"{prefix}banner_etc_issue_net" not in known
    assert f"{prefix}sshd_use_approved_ciphers" not in known
    # ...and that alma9 does have them, i.e. the divergence is real drift
    # rather than an extraction artefact.
    al9 = _known_ids("alma9")
    assert f"{prefix}banner_etc_issue_net" in al9
    assert f"{prefix}sshd_use_approved_ciphers" in al9
