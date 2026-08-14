from __future__ import annotations

import shutil
import subprocess

import pytest

from ks_gen.config import Crypto, CryptoPolicy, HostConfig
from ks_gen.registry import load_rules
from ks_gen.rules.alma9.crypto_policy import RULE


def test_stig_emits_fips(minimal_cfg):
    cfg = minimal_cfg.model_copy(update={"crypto": Crypto(policy=CryptoPolicy.STIG)})
    out = RULE.emit_post(cfg)
    assert "update-crypto-policies --set FIPS" in out


def test_modern_emits_default_and_ed25519(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)  # default MODERN
    assert "update-crypto-policies --set DEFAULT" in out
    assert "ssh-keygen -A" in out


def test_modern_tailoring_disables_fips_and_the_crypto_policy_backend_rules(minimal_cfg):
    # Per #61: the set is derived from what the AL9 stig profile actually
    # selects. sshd_use_approved_ciphers exists in the datastream but is never
    # selected, so disabling it was inert; the four harden_sshd_* rules are
    # the ones that fire, and each asserts a FIPS-only algorithm list in the
    # crypto-policies back-end files that MODERN/FUTURE rewrites.
    # Per #67: the three FIPS-only rules below can never pass off FIPS either.
    ops = RULE.emit_tailoring(minimal_cfg)
    disabled = {o.rule_id for o in ops if o.action == "disable"}
    assert disabled == {
        "xccdf_org.ssgproject.content_rule_enable_fips_mode",
        "xccdf_org.ssgproject.content_rule_harden_sshd_ciphers_openssh_conf_crypto_policy",
        "xccdf_org.ssgproject.content_rule_harden_sshd_ciphers_opensshserver_conf_crypto_policy",
        "xccdf_org.ssgproject.content_rule_harden_sshd_macs_openssh_conf_crypto_policy",
        "xccdf_org.ssgproject.content_rule_harden_sshd_macs_opensshserver_conf_crypto_policy",
        "xccdf_org.ssgproject.content_rule_sysctl_crypto_fips_enabled",
        "xccdf_org.ssgproject.content_rule_enable_dracut_fips_module",
        "xccdf_org.ssgproject.content_rule_fips_crypto_subpolicy",
    }


def test_modern_tailoring_leaves_the_rules_that_pass_off_fips_enabled(minimal_cfg):
    """#67's care rule: only rules that cannot pass get disabled.

    aide_use_fips_hashes wants sha512 in aide.conf and fips_custom_stig_sub_policy
    checks a file its own remediation writes — both pass under DEFAULT, so
    disabling them would put a misleading line in exceptions.md.
    """
    disabled = {o.rule_id for o in RULE.emit_tailoring(minimal_cfg) if o.action == "disable"}
    assert "xccdf_org.ssgproject.content_rule_aide_use_fips_hashes" not in disabled
    assert "xccdf_org.ssgproject.content_rule_fips_custom_stig_sub_policy" not in disabled


def test_modern_tailoring_retunes_the_crypto_policy_variable(minimal_cfg):
    ops = RULE.emit_tailoring(minimal_cfg)
    set_values = [o for o in ops if o.action == "set_value"]
    assert len(set_values) == 1
    assert set_values[0].rule_id == ("xccdf_org.ssgproject.content_value_var_system_crypto_policy")
    assert set_values[0].value == "DEFAULT"


def test_stig_emits_no_tailoring(minimal_cfg):
    cfg = minimal_cfg.model_copy(update={"crypto": Crypto(policy=CryptoPolicy.STIG)})
    assert RULE.emit_tailoring(cfg) == []


def test_exception_entry_named_for_non_stig(minimal_cfg):
    entry = RULE.exception_entry(minimal_cfg)
    assert entry is not None
    assert "MODERN" in entry.summary


def test_no_exception_for_stig(minimal_cfg):
    cfg = minimal_cfg.model_copy(update={"crypto": Crypto(policy=CryptoPolicy.STIG)})
    assert RULE.exception_entry(cfg) is None


# ---- #84: STIG must put the kernel in FIPS mode, not just the crypto policy ----

_ALMA = ["alma8", "alma9", "alma10"]


def _rule(distro: str):
    return next(r for r in load_rules(distro) if r.id == "crypto_policy")


