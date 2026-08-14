"""What `%post` applies must equal what the stig profile expects (#66).

`update-crypto-policies --set <X>` and the profile's `refine-value` for
`var_system_crypto_policy` are written in two different places — ks-gen's rule
and the SSG datastream — and nothing tied them together. On alma9 they had
drifted: `%post` set `FIPS` while the AL9 profile expects `FIPS:STIG`, so
`configure_crypto_policy` failed on every STIG-policy host with no
expected-failure entry to explain it.

The expected side is read from `<distro>-stig-refine-values.txt`, extracted
from the shipped datastreams, so an upstream change to the refinement fails
this test instead of silently un-fixing the bug. The value genuinely differs
per distro, and upstream moves it: AL8 expected plain FIPS through ssg 0.1.74
and the STIG sub-policy from 0.1.81 (#90). Nothing here pins a literal.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ks_gen.config import Crypto, CryptoPolicy, HostConfig
from ks_gen.registry import load_rules

_DOCS = Path(__file__).resolve().parent.parent / "docs" / "audit-story"
_VAR = "xccdf_org.ssgproject.content_value_var_system_crypto_policy"


def _refined_crypto_policy(distro: str) -> str | None:
    """The value the distro's stig profile refines var_system_crypto_policy to."""
    path = _DOCS / f"{distro}-stig-refine-values.txt"
    assert path.is_file(), (
        f"missing {path.name} — re-run scripts/audit_story/extract_ssg_rule_ids.py "
        f"with all four datastreams (see docs/audit-story/SSG-VERSIONS.md)."
    )
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        idref, _, value = line.partition("\t")
        if idref == _VAR:
            return value
    return None


def _distros_with_crypto_refinement() -> list[str]:
    """Derived from the shipped lists, not hardcoded.

    A distro added later whose stig profile refines the crypto policy is then
    covered automatically; a hardcoded list would leave it silently untested
    and let #66 return on the new target.
    """
    found = []
    for path in sorted(_DOCS.glob("*-stig-refine-values.txt")):
        distro = path.name[: -len("-stig-refine-values.txt")]
        if _refined_crypto_policy(distro):
            found.append(distro)
    return found


_RHEL_FAMILY = _distros_with_crypto_refinement()

# Distros split by whether their refined value names a sub-policy — derived,
# not listed, because which side a distro falls on is upstream's to change and
# has changed (#90).
_SUB_POLICY = [d for d in _RHEL_FAMILY if ":" in (_refined_crypto_policy(d) or "")]
_PLAIN_POLICY = [d for d in _RHEL_FAMILY if ":" not in (_refined_crypto_policy(d) or "")]


def test_the_derived_distro_list_is_not_empty():
    """A glob that matches nothing would make every parametrized test vanish."""
    assert _RHEL_FAMILY, "no distro exposes a var_system_crypto_policy refinement"
    assert "alma9" in _RHEL_FAMILY


def _cfg_for(minimal_cfg, distro: str, policy: CryptoPolicy) -> HostConfig:
    base = minimal_cfg.model_dump(exclude={"meta", "install"})
    return HostConfig.model_validate({**base, "distro": distro, "crypto": Crypto(policy=policy)})


@pytest.mark.parametrize("distro", _RHEL_FAMILY)
def test_stig_post_applies_the_policy_the_profile_expects(distro, minimal_cfg):
    expected = _refined_crypto_policy(distro)
    assert expected, f"{distro} stig profile does not refine {_VAR}"

    cfg = _cfg_for(minimal_cfg, distro, CryptoPolicy.STIG)
    crypto = next(r for r in load_rules(distro) if r.id == "crypto_policy")

    assert f"update-crypto-policies --set {expected}\n" in crypto.emit_post(cfg), (
        f"{distro}: %post must apply {expected!r} — the value its stig profile "
        f"refines var_system_crypto_policy to. Applying anything else leaves "
        f"configure_crypto_policy failing on every STIG-policy host."
    )


@pytest.mark.parametrize("distro", _SUB_POLICY)
def test_sub_policy_target_is_guarded_by_its_module_file(distro, minimal_cfg):
    """A `FIPS:<sub>` target needs <sub>.pmod, which the OS does not ship.

    SSG's own fips_custom_stig_sub_policy remediation writes that module
    earlier in the install. Since this %post block runs under `set -e` with
    --erroronfail, an unguarded `--set FIPS:STIG` would abort the install
    whenever oscap's remediation didn't run — turning verify noise into a
    failed build.
    """
    target = _refined_crypto_policy(distro) or ""
    base, _, sub = target.partition(":")
    cfg = _cfg_for(minimal_cfg, distro, CryptoPolicy.STIG)
    post = next(r for r in load_rules(distro) if r.id == "crypto_policy").emit_post(cfg)

    # Both module search paths: SSG writes it under /etc, but the stock
    # modules ship under /usr/share, so testing only /etc would fall back
    # needlessly if a future package shipped this one.
    assert f"/etc/crypto-policies/policies/modules/{sub}.pmod" in post
    assert f"/usr/share/crypto-policies/policies/modules/{sub}.pmod" in post
    assert post.count("update-crypto-policies --set") == 2, "guarded set + fallback"
    assert f"update-crypto-policies --set {target}" in post
    assert f"update-crypto-policies --set {base}\n" in post  # the fallback
    assert post.isascii(), "generated %post shell must stay ASCII"


