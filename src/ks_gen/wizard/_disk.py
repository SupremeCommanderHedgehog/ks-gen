"""Disk group prompts.

Covers preset choice (stig_server / minimal), wipe confirm, LUKS preset
(none / partial), and an opt-in loop for secondary data_disks. Tang and
custom disk.layout are deferred to hand-edit per the design spec.
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


def _ask_data_disk() -> dict[str, Any]:
    """Prompt for one data disk. Returns a DataDisk-shaped fragment."""
    target = _prompts.ask_text("Data disk target (by-id or short name):")
    if not target:
        raise WizardError("data disk target is empty")
    mount = _prompts.ask_text("Mount point:")
    if not mount:
        raise WizardError("data disk mount is empty")
    fstype = _prompts.select_one("Filesystem:", ["xfs", "ext4"])
    fsoptions = _prompts.ask_text("fsoptions:", default="nodev,nosuid")
    wipe = _prompts.ask_confirm("Wipe disk on install?", default=True)

    fragment: dict[str, Any] = {
        "target": target,
        "mount": mount,
        "fstype": fstype,
        "fsoptions": fsoptions,
        "wipe": wipe,
    }
    if wipe:
        return fragment

    # wipe=False -> ask how to identify the existing partition
    id_kind = _prompts.select_one("Identify existing partition by:", ["partition", "uuid", "label"])
    if id_kind == "partition":
        raw = _prompts.ask_text("Partition number:", default="1")
        try:
            fragment["partition"] = int(raw)
        except ValueError as e:
            raise WizardError(f"partition number must be an integer (got {raw!r})") from e
    elif id_kind == "uuid":
        uuid = _prompts.ask_text("Partition UUID:")
        if not uuid:
            raise WizardError("partition UUID is empty")
        fragment["partition_uuid"] = uuid
    else:  # label
        label = _prompts.ask_text("Partition LABEL:")
        if not label:
            raise WizardError("partition LABEL is empty")
        fragment["partition_label"] = label
    return fragment


def _ask_data_disks_loop() -> list[dict[str, Any]]:
    """Ask 'Add a data disk?' / collect / repeat. Empty list is valid."""
    collected: list[dict[str, Any]] = []
    add = _prompts.ask_confirm("Add a data disk?", default=False)
    while add:
        collected.append(_ask_data_disk())
        add = _prompts.ask_confirm("Add another data disk?", default=False)
    return collected


def prompts() -> dict[str, Any]:
    """Run the disk-group prompts. Returns a HostConfig.disk fragment."""
    preset = _prompts.select_one("Disk preset:", ["stig_server", "minimal"])
    wipe = _prompts.ask_confirm("Wipe disk on install?", default=True)

    payload: dict[str, Any] = {"preset": preset, "wipe": wipe}

    if preset == "minimal":
        # _minimal_preset_rejects_luks would reject any LUKS != none, and
        # _minimal_preset_rejects_data_disks would reject data_disks too.
        # Skip both prompts entirely.
        print("minimal preset has no LVM PV; skipping LUKS and data_disks prompts.")
        return payload

    luks_preset = _prompts.select_one("LUKS encryption:", ["none", "partial"])
    if luks_preset == "none":
        payload["luks"] = {"preset": "none"}
    else:
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
        else:
            # source == "file"
            path = _prompts.ask_text("Passphrase file path:")
            if not path:
                raise WizardError("passphrase_file path is empty")
            payload["luks"] = {"preset": "partial", "passphrase_file": path}

    # Data disks loop (applies to stig_server and stig_server+layout paths).
    data_disks = _ask_data_disks_loop()
    if data_disks:
        payload["data_disks"] = data_disks
    return payload
