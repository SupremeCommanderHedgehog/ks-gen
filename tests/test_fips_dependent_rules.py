"""Every FIPS-dependent stig-selected rule must be explicitly classified (#67).

tests/test_rule_ids_selected_by_stig.py asserts one direction — that nothing we
disable is unselected (#61). This file asserts the converse: on a host whose
operator chose MODERN or FUTURE, no stig-selected rule that depends on FIPS
stays quietly enabled. That gap left `sysctl_crypto_fips_enabled`,
`fips_crypto_subpolicy`, `system_booted_in_fips_mode` and
`enable_dracut_fips_module` — whose AL8 remediation runs `fips-mode-setup
--enable`, putting `fips=1` on the kernel command line of a host that opted out
— all enabled on non-FIPS installs.

The candidate queue is `docs/audit-story/<distro>-fips-candidates.txt`,
extracted from the shipped datastreams: every stig-selected rule whose OVAL
check or shell remediation mentions FIPS. It is deliberately over-inclusive.
A candidate is a rule someone must *classify*, not a rule that must be
disabled — bulk-disabling anything matching "fips" is how #61 happened.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ks_gen.config import CryptoPolicy, HostConfig
from ks_gen.registry import load_rules

_DOCS = Path(__file__).resolve().parent.parent / "docs" / "audit-story"
_DISTROS = ["alma8", "alma9", "alma10"]
_PREFIX = "xccdf_org.ssgproject.content_rule_"
_NON_STIG = [CryptoPolicy.MODERN, CryptoPolicy.FUTURE]

# Candidates deliberately left enabled, keyed by distro, with the reason each
# one still evaluates and passes off FIPS. Verified against the shipped
# datastreams; distro-scoped because the same rule is selected on one distro
# and not another (#66) — ssg 0.1.81 selects enable_fips_mode on AL10 but on
# neither AL8 nor AL9.
_PASSES_ANYWAY: dict[str, dict[str, str]] = {
    "alma8": {
        "configure_crypto_policy": (
            "variable-driven: var_system_crypto_policy is retuned to the chosen "
            "policy, so the rule evaluates and passes rather than being suppressed (#61)"
        ),
        "fips_custom_stig_sub_policy": (
            "newly stig-selected on AL8 in ssg 0.1.81 (#90). Checks the contents of "
            "/etc/crypto-policies/policies/modules/STIG.pmod, which its own remediation "
            "writes, so it passes under any policy. The remediation also sets FIPS:STIG, "
            "which the crypto_policy %post block re-points at the chosen policy "
            "immediately afterwards"
        ),
    },
    "alma9": {
        "crypto_policy_not_overridden": (
            "newly stig-selected in ssg 0.1.82 (#112); flagged only because its fix calls "
            "update-crypto-policies. The fix sets var_system_crypto_policy, which ks-gen "
            "retunes to the chosen policy (#61), so it never moves the host towards FIPS. "
            "The check is SCE-only and AlmaLinux's package ships no SCE scripts (nor does "
            "ks-gen install openscap-engine-sce), so it reports notchecked, never fail, "
            "under any policy"
        ),
        "configure_crypto_policy": (
            "variable-driven: var_system_crypto_policy is retuned to the chosen "
            "policy, so the rule evaluates and passes rather than being suppressed (#61)"
        ),
        "aide_use_fips_hashes": (
            "checks /etc/aide.conf for sha512; independent of FIPS mode, so it "
            "passes under DEFAULT and FUTURE too"
        ),
        "fips_custom_stig_sub_policy": (
            "checks the contents of /etc/crypto-policies/policies/modules/STIG.pmod, "
            "which its own remediation writes, so it passes under any policy. The "
            "remediation also sets FIPS:STIG, which the crypto_policy %post block "
            "re-points at the chosen policy immediately afterwards"
        ),
    },
    "alma10": {
        "crypto_policy_not_overridden": (
            "newly stig-selected in ssg 0.1.82 (#112); flagged only because its fix calls "
            "update-crypto-policies. The fix sets var_system_crypto_policy, which ks-gen "
            "retunes to the chosen policy (#61), so it never moves the host towards FIPS. "
            "The check is SCE-only and AlmaLinux's package ships no SCE scripts (nor does "
            "ks-gen install openscap-engine-sce), so it reports notchecked, never fail, "
            "under any policy"
        ),
        "configure_crypto_policy": (
            "variable-driven: var_system_crypto_policy is retuned to the chosen "
            "policy, so the rule evaluates and passes rather than being suppressed (#61)"
        ),
        "aide_use_fips_hashes": (
            "checks /etc/aide.conf for sha512; independent of FIPS mode, so it "
            "passes under DEFAULT and FUTURE too"
        ),
    },
}


def _candidates(distro: str) -> set[str]:
    """The distro's FIPS-dependent stig-selected rule IDs."""
    path = _DOCS / f"{distro}-fips-candidates.txt"
    # Deliberately NOT pytest.skip: a missing list is the failure mode this
    # guard exists to catch — a new distro would otherwise ship with every
    # FIPS-only rule unclassified and CI green.
    assert path.is_file(), (
        f"missing {path.name} — re-run scripts/audit_story/extract_ssg_rule_ids.py "
        f"with every datastream (see docs/audit-story/SSG-VERSIONS.md)."
    )
    lines = [line for line in path.read_text(encoding="utf-8").split("\n") if line]
    # A truncated extraction is a real failure; "extracted, found none" is not,
    # and the extractor writes an explicit marker line for it.
    assert lines, f"{path.name} is empty — the extraction was truncated"
    return {line.split("\t", 1)[0] for line in lines if not line.startswith("#")}


