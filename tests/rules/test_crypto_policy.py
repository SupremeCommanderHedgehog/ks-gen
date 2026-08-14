from __future__ import annotations

import re
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
    # selects. The four harden_sshd_* rules are the ones that fire, and each
    # asserts a FIPS-only algorithm list in the crypto-policies back-end files
    # that MODERN/FUTURE rewrites; sysctl_crypto_fips_enabled and
    # fips_crypto_subpolicy can never pass off FIPS either (#67).
    # Per #90: ssg-almalinux9 0.1.81 dropped enable_fips_mode and
    # enable_dracut_fips_module from the profile, so both left this set.
    ops = RULE.emit_tailoring(minimal_cfg)
    disabled = {o.rule_id for o in ops if o.action == "disable"}
    assert disabled == {
        "xccdf_org.ssgproject.content_rule_harden_sshd_ciphers_openssh_conf_crypto_policy",
        "xccdf_org.ssgproject.content_rule_harden_sshd_ciphers_opensshserver_conf_crypto_policy",
        "xccdf_org.ssgproject.content_rule_harden_sshd_macs_openssh_conf_crypto_policy",
        "xccdf_org.ssgproject.content_rule_harden_sshd_macs_opensshserver_conf_crypto_policy",
        "xccdf_org.ssgproject.content_rule_sysctl_crypto_fips_enabled",
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


def _code_lines(body: str) -> list[str]:
    """The body's executable lines — comments explain the distro facts and
    would otherwise trip the command and module assertions below."""
    return [ln.strip() for ln in body.splitlines() if ln.strip() and not ln.strip().startswith("#")]


@pytest.mark.parametrize("distro", _ALMA)
def test_stig_enables_kernel_fips(minimal_cfg, distro):
    """The two steps fips-finish-install takes, done natively (#84)."""
    body = _post(minimal_cfg, distro, "STIG")
    assert "echo 'add_dracutmodules+=\" fips \"' > /etc/dracut.conf.d/40-fips.conf" in body
    assert "dracut -f --regenerate-all" in body


@pytest.mark.parametrize("distro", _ALMA)
def test_dracut_fips_conf_is_written_before_the_initramfs_is_rebuilt(minimal_cfg, distro):
    """Writing it after `dracut` would leave every initramfs without the module."""
    body = _post(minimal_cfg, distro, "STIG")
    assert body.index("> /etc/dracut.conf.d/40-fips.conf") < body.index("dracut -f")


@pytest.mark.parametrize("distro", _ALMA)
def test_stig_creates_the_system_fips_marker(minimal_cfg, distro):
    """dracut's 01fips module `inst_simple`s this file; no package ships it (#84)."""
    body = _post(minimal_cfg, distro, "STIG")
    assert body.index("> /etc/system-fips") < body.index("dracut -f")


@pytest.mark.parametrize("distro", _ALMA)
def test_the_dracut_conf_names_only_the_module_every_target_has(minimal_cfg, distro):
    """AL8's dracut has no 01fips-crypto-policies; naming it would fail there.

    On AL10 that module enables itself and depends on `fips`, so it is pulled
    in without being named.
    """
    assert not [ln for ln in _code_lines(_post(minimal_cfg, distro, "STIG")) if "fips-cry" in ln]


@pytest.mark.parametrize("distro", _ALMA)
def test_fips_enablement_precedes_the_policy_set(minimal_cfg, distro):
    """`update-crypto-policies --set` stays the last word on the policy (#66).

    AL9 needs FIPS:STIG re-applied after anything that could reset it, so the
    FIPS work goes first and nothing is appended after the set.
    """
    body = _post(minimal_cfg, distro, "STIG")
    assert body.index("dracut -f") < body.index("update-crypto-policies --set")


@pytest.mark.parametrize("distro", _ALMA)
def test_fips_enablement_failure_aborts_the_install(minimal_cfg, distro):
    """A silent fallback would re-create #84: a host claiming FIPS without it."""
    body = _post(minimal_cfg, distro, "STIG")
    assert "exit 1" in body


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
    check = next(ln for ln in body.splitlines() if ln.startswith("[ -f /etc/dracut.conf.d/"))
    assert "40-fips.conf" in check
    assert "exit 1" in check
    assert "ks-gen:" in check


@pytest.mark.parametrize("distro", _ALMA)
def test_stig_establishes_a_non_empty_boot_uuid(minimal_cfg, distro):
    """/boot is always separate; fips=1 without boot= drops to the dracut shell."""
    body = _post(minimal_cfg, distro, "STIG")
    assert "findmnt" in body
    assert "grubby --update-kernel=ALL --args=" in body
    assert "boot=UUID=$" in body or "boot=UUID=${" in body
    assert 'boot=UUID="' not in body  # never a bare, empty value


@pytest.mark.parametrize("distro", _ALMA)
def test_boot_uuid_is_looked_up_in_fstab_as_well_as_the_mount_table(minimal_cfg, distro):
    """In anaconda's chroot the live table keys /boot as /mnt/sysimage/boot."""
    body = _post(minimal_cfg, distro, "STIG")
    lookups = [ln for ln in body.splitlines() if "findmnt" in ln]
    assert len(lookups) == 2
    assert "--fstab" in lookups[0]
    assert "--fstab" not in lookups[1]


@pytest.mark.parametrize("distro", _ALMA)
def test_stig_aborts_when_boot_uuid_cannot_be_resolved(minimal_cfg, distro):
    body = _post(minimal_cfg, distro, "STIG")
    guard = next(ln for ln in body.splitlines() if "cannot read the /boot UUID" in ln)
    assert "exit 1" in guard
    assert "ks-gen:" in guard
    assert body.index("cannot read the /boot UUID") < body.index("grubby --update-kernel")


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
    assert "dracut" not in body
    assert "grubby" not in body
    assert "findmnt" not in body
    assert "system-fips" not in body


# Every external command the block may call, and what ships it on AL8, AL9 AND
# AL10 (checked against the three BaseOS filelists, 2026-08-14):
#   dracut                 -> dracut
#   grubby                 -> grubby
#   findmnt                -> util-linux (AL8) / util-linux-core (AL9, AL10)
#   mkdir                  -> coreutils
#   update-crypto-policies -> crypto-policies-scripts
#   ssh-keygen             -> openssh
_COMMANDS_ON_EVERY_ALMA = {
    "dracut",
    "findmnt",
    "grubby",
    "mkdir",
    "ssh-keygen",
    "update-crypto-policies",
}

# Shipped by crypto-policies-scripts on AL8 and AL9 but by nothing on AL10 —
# calling it aborted a real AL10 install, which is #84's second bug.
_ABSENT_FROM_SOME_ALMA = ("fips-mode-setup", "fips-finish-install")

_SHELL_WORDS = frozenset(
    "[ [[ echo exit test true false if then else elif fi for do done while set printf".split()
)
# Single-quoted spans are blanked first so the prose inside a diagnostic cannot
# look like a command; what is left splits on shell separators, and the first
# bare word of each fragment is the command position.
_QUOTED = re.compile(r"'[^']*'")
_SEPARATOR = re.compile(r"\$\(|[;&|{}()]|\bthen\b|\bdo\b|\belse\b")
_ENV_PREFIX = re.compile(r"^\w+=\S*\s+")
_BARE_WORD = re.compile(r"[A-Za-z_][\w.+-]*$")


def _external_commands(body: str) -> set[str]:
    found: set[str] = set()
    for line in _code_lines(body):
        for fragment in _SEPARATOR.split(_QUOTED.sub("''", line)):
            fragment = _ENV_PREFIX.sub("", fragment.strip())
            word = fragment.split(maxsplit=1)[0] if fragment else ""
            if _BARE_WORD.match(word):
                found.add(word)
    return found - _SHELL_WORDS


@pytest.mark.parametrize("distro", _ALMA)
@pytest.mark.parametrize("policy", ["STIG", "MODERN", "FUTURE"])
def test_emits_no_command_a_target_distro_lacks(minimal_cfg, distro, policy):
    """#84: the block must only call commands all three alma targets ship.

    A command the extractor cannot see would slip through, which is what the
    next test guards; any new *visible* one has to be verified against the
    three BaseOS filelists and added to the set above deliberately.
    """
    code = "\n".join(_code_lines(_post(minimal_cfg, distro, policy)))
    assert _external_commands(code) <= _COMMANDS_ON_EVERY_ALMA
    for absent in _ABSENT_FROM_SOME_ALMA:
        assert absent not in code


@pytest.mark.parametrize("distro", _ALMA)
def test_the_command_extractor_sees_the_commands_that_are_there(minimal_cfg, distro):
    """Guards the test above: a silently blind extractor would assert nothing."""
    found = _external_commands(_post(minimal_cfg, distro, "STIG"))
    assert found == _COMMANDS_ON_EVERY_ALMA


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
    assert ("/etc/dracut.conf.d/40-fips.conf" in rule.emit_post(cfg)) is cfg.kernel_fips


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
