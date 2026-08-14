from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import crypto_policy as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_PREFIX = "xccdf_org.ssgproject.content_rule_"
# The XCCDF Value the stig profile refines to FIPS:STIG. Retuning it to the
# operator's policy keeps configure_crypto_policy running *and passing*,
# which beats disabling it (#61).
_VAR_CRYPTO_POLICY = "xccdf_org.ssgproject.content_value_var_system_crypto_policy"

# Stig-selected on AL9 and unsatisfiable off FIPS. The four harden_sshd_* rules
# each assert a FIPS-only algorithm list in the crypto-policies back-end files
# that update-crypto-policies rewrites under MODERN/FUTURE;
# sysctl_crypto_fips_enabled wants crypto.fips_enabled=1, which only a fips=1
# boot provides; fips_crypto_subpolicy requires /etc/crypto-policies/config to
# match ^FIPS$|^FIPS:(OSPP|NO-SHA1|NO-CAMELLIA|ECDHE-ONLY|STIG)$, which DEFAULT
# and FUTURE cannot (#67).
#
# ssg-almalinux9 0.1.81 dropped enable_fips_mode and enable_dracut_fips_module
# from the stig profile, so both left this list — disabling an unselected rule
# is inert, which is the #61 bug (#90).
#
# alma10 imports this list and extends it. alma8's set is genuinely different
# and lives in its own module. Every ID is confirmed selected *and*
# FIPS-dependent against the shipped datastreams — see
# docs/audit-story/<distro>-fips-candidates.txt and the classification in
# tests/test_fips_dependent_rules.py.
_TAILORED_WHEN_NOT_STIG = [
    f"{_PREFIX}fips_crypto_subpolicy",
    f"{_PREFIX}harden_sshd_ciphers_openssh_conf_crypto_policy",
    f"{_PREFIX}harden_sshd_ciphers_opensshserver_conf_crypto_policy",
    f"{_PREFIX}harden_sshd_macs_openssh_conf_crypto_policy",
    f"{_PREFIX}harden_sshd_macs_opensshserver_conf_crypto_policy",
    f"{_PREFIX}sysctl_crypto_fips_enabled",
]

# What `update-crypto-policies --set` must be given for each ks-gen policy.
# STIG is per-distro (#66): a distro whose stig profile refines
# var_system_crypto_policy to FIPS:STIG must be given FIPS:STIG, or
# configure_crypto_policy fails forever with no expected-failure entry — and
# vice versa. Upstream owns these values and moves them: AL8 was plain FIPS
# through ssg 0.1.74 and switched to FIPS:STIG in 0.1.81, which is #90.
# Each value is checked against the shipped datastream by
# tests/test_stig_crypto_policy_value.py.
_STIG_POLICY_BY_DISTRO = {"alma8": "FIPS:STIG", "alma9": "FIPS:STIG", "alma10": "FIPS"}
_NON_STIG_POLICY = {"MODERN": "DEFAULT", "FUTURE": "FUTURE"}


def _policy_target(cfg: HostConfig) -> str:
    """The crypto-policies name for this host's chosen policy.

    Indexed, not `.get(..., "FIPS")`: a new RHEL-family distro whose profile
    refines to `FIPS:<sub>` would silently inherit plain FIPS and reproduce
    #66. A KeyError at generation time is the correct failure.
    """
    policy = cfg.crypto.policy.value
    if policy == "STIG":
        return _STIG_POLICY_BY_DISTRO[cfg.distro]
    return _NON_STIG_POLICY[policy]


