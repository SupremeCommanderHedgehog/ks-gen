"""Under STIG, the crypto policy is oscap's to choose — ks-gen must not name it.

The original bug (#66) was drift between two places that had to agree: ks-gen's
`update-crypto-policies --set <X>` and the stig profile's `refine-value` for
`var_system_crypto_policy`. The first fix pinned ks-gen's value to the profile's,
checked against the extracted datastream.

That fix was not enough, and #90 is why. There is no single profile to agree
with: oscap remediates against whatever `scap-security-guide` the host has, and
a host does not have one version over its life. The AlmaLinux 8.10 DVD ships
0.1.72, whose stig profile refines the value to `FIPS`; the repos ship 0.1.81,
which refines it to `FIPS:STIG`. An offline install stays on the first, an
online one is upgraded to the second. Whichever literal ks-gen pinned, the other
kind of install failed `configure_crypto_policy` forever with no
expected-failure entry to explain it.

So ks-gen stopped choosing. oscap's own `configure_crypto_policy` remediation
applies the value its content refines to, which is right for that content by
construction; ks-gen's `%post` — which runs *after* the oscap block, and so
would silently override it — verifies the result instead of setting it.

These tests hold that line: no hardcoded target under STIG, a real verification
in its place, and non-STIG policies still applied by ks-gen (oscap will not set
DEFAULT or FUTURE for us).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ks_gen.config import Crypto, CryptoPolicy, HostConfig
from ks_gen.registry import load_rules

_DOCS = Path(__file__).resolve().parent.parent / "docs" / "audit-story"
_FLOORS = _DOCS / "floors"
_VAR = "xccdf_org.ssgproject.content_value_var_system_crypto_policy"

_SET = re.compile(r"^\s*update-crypto-policies --set (\S+)$", re.M)


def _refined_in(path: Path) -> str | None:
    """The value one extracted profile refines var_system_crypto_policy to."""
    for line in path.read_text(encoding="utf-8").splitlines():
        idref, _, value = line.partition("\t")
        if idref == _VAR:
            return value
    return None


def _refined_crypto_policy(distro: str) -> str | None:
    path = _DOCS / f"{distro}-stig-refine-values.txt"
    assert path.is_file(), (
        f"missing {path.name} — re-run scripts/audit_story/extract_ssg_rule_ids.py "
        f"with all four datastreams (see docs/audit-story/SSG-VERSIONS.md)."
    )
    return _refined_in(path)


def _supported_crypto_policies(distro: str) -> set[str]:
    """Every value this distro's stig profile refines to across supported SSG.

    Current pin plus each checked-in media floor. More than one value here is
    the whole reason ks-gen cannot hardcode a target.
    """
    values = {_refined_crypto_policy(distro)}
    for path in sorted(_FLOORS.glob(f"{distro}-*-stig-refine-values.txt")):
        values.add(_refined_in(path))
    return {v for v in values if v}


def _distros_with_crypto_refinement() -> list[str]:
    """Derived from the shipped lists, not hardcoded, so a distro added later
    is covered automatically instead of silently untested."""
    return [
        distro
        for path in sorted(_DOCS.glob("*-stig-refine-values.txt"))
        if _refined_crypto_policy(distro := path.name[: -len("-stig-refine-values.txt")])
    ]


_RHEL_FAMILY = _distros_with_crypto_refinement()


def test_the_derived_distro_list_is_not_empty():
    """A glob that matches nothing would make every parametrized test vanish."""
    assert _RHEL_FAMILY, "no distro exposes a var_system_crypto_policy refinement"
    assert "alma9" in _RHEL_FAMILY


def _cfg_for(minimal_cfg, distro: str, policy: CryptoPolicy) -> HostConfig:
    base = minimal_cfg.model_dump(exclude={"meta", "install"})
    return HostConfig.model_validate({**base, "distro": distro, "crypto": Crypto(policy=policy)})


def _post(minimal_cfg, distro: str, policy: CryptoPolicy) -> str:
    cfg = _cfg_for(minimal_cfg, distro, policy)
    return next(r for r in load_rules(distro) if r.id == "crypto_policy").emit_post(cfg)


def test_the_refined_value_is_not_stable_across_supported_releases():
    """The premise of this whole file: pinning one literal cannot be correct.

    If upstream ever converged on a single value for every supported release of
    every distro, hardcoding would stop being a bug and this file would be
    guarding nothing — so assert the disagreement is real rather than assumed.
    """
    observed = {v for distro in _RHEL_FAMILY for v in _supported_crypto_policies(distro)}
    assert len(observed) > 1, (
        f"every supported release now refines {_VAR} to the same value ({observed}). "
        f"Re-check whether ks-gen still needs to defer to oscap, and re-read #90 "
        f"before pinning a literal again."
    )


@pytest.mark.parametrize("distro", _RHEL_FAMILY)
def test_stig_post_sets_no_crypto_policy(distro, minimal_cfg):
    """Setting one here overrides oscap — this %post runs after that block."""
    post = _post(minimal_cfg, distro, CryptoPolicy.STIG)
    applied = _SET.findall(post)
    assert not applied, (
        f"{distro}: %post applies {applied} under STIG. The value belongs to the "
        f"installed content's stig profile, which differs between the media and "
        f"the repos ({_supported_crypto_policies(distro)}); this block runs after "
        f"oscap, so anything set here silently overrides the remediation (#90)."
    )


@pytest.mark.parametrize("distro", _RHEL_FAMILY)
def test_stig_post_names_no_supported_policy_literal(distro, minimal_cfg):
    """Catches a hardcode reintroduced by some other mechanism than --set."""
    post = _post(minimal_cfg, distro, CryptoPolicy.STIG)
    # FIPS on its own is the verification's accept-condition, not a target.
    literals = {v for v in _supported_crypto_policies(distro) if ":" in v}
    offenders = sorted(v for v in literals if v in post)
    assert not offenders, (
        f"{distro}: %post names the sub-policy target(s) {offenders}. Whichever "
        f"release ks-gen pins to, hosts running the other one fail (#90)."
    )


@pytest.mark.parametrize("distro", _RHEL_FAMILY)
def test_stig_post_verifies_the_policy_oscap_applied(distro, minimal_cfg):
    """Not setting it is only safe if a failure to apply it is caught."""
    post = _post(minimal_cfg, distro, CryptoPolicy.STIG)
    assert "update-crypto-policies --show" in post, (
        f"{distro}: %post neither sets nor checks the crypto policy. If oscap's "
        f"remediation did not run, the host ships non-FIPS with no signal."
    )
    assert '"${ks_policy%%:*}" = FIPS' in post, (
        f"{distro}: the accept-condition must strip the sub-policy, so that FIPS "
        f"and any FIPS:<sub> both pass without ks-gen naming which one."
    )
    assert "exit 1" in post, f"{distro}: a non-FIPS policy under STIG must fail the install"


@pytest.mark.parametrize("distro", _RHEL_FAMILY)
@pytest.mark.parametrize(
    ("policy", "target"), [(CryptoPolicy.MODERN, "DEFAULT"), (CryptoPolicy.FUTURE, "FUTURE")]
)
def test_non_stig_policies_are_applied_by_ks_gen(distro, policy, target, minimal_cfg):
    """oscap will not set these — the profile only ever asks for FIPS."""
    post = _post(minimal_cfg, distro, policy)
    assert _SET.findall(post) == [target], (
        f"{distro}/{policy.value}: %post must apply {target} itself; nothing else will."
    )


@pytest.mark.parametrize("distro", _RHEL_FAMILY)
def test_stig_generates_fips_approved_host_keys(distro, minimal_cfg):
    """#72: without a host key, ssh_config_apply's `sshd -t` aborts the install.

    ssh-keygen -A would also mint an Ed25519 key, which is exactly what the
    STIG branch avoids under FIPS — so the approved types are generated
    explicitly, guarded so an existing key is never clobbered.
    """
    post = _post(minimal_cfg, distro, CryptoPolicy.STIG)

    assert "ssh-keygen -q -t rsa -b 3072 -f /etc/ssh/ssh_host_rsa_key" in post
    assert "ssh-keygen -q -t ecdsa -b 384 -f /etc/ssh/ssh_host_ecdsa_key" in post
    assert "[ -f /etc/ssh/ssh_host_rsa_key ] ||" in post
    assert "ed25519" not in post, "Ed25519 is not FIPS 140 approved"
    assert "ssh-keygen -A" not in post, "-A would create an Ed25519 host key"
    assert post.isascii(), "generated %post shell must stay ASCII"


@pytest.mark.parametrize("distro", _RHEL_FAMILY)
def test_non_stig_still_uses_ssh_keygen_A(distro, minimal_cfg):
    assert "ssh-keygen -A" in _post(minimal_cfg, distro, CryptoPolicy.MODERN)