def _post(minimal_cfg, distro: str, policy: str) -> str:
    base = minimal_cfg.model_dump(exclude={"meta", "install"})
    cfg = HostConfig.model_validate({**base, "distro": distro, "crypto": {"policy": policy}})
    return _rule(distro).emit_post(cfg)


@pytest.mark.parametrize("distro", _ALMA)
def test_stig_enables_kernel_fips(minimal_cfg, distro):
    body = _post(minimal_cfg, distro, "STIG")
    assert "fips-mode-setup --enable" in body
    assert "dracut -f --regenerate-all" in body


@pytest.mark.parametrize("distro", _ALMA)
def test_fips_enablement_precedes_the_policy_set(minimal_cfg, distro):
    """fips-mode-setup resets the policy to plain FIPS, so it must run first (#66)."""
    body = _post(minimal_cfg, distro, "STIG")
    assert body.index("fips-mode-setup --enable") < body.index("update-crypto-policies --set")


@pytest.mark.parametrize("distro", _ALMA)
def test_fips_enablement_failure_aborts_the_install(minimal_cfg, distro):
    """A silent fallback would re-create #84: a host claiming FIPS without it."""
    body = _post(minimal_cfg, distro, "STIG")
    assert "fips-mode-setup --enable || true" not in body
    assert "exit 1" in body


@pytest.mark.parametrize("distro", _ALMA)
def test_fips_mode_setup_exit_code_alone_is_not_fatal(minimal_cfg, distro):
    """Its inner `dracut -f` targets the installer's kernel and fails on a
    network install; the outcome is what matters, not the exit code (#84)."""
    body = _post(minimal_cfg, distro, "STIG")
    stmt = next(ln for ln in body.splitlines() if ln.startswith("fips-mode-setup --enable"))
    assert "exit 1" not in stmt
    assert not stmt.rstrip().endswith("{")


@pytest.mark.parametrize("distro", _ALMA)
def test_stig_asserts_fips_reached_the_installed_kernel_args(minimal_cfg, distro):
    """fips=1 missing from the installed entries means a non-FIPS boot (#84)."""
    body = _post(minimal_cfg, distro, "STIG")
    assert "grubby --info=ALL" in body
    checks = [ln for ln in body.splitlines() if "fips=1" in ln and "exit 1" in ln]
    assert checks, body
    assert all("ks-gen:" in ln for ln in checks)


@pytest.mark.parametrize("distro", _ALMA)
def test_stig_requires_the_dracut_fips_conf(minimal_cfg, distro):
    """No 40-fips.conf means the regenerated initramfs has no FIPS module (#84)."""
    body = _post(minimal_cfg, distro, "STIG")
    check = next(ln for ln in body.splitlines() if "/etc/dracut.conf.d/40-fips.conf" in ln)
    assert "exit 1" in check
    assert "ks-gen:" in check


@pytest.mark.parametrize("distro", _ALMA)
def test_stig_establishes_a_non_empty_boot_uuid(minimal_cfg, distro):
    """/boot is always separate; fips=1 without boot= drops to the dracut shell."""
    body = _post(minimal_cfg, distro, "STIG")
    assert "findmnt -no UUID /boot" in body
    assert "grubby --update-kernel=ALL --args=" in body
    assert "boot=UUID=$" in body or "boot=UUID=${" in body
    assert 'boot=UUID="' not in body  # never a bare, empty value


@pytest.mark.parametrize("distro", _ALMA)
def test_stig_aborts_when_boot_uuid_cannot_be_resolved(minimal_cfg, distro):
    body = _post(minimal_cfg, distro, "STIG")
    guard = next(ln for ln in body.splitlines() if "findmnt" not in ln and "boot_uuid" in ln)
    assert "exit 1" in guard
    assert "ks-gen:" in guard


@pytest.mark.parametrize("distro", _ALMA)
def test_initramfs_is_regenerated_for_every_installed_kernel(minimal_cfg, distro):
    """`dracut -f` alone targets `uname -r` — the installer's kernel (#84)."""
    body = _post(minimal_cfg, distro, "STIG")
    assert "dracut -f --regenerate-all" in body