# The long lines of the kernel-FIPS %post block, named rather than split inside
# the list literal: implicit concatenation there reads as a missing comma, which
# is both a CodeQL finding and a real hazard in a list of shell commands.
_ERR_NO_DRACUT_CONF = (
    "ks-gen: /etc/dracut.conf.d/40-fips.conf is missing, so no initramfs "
    "would carry the FIPS module (#84)"
)
_ERR_NO_BOOT_UUID = (
    "ks-gen: cannot read the /boot UUID; refusing to ship fips=1 with no boot=UUID= (#84)"
)
_ERR_NO_FIPS_KARG = (
    "ks-gen: no fips=1 in the installed kernel args; the host would boot without FIPS (#84)"
)
_ERR_NO_BOOT_KARG = (
    "ks-gen: no boot=UUID= in the installed kernel args; a FIPS boot would drop "
    "to the dracut emergency shell (#84)"
)
_C_FIPS_CRYPTO_POLICIES = (
    "# AL10's fips-crypto-policies module is pulled in by its own dracut "
    "dependency; naming it here would break AL8, which has no such module"
)
_C_REGENERATE_ALL = (
    "# --regenerate-all: `dracut -f` alone targets uname -r, which inside "
    "anaconda's chroot is the installer's kernel"
)
_C_SEPARATE_BOOT = (
    "# /boot is always separate here, and fips=1 without a matching boot= leaves "
    "dracut unable to find /boot/.vmlinuz-*.hmac"
)
_C_FSTAB_FIRST = (
    "# --fstab first: in the chroot the live mount table keys /boot as "
    "/mnt/sysimage/boot, so only the fstab lookup resolves"
)
_FINDMNT_LIVE_FALLBACK = (
    '[ -n "$ks_boot_uuid" ] || ks_boot_uuid="$(findmnt -f -t noautofs -no UUID '
    '--mountpoint /boot || true)"'
)

_EXCEPTION_REASON = (
    "{policy} accepts loss of FIPS 140-3 certification in exchange for "
    "Curve25519 / Ed25519 / ChaCha20-Poly1305 support. The system crypto "
    "policy variable is retuned to {target} so configure_crypto_policy still "
    "evaluates against the chosen policy instead of being suppressed."
)


def _emit_tailoring(cfg: HostConfig, disabled: list[str]) -> list[TailoringOp]:
    """Shared tailoring for the RHEL-family crypto_policy rules.

    Module-level so the alma8/alma10 siblings reuse one implementation; only
    the disabled-ID list differs between them.
    """
    policy = cfg.crypto.policy.value
    if policy == "STIG":
        return []
    ops = [TailoringOp(rule_id=r, action="disable") for r in disabled]
    ops.append(
        TailoringOp(
            rule_id=_VAR_CRYPTO_POLICY,
            action="set_value",
            value=_policy_target(cfg),
        )
    )
    return ops


def _exception_entry(cfg: HostConfig, disabled: list[str]) -> ExceptionEntry | None:
    """Shared exception entry; mirrors _emit_tailoring's disabled set."""
    policy = cfg.crypto.policy.value
    if policy == "STIG":
        return None
    return ExceptionEntry(
        rule_id=meta.ID,
        summary=f"{policy} crypto policy",
        stig_rules_disabled=list(disabled),
        reason=_EXCEPTION_REASON.format(policy=policy, target=_policy_target(cfg)),
    )


