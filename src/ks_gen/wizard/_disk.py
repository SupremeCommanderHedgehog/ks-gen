"""Disk group prompts.

Covers preset choice (stig_server / minimal), wipe confirm, and LUKS
preset (none / partial). Tang and custom disk.layout are deferred to
hand-edit per the design spec.
"""

from __future__ import annotations

from typing import Any

from ks_gen.wizard import _prompts
from ks_gen.wizard._core import WizardError

_INLINE_RETRY_LIMIT = 3


def _ask_inline_passphrase() -> str:
    """Inline passphrase + confirm loop. Up to 3 mismatch retries."""
    for _ in range(_INLINE_RETRY_LIMIT):
        first = _prompts.ask_password("Passphrase:")
        second = _prompts.ask_password("Confirm passphrase:")
        if first.strip() == "" and second.strip() == "":
            raise WizardError("passphrase is empty")
        if first == second:
            return first
        print("passphrase mismatch; please try again")
    raise WizardError(f"passphrase confirmation mismatch after {_INLINE_RETRY_LIMIT} attempts")


def prompts() -> dict[str, Any]:
    """Run the disk-group prompts. Returns a HostConfig.disk fragment."""
    preset = _prompts.select_one("Disk preset:", ["stig_server", "minimal"])
    wipe = _prompts.ask_confirm("Wipe disk on install?", default=True)

    payload: dict[str, Any] = {"preset": preset, "wipe": wipe}

    if preset == "minimal":
        # _minimal_preset_rejects_luks would reject any LUKS != none.
        # Skip the prompt entirely.
        print("minimal preset has no LVM PV; skipping LUKS prompt.")
        return payload

    luks_preset = _prompts.select_one("LUKS encryption:", ["none", "partial"])
    if luks_preset == "none":
        payload["luks"] = {"preset": "none"}
        return payload

    # luks_preset == "partial"
    print(
        "(LUKS tang preset is hand-edit only — needs URLs, thumbprints, "
        "and threshold. See MANUAL.md §5.1.)"
    )
    print(
        "NOTE: inline passphrase will be stored in plaintext in host.yaml; "
        "for production use the 'file' option."
    )
    source = _prompts.select_one("Passphrase source:", ["inline", "file"])
    if source == "inline":
        payload["luks"] = {
            "preset": "partial",
            "passphrase": _ask_inline_passphrase(),
        }
        return payload

    # source == "file"
    path = _prompts.ask_text("Passphrase file path:")
    if not path:
        raise WizardError("passphrase_file path is empty")
    payload["luks"] = {"preset": "partial", "passphrase_file": path}
    return payload
