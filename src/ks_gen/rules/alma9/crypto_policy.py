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

# Rules that force FIPS on, disabled when the operator did not ask for FIPS.
#
# The four harden_sshd_* rules each assert a FIPS-only algorithm list in the
# crypto-policies back-end files that update-crypto-policies rewrites under
# MODERN/FUTURE; sysctl_crypto_fips_enabled wants crypto.fips_enabled=1, which
# only a fips=1 boot provides; fips_crypto_subpolicy requires
# /etc/crypto-policies/config to match
# ^FIPS$|^FIPS:(OSPP|NO-SHA1|NO-CAMELLIA|ECDHE-ONLY|STIG)$, which DEFAULT and
# FUTURE cannot; enable_fips_mode and enable_dracut_fips_module remediate via
# `fips-mode-setup --enable`, and fips_custom_stig_sub_policy's remediation runs
# `update-crypto-policies --set FIPS:STIG` outright (#67).
#
# This is the UNION over every SSG release a supported install can present, not
# the set one pinned release selects (#90). oscap remediates against whatever
# content the host has: media if the install is offline, repo content if the
# %post upgrade succeeded. Pinning to one release left AL8 media installs
# unprotected, because ssg-almalinux8 0.1.72 — what the 8.10 DVD ships — selects
# rules 0.1.81 dropped. An ID the running content does not select is inert;
# one it does select and cannot pass off FIPS is a live regression, so the union
# is the safe direction. docs/audit-story/SSG-VERSIONS.md records the floors.
# Present on all three alma targets and selected by at least one supported
# release of each.
_FIPS_ONLY_COMMON = [
    f"{_PREFIX}enable_fips_mode",
    f"{_PREFIX}fips_crypto_subpolicy",
    f"{_PREFIX}harden_sshd_ciphers_openssh_conf_crypto_policy",
    f"{_PREFIX}harden_sshd_ciphers_opensshserver_conf_crypto_policy",
    f"{_PREFIX}harden_sshd_macs_openssh_conf_crypto_policy",
    f"{_PREFIX}harden_sshd_macs_opensshserver_conf_crypto_policy",
    f"{_PREFIX}sysctl_crypto_fips_enabled",
]

# AL8 and AL9 add this one; the AL10 datastream does not define it, so alma10
# composes its own list from _FIPS_ONLY_COMMON instead of extending this.
#
# fips_custom_stig_sub_policy is deliberately NOT here despite being
# stig-selected on both and remediating to FIPS:STIG: it checks the STIG.pmod
# its own remediation writes, so it passes under any policy, and the non-STIG
# branch below re-applies DEFAULT/FUTURE afterwards. Disabling it would be
# inert. See _PASSES_ANYWAY in tests/test_fips_dependent_rules.py.
_TAILORED_WHEN_NOT_STIG = [
    *_FIPS_ONLY_COMMON,
    f"{_PREFIX}enable_dracut_fips_module",
]

# Only the non-STIG policies are named here. Under STIG the target is not
# ks-gen's to choose: oscap's own configure_crypto_policy remediation applies
# whatever the installed content's stig profile refines
# var_system_crypto_policy to, so it is right for that content by construction.
# A hardcoded per-distro map was #66 and then #90 — upstream moved AL8 from
# FIPS to FIPS:STIG and every AL8 STIG host failed until a real install found it.
_NON_STIG_POLICY = {"MODERN": "DEFAULT", "FUTURE": "FUTURE"}


def _policy_target(cfg: HostConfig) -> str:
    """The crypto-policies name ks-gen applies for a non-STIG policy.

    Indexed, not `.get(...)`: a new policy added to the enum without a target
    here must fail at generation time rather than silently pick one.
    """
    return _NON_STIG_POLICY[cfg.crypto.policy.value]


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

_C_POLICY_FROM_OSCAP = (
    "# Crypto policy comes from oscap's configure_crypto_policy remediation, "
    "which uses the installed content's own refine-value (#90)"
)
# A printf format, not an echo string: the policy has to be interpolated, and a
# double-quoted echo carrying this much prose would end the quoted span at the
# first inner quote and run the rest of the sentence as a command.
_ERR_POLICY_NOT_FIPS = (
    "ks-gen: crypto policy is %s, not a FIPS policy. oscap did not apply one, "
    "so this host would not be FIPS (#90)\\n"
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
    the disabled-rule list differs per distro.
    """
    policy = cfg.crypto.policy.value
    if policy == "STIG":
        # Same shape as the non-STIG header because tests/install-regression
        # parses the parenthesised value out of it. A glob, not a literal:
        # which FIPS target lands here belongs to the installed content (#90).
        lines = [f"# Apply system-wide crypto policy: {policy} (FIPS*)"]
    else:
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

    if policy == "STIG":
        # Deliberately not `update-crypto-policies --set <hardcoded>`. This
        # block runs after the oscap %post, so anything set here overrides the
        # remediation — which is how a stale hardcoded value silently won and
        # left configure_crypto_policy failing forever (#66, #90). Verify
        # instead: FIPS or any FIPS:<sub> is correct, whichever the installed
        # content asked for.
        lines += [
            _C_POLICY_FROM_OSCAP,
            'ks_policy="$(update-crypto-policies --show)"',
            # %%:* strips any sub-policy, so FIPS and FIPS:STIG both pass and
            # ks-gen never has to know which one this content asked for.
            f"[ \"${{ks_policy%%:*}}\" = FIPS ] || {{ printf '{_ERR_POLICY_NOT_FIPS}'"
            ' "$ks_policy" >&2; exit 1; }',
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