def _allow_listed(distro: str) -> set[str]:
    return {f"{_PREFIX}{short}" for short in _PASSES_ANYWAY[distro]}


def _cfg(minimal_cfg, distro: str, policy: CryptoPolicy) -> HostConfig:
    """Re-validated rather than model_copy'd: `distro` drives a mode="before"
    validator that derives meta.scap_content."""
    base = minimal_cfg.model_dump(exclude={"meta", "install"})
    return HostConfig.model_validate({**base, "distro": distro, "crypto": {"policy": policy.value}})


def _disabled(minimal_cfg, distro: str, policy: CryptoPolicy) -> set[str]:
    """Every SSG rule the distro's rules disable under the given crypto policy."""
    cfg = _cfg(minimal_cfg, distro, policy)
    return {
        op.rule_id
        for rule in load_rules(distro)
        if rule.applies(cfg)
        for op in rule.emit_tailoring(cfg)
        if op.action == "disable"
    }


@pytest.mark.parametrize("distro", _DISTROS)
@pytest.mark.parametrize("policy", _NON_STIG)
def test_every_fips_candidate_is_disabled_or_classified(distro, policy, minimal_cfg):
    unclassified = (
        _candidates(distro) - _disabled(minimal_cfg, distro, policy) - _allow_listed(distro)
    )
    assert not unclassified, (
        f"{distro}/{policy.value}: FIPS-dependent stig-selected rules are neither "
        f"disabled nor classified: {sorted(unclassified)}. Read the rule's OVAL check "
        f"and its sh remediation in the pinned datastream: if it cannot pass off FIPS, "
        f"or its remediation reconfigures the host towards FIPS, add it to that "
        f"distro's crypto_policy disable list; if it passes anyway, record it in "
        f"_PASSES_ANYWAY with the reason. Prefer a set_value retune where the rule is "
        f"variable-driven (#61)."
    )


@pytest.mark.parametrize("distro", _DISTROS)
def test_allow_list_has_no_stale_entries(distro):
    """A classified rule the profile stopped selecting is a stale exemption."""
    stale = _allow_listed(distro) - _candidates(distro)
    assert not stale, (
        f"{distro}: _PASSES_ANYWAY names rules that are no longer FIPS candidates: "
        f"{sorted(stale)} — drop them, the SSG bump already removed the reason."
    )


@pytest.mark.parametrize("distro", _DISTROS)
@pytest.mark.parametrize("policy", _NON_STIG)
def test_no_rule_is_both_disabled_and_classified_as_passing(distro, policy, minimal_cfg):
    both = _allow_listed(distro) & _disabled(minimal_cfg, distro, policy)
    assert not both, (
        f"{distro}/{policy.value}: {sorted(both)} are disabled *and* listed in "
        f"_PASSES_ANYWAY as passing. One of the two claims is wrong, and "
        f"exceptions.md reports the disable as a suppressed check."
    )


@pytest.mark.parametrize("distro", _DISTROS)
def test_every_classified_rule_carries_a_reason(distro):
    missing = [short for short, why in _PASSES_ANYWAY[distro].items() if not why.strip()]
    assert not missing, f"{distro}: _PASSES_ANYWAY entries without a reason: {missing}"


@pytest.mark.parametrize("distro", _DISTROS)
def test_stig_fips_candidates_stay_enabled(distro, minimal_cfg):
    """#84: a STIG host reaches kernel FIPS, so its FIPS rules must stay enabled.

    They are expected to pass; suppressing them would hide a real regression
    behind an exception the host does not need.
    """
    cfg = _cfg(minimal_cfg, distro, CryptoPolicy.STIG)
    assert cfg.kernel_fips, f"{distro}/STIG must boot with kernel FIPS (#84)"
    suppressed = _candidates(distro) & _disabled(minimal_cfg, distro, CryptoPolicy.STIG)
    assert not suppressed, (
        f"{distro}/STIG reaches kernel FIPS, so {sorted(suppressed)} must stay "
        f"enabled and pass. Disabling them hides real regressions behind an "
        f"exception the host does not need."
    )
