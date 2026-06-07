from __future__ import annotations

from ks_gen.config import _DEFAULT_LV_SIZES, DiskLvDef


def size_to_mb(size_str: str) -> int:
    """Convert size string like '15G' or '500M' to MB integer.

    Used for /boot and /boot/efi where 'recommended' isn't valid.
    """
    n, unit = int(size_str[:-1]), size_str[-1]
    return n * {"M": 1, "G": 1024}[unit]


def effective_size_mb(lv: DiskLvDef) -> int | str:
    """Returns MB integer, or the string 'recommended' for swap-style sizing.

    Falls back to _DEFAULT_LV_SIZES when lv.size is None.
    """
    s = lv.size if lv.size is not None else _DEFAULT_LV_SIZES[lv.mount]
    if s == "recommended":
        return "recommended"
    n, unit = int(s[:-1]), s[-1]
    return n * {"M": 1, "G": 1024, "T": 1024 * 1024}[unit]
