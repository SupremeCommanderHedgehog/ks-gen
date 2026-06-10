from __future__ import annotations

from ks_gen.config import DEFAULT_FSOPTIONS, DEFAULT_LV_SIZES, DiskLvDef


def size_to_mb(size_str: str) -> int:
    """Convert size string like '15G', '500M', or '2T' to MB integer.

    Used by /boot and /boot/efi (which only allow M/G via DiskBootPart /
    DiskEfiPart) and by effective_size_mb after the 'recommended'
    short-circuit. The 'recommended' literal is NOT valid here — callers
    must handle it before calling.
    """
    n, unit = int(size_str[:-1]), size_str[-1]
    return n * {"M": 1, "G": 1024, "T": 1024 * 1024}[unit]


def effective_size_mb(lv: DiskLvDef) -> int | str:
    """Returns MB integer, or the string 'recommended' for swap-style sizing.

    Falls back to DEFAULT_LV_SIZES when lv.size is None.
    """
    s = lv.size if lv.size is not None else DEFAULT_LV_SIZES[lv.mount]
    if s == "recommended":
        return "recommended"
    return size_to_mb(s)


def effective_fsoptions(lv: DiskLvDef) -> str | None:
    """Returns explicit fsoptions if set; otherwise the STIG-baseline
    default for the mountpoint; otherwise None (for / and swap).
    """
    if lv.fsoptions is not None:
        return lv.fsoptions
    if lv.mount is None:
        return None
    return DEFAULT_FSOPTIONS.get(lv.mount)