def _emit_post(cfg: HostConfig) -> str:
    """Render the %post body for the crypto policy.

    Module-level so the alma8 and alma10 siblings can reuse it — the shell is
    the same on all three (`update-crypto-policies` shipped in RHEL 8.0); only
    the policy target and the disabled-rule list differ per distro.
    """
    policy = cfg.crypto.policy.value
    target = _policy_target(cfg)
    lines = [f"# Apply system-wide crypto policy: {policy} ({target})"]

    if cfg.kernel_fips:
        # Same predicate as the fips=1 bootloader arg, so the two cannot disagree.
        # Done natively instead of via fips-mode-setup, which AlmaLinux 10 does
        # not ship at all — that aborted a real AL10 install (#84). These are
        # the steps fips-finish-install/fips-mode-setup take, using only
        # commands all three alma targets have. It must all precede the
        # update-crypto-policies call below, which re-applies the policy (#66).
        lines += [
            "# Kernel FIPS mode: dracut module + fips=1; takes effect at first boot",
            "# Native equivalent of fips-mode-setup, which AL10 does not ship (#84)",
            "mkdir -p /etc/dracut.conf.d",
            "# dracut's fips module installs this file into the initramfs; no package ships it",
            "echo '# FIPS module installation complete' > /etc/system-fips",
            "echo 'add_dracutmodules+=\" fips \"' > /etc/dracut.conf.d/40-fips.conf",
            _C_FIPS_CRYPTO_POLICIES,
            f"[ -f /etc/dracut.conf.d/40-fips.conf ] || {{ echo '{_ERR_NO_DRACUT_CONF}'"
            f" >&2; exit 1; }}",
            _C_REGENERATE_ALL,
            "dracut -f --regenerate-all",
            _C_SEPARATE_BOOT,
            _C_FSTAB_FIRST,
            'ks_boot_uuid="$(findmnt -f -t noautofs -no UUID --fstab --mountpoint /boot || true)"',
            _FINDMNT_LIVE_FALLBACK,
            f"[ -n \"$ks_boot_uuid\" ] || {{ echo '{_ERR_NO_BOOT_UUID}' >&2; exit 1; }}",
            'grubby --update-kernel=ALL --args="fips=1 boot=UUID=$ks_boot_uuid"',
            'ks_kargs="$(grubby --info=ALL)"',
            f"[[ \"$ks_kargs\" == *fips=1* ]] || {{ echo '{_ERR_NO_FIPS_KARG}' >&2; exit 1; }}",
            f'[[ "$ks_kargs" == *boot=UUID=[0-9a-fA-F]* ]] || {{ echo'
            f" '{_ERR_NO_BOOT_KARG}' >&2; exit 1; }}",
        ]

    base, _, submodule = target.partition(":")
    if submodule:
        # A sub-policy needs its .pmod module present. The OS does not ship
        # one — SSG's own fips_custom_stig_sub_policy remediation writes it
        # earlier in this install. This block runs under `set -e` with
        # --erroronfail, so an absent module would abort the install; degrade
        # to the base policy and say so instead (#66).
        # Both search paths: SSG's remediation writes the module under /etc,
        # but update-crypto-policies also resolves the stock modules shipped
        # under /usr/share, so testing only /etc would fall back needlessly if
        # a future crypto-policies package ships this one.
        etc_pmod = f"/etc/crypto-policies/policies/modules/{submodule}.pmod"
        usr_pmod = f"/usr/share/crypto-policies/policies/modules/{submodule}.pmod"
        lines += [
            f"if [ -f {etc_pmod} ] || [ -f {usr_pmod} ]; then",
            f"  update-crypto-policies --set {target}",
            "else",
            f"  echo 'ks-gen: {submodule}.pmod not found in /etc or /usr/share;"
            f" oscap did not apply the sub-policy, falling back to {base}' >&2",
            f"  update-crypto-policies --set {base}",
            "fi",
        ]
    else:
        lines.append(f"update-crypto-policies --set {target}")

    if policy != "STIG":
        lines.append("# Generate any missing host keys (incl. Ed25519, not produced under FIPS)")
        lines.append("ssh-keygen -A")
    else:
        # ssh_config_apply validates its drop-in with `sshd -t`, which exits
        # non-zero when no host key exists at all — that aborted every STIG
        # install (#72). Generate the FIPS-approved types rather than
        # `ssh-keygen -A`, guarded on the file so nothing existing is
        # clobbered. Note the installed host ends up with an Ed25519 key
        # anyway, created by sshd-keygen.service at first boot; sshd does not
        # offer it under a FIPS policy, so this only controls what ks-gen
        # itself puts there.
        lines.append("# FIPS-approved host keys; sshd will not offer Ed25519 under FIPS")
        for keytype, bits in (("rsa", 3072), ("ecdsa", 384)):
            key = f"/etc/ssh/ssh_host_{keytype}_key"
            lines.append(f"[ -f {key} ] || ssh-keygen -q -t {keytype} -b {bits} -f {key} -N ''")
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=lambda: list(_TAILORED_WHEN_NOT_STIG))

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return _emit_tailoring(cfg, _TAILORED_WHEN_NOT_STIG)

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit_post(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return _exception_entry(cfg, _TAILORED_WHEN_NOT_STIG)


RULE: Rule = cast(Rule, _Rule())