@pytest.mark.parametrize("distro", _ALMA)
def test_fips_verification_precedes_the_policy_set(minimal_cfg, distro):
    """All of it must land before update-crypto-policies re-applies the policy (#66)."""
    body = _post(minimal_cfg, distro, "STIG")
    assert body.index("40-fips.conf") < body.index("update-crypto-policies --set")
    assert body.index("grubby") < body.index("update-crypto-policies --set")


@pytest.mark.parametrize("distro", _ALMA)
@pytest.mark.parametrize("policy", ["MODERN", "FUTURE"])
def test_non_stig_never_touches_fips(minimal_cfg, distro, policy):
    body = _post(minimal_cfg, distro, policy)
    assert "fips-mode-setup" not in body
    assert "dracut" not in body
    assert "grubby" not in body
    assert "findmnt" not in body


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
@pytest.mark.parametrize("distro", _ALMA)
@pytest.mark.parametrize("policy", ["STIG", "MODERN", "FUTURE"])
def test_emitted_post_is_valid_bash(minimal_cfg, distro, policy, tmp_path):
    script = tmp_path / "post.sh"
    script.write_text("set -euxo pipefail\n" + _post(minimal_cfg, distro, policy))
    proc = subprocess.run(
        [shutil.which("bash") or "bash", "-n", str(script)], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize("distro", _ALMA)
@pytest.mark.parametrize("policy", ["STIG", "MODERN", "FUTURE"])
def test_post_fips_block_matches_the_bootloader_predicate(minimal_cfg, distro, policy):
    """%post and the fips=1 boot arg must never disagree (#84)."""
    base = minimal_cfg.model_dump(exclude={"meta", "install"})
    cfg = HostConfig.model_validate({**base, "distro": distro, "crypto": {"policy": policy}})
    rule = next(r for r in load_rules(distro) if r.id == "crypto_policy")
    assert ("fips-mode-setup --enable" in rule.emit_post(cfg)) is cfg.kernel_fips


@pytest.mark.parametrize("distro", _ALMA)
@pytest.mark.parametrize("policy", ["STIG", "MODERN", "FUTURE"])
def test_policy_header_line_stays_first(minimal_cfg, distro, policy):
    """run.sh parses this line to learn the expected policy — keep it line 1."""
    body = _post(minimal_cfg, distro, policy)
    assert body.splitlines()[0].startswith("# Apply system-wide crypto policy:")


# ---- #84: Ubuntu can never reach kernel FIPS, so say so under STIG too ----

_IS_FIPS = "xccdf_org.ssgproject.content_rule_is_fips_mode_enabled"


def _ubuntu_cfg(minimal_cfg, policy: str) -> HostConfig:
    base = minimal_cfg.model_dump(exclude={"meta", "install"})
    return HostConfig.model_validate({**base, "distro": "ubuntu2404", "crypto": {"policy": policy}})


def _ubuntu_disabled(minimal_cfg, policy: str) -> set[str]:
    cfg = _ubuntu_cfg(minimal_cfg, policy)
    return {op.rule_id for op in _rule("ubuntu2404").emit_tailoring(cfg) if op.action == "disable"}


@pytest.mark.parametrize("policy", ["STIG", "MODERN", "FUTURE"])
def test_ubuntu_always_disables_is_fips_mode_enabled(minimal_cfg, policy):
    assert _IS_FIPS in _ubuntu_disabled(minimal_cfg, policy)


@pytest.mark.parametrize("policy", ["STIG", "MODERN", "FUTURE"])
def test_ubuntu_declares_every_rule_it_disables(minimal_cfg, policy):
    entry = _rule("ubuntu2404").exception_entry(_ubuntu_cfg(minimal_cfg, policy))
    assert entry is not None
    assert _ubuntu_disabled(minimal_cfg, policy) <= set(entry.stig_rules_disabled)


def test_ubuntu_stig_exception_names_the_pro_entitlement(minimal_cfg):
    """The reason must say why it cannot pass, not just that it is disabled."""
    entry = _rule("ubuntu2404").exception_entry(_ubuntu_cfg(minimal_cfg, "STIG"))
    assert entry is not None
    assert "fips-updates" in entry.reason


def test_ubuntu_stig_keeps_the_sshd_algorithm_rules_enabled(minimal_cfg):
    """STIG writes exactly those algorithm lists, so those rules must evaluate."""
    assert _ubuntu_disabled(minimal_cfg, "STIG") == {_IS_FIPS}