def test_at_least_one_distro_still_needs_the_sub_policy_guard():
    """The guard above vanishes silently if the derived list empties out."""
    assert _SUB_POLICY, "no distro refines to a FIPS:<sub> target — is the extract stale?"


@pytest.mark.parametrize("distro", _RHEL_FAMILY)
def test_stig_generates_fips_approved_host_keys(distro, minimal_cfg):
    """#72: without a host key, ssh_config_apply's `sshd -t` aborts the install.

    ssh-keygen -A would also mint an Ed25519 key, which is exactly what the
    STIG branch avoids under FIPS — so the approved types are generated
    explicitly, guarded so an existing key is never clobbered.
    """
    cfg = _cfg_for(minimal_cfg, distro, CryptoPolicy.STIG)
    post = next(r for r in load_rules(distro) if r.id == "crypto_policy").emit_post(cfg)

    assert "ssh-keygen -q -t rsa -b 3072 -f /etc/ssh/ssh_host_rsa_key" in post
    assert "ssh-keygen -q -t ecdsa -b 384 -f /etc/ssh/ssh_host_ecdsa_key" in post
    assert "[ -f /etc/ssh/ssh_host_rsa_key ] ||" in post
    assert "ed25519" not in post, "Ed25519 is not FIPS 140 approved"
    assert "ssh-keygen -A" not in post, "-A would create an Ed25519 host key"


@pytest.mark.parametrize("distro", _RHEL_FAMILY)
def test_non_stig_still_uses_ssh_keygen_A(distro, minimal_cfg):
    cfg = _cfg_for(minimal_cfg, distro, CryptoPolicy.MODERN)
    post = next(r for r in load_rules(distro) if r.id == "crypto_policy").emit_post(cfg)
    assert "ssh-keygen -A" in post


@pytest.mark.parametrize("distro", _PLAIN_POLICY)
def test_plain_policies_need_no_module_guard(distro, minimal_cfg):
    target = _refined_crypto_policy(distro)
    cfg = _cfg_for(minimal_cfg, distro, CryptoPolicy.STIG)
    post = next(r for r in load_rules(distro) if r.id == "crypto_policy").emit_post(cfg)
    assert ".pmod" not in post
    assert f"update-crypto-policies --set {target}\n" in post


_SET = re.compile(r"^\s*update-crypto-policies --set (\S+)$", re.M)


def _applied_stig_target(minimal_cfg, distro: str) -> str:
    """The policy %post actually applies on a STIG host.

    The guarded sub-policy branch emits the fallback second, so the first
    match is the intended target.
    """
    cfg = _cfg_for(minimal_cfg, distro, CryptoPolicy.STIG)
    post = next(r for r in load_rules(distro) if r.id == "crypto_policy").emit_post(cfg)
    match = _SET.search(post)
    assert match, f"{distro}: %post applies no crypto policy at all"
    return match.group(1)


def test_the_stig_value_is_resolved_per_distro_not_family_wide(minimal_cfg):
    """Guards against a 'fix' that hardcodes one crypto target for the family.

    Deliberately asserts no literal. Upstream owns these values and has moved
    them — AL8's stig profile switched from FIPS to FIPS:STIG in ssg 0.1.81 and
    the literals pinned here went stale, which is #90. Instead: ks-gen must
    apply as many distinct targets across the family as the profiles refine to,
    so collapsing them onto one value fails here.

    Which target each distro gets is checked separately by
    test_stig_post_applies_the_policy_the_profile_expects. If upstream ever
    converges on a single value this test stops discriminating, and correctly
    so — a single value would then not be a hardcode.
    """
    upstream = {_refined_crypto_policy(d) for d in _RHEL_FAMILY}
    applied = {_applied_stig_target(minimal_cfg, d) for d in _RHEL_FAMILY}
    assert len(applied) == len(upstream), (
        f"the stig profiles refine var_system_crypto_policy to {len(upstream)} "
        f"distinct values across {_RHEL_FAMILY}, but %post applies {len(applied)}. "
        f"The crypto target must be resolved per distro — one value for the whole "
        f"family leaves configure_crypto_policy failing wherever it is wrong (#66)."
    )
