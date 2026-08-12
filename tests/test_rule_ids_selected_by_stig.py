"""Every SSG rule a ks-gen rule disables must be selected by the stig profile.

Existence is too weak a guard (see tests/test_rule_ids_exist_in_datastream.py):
an ID can be present in the datastream and still never run, because the `stig`
profile does not select it. Disabling such a rule is inert — it produces a
tailoring entry and an exceptions.md line that both claim to suppress a check
that was never going to fire, while the check that *does* fire stays enabled.

That is issue #61: on alma9/alma8 the MODERN/FUTURE crypto exception disabled
`sshd_use_approved_ciphers` (not selected) and left the two stig-selected
`harden_sshd_ciphers_*` rules enabled.

The `<distro>-stig-selected.txt` lists are extracted from the same pinned
datastreams as the rule-ID lists — see docs/audit-story/SSG-VERSIONS.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ks_gen.config import Crypto, CryptoPolicy
from ks_gen.registry import load_rules

_DOCS = Path(__file__).resolve().parent.parent / "docs" / "audit-story"
_DISTROS = ["alma8", "alma9", "alma10", "ubuntu2404"]
_RHEL_FAMILY = ["alma8", "alma9", "alma10"]
_RULE_PREFIX = "xccdf_org.ssgproject.content_rule_"


def _stig_selected(distro: str) -> set[str]:
    path = _DOCS / f"{distro}-stig-selected.txt"
    if not path.is_file():
        pytest.skip(f"no extracted stig-selected list for {distro}")
    return set(path.read_text(encoding="utf-8").split())


@pytest.mark.parametrize("distro", _DISTROS)
def test_declared_stig_rules_affected_are_stig_selected(distro):
    selected = _stig_selected(distro)
    offenders = {
        rule.id: sorted(set(getattr(rule, "stig_rules_affected", []) or []) - selected)
        for rule in load_rules(distro)
    }
    offenders = {rid: unselected for rid, unselected in offenders.items() if unselected}
    assert not offenders, (
        f"{distro} rules declare SSG rule IDs the stig profile does not select: "
        f"{offenders}. Disabling an unselected rule is inert — find the rule the "
        f"stig profile actually selects for that check, or drop the ID."
    )


@pytest.mark.parametrize("distro", _RHEL_FAMILY)
@pytest.mark.parametrize("policy", [CryptoPolicy.MODERN, CryptoPolicy.FUTURE])
def test_crypto_policy_only_disables_stig_selected_rules(distro, policy, minimal_cfg):
    """The #61 regression, checked against emitted ops rather than the declared list."""
    selected = _stig_selected(distro)
    cfg = minimal_cfg.model_copy(update={"distro": distro, "crypto": Crypto(policy=policy)})
    crypto = next(r for r in load_rules(distro) if r.id == "crypto_policy")

    disabled = {op.rule_id for op in crypto.emit_tailoring(cfg) if op.action == "disable"}
    assert disabled, f"{distro}/{policy.value} should disable the FIPS-dependent rules"
    assert disabled <= selected, (
        f"{distro}/{policy.value} disables rules the stig profile never selects: "
        f"{sorted(disabled - selected)}"
    )


@pytest.mark.parametrize("distro", _RHEL_FAMILY)
def test_crypto_policy_retunes_the_policy_variable_instead_of_disabling_it(distro, minimal_cfg):
    """configure_crypto_policy is variable-driven, so it can pass rather than be skipped."""
    cfg = minimal_cfg.model_copy(
        update={"distro": distro, "crypto": Crypto(policy=CryptoPolicy.MODERN)}
    )
    crypto = next(r for r in load_rules(distro) if r.id == "crypto_policy")
    ops = crypto.emit_tailoring(cfg)

    set_values = [op for op in ops if op.action == "set_value"]
    assert len(set_values) == 1
    assert set_values[0].rule_id.endswith("value_var_system_crypto_policy")
    assert set_values[0].value == "DEFAULT"
    # ...and the rule it governs is left enabled, not disabled.
    assert f"{_RULE_PREFIX}configure_crypto_policy" not in {
        op.rule_id for op in ops if op.action == "disable"
    }


@pytest.mark.parametrize("distro", _DISTROS)
def test_set_value_ops_target_values_not_rules(distro, minimal_cfg):
    """A set_value op must name an XCCDF Value; naming a Rule would silently no-op."""
    cfg = minimal_cfg.model_copy(update={"distro": distro})
    for rule in load_rules(distro):
        if not rule.applies(cfg):
            continue
        for op in rule.emit_tailoring(cfg):
            if op.action == "set_value":
                assert not op.rule_id.startswith(_RULE_PREFIX), (
                    f"{distro}/{rule.id}: set_value targets a Rule ID ({op.rule_id}); "
                    f"it must target an xccdf Value ID"
                )
