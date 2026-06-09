"""Disk group prompts.

Covers preset choice (stig_server / minimal), wipe confirm, and LUKS
preset (none / partial). Tang and custom disk.layout are deferred to
hand-edit per the design spec.
"""

from __future__ import annotations

from typing import Any

from ks_gen.wizard import _prompts


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
    print(
        "(LUKS tang preset is hand-edit only — needs URLs, thumbprints, "
        "and threshold. See MANUAL.md §5.1.)"
    )
    if luks_preset == "none":
        payload["luks"] = {"preset": "none"}
        return payload

    # luks_preset == "partial" — handled by the partial helpers added in
    # Task 7 / Task 8. Placeholder raises until those land.
    raise NotImplementedError("LUKS partial path not yet implemented")
