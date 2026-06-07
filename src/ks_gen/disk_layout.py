from __future__ import annotations


def size_to_mb(size_str: str) -> int:
    """Convert size string like '15G' or '500M' to MB integer.

    Used for /boot and /boot/efi where 'recommended' isn't valid.
    """
    n, unit = int(size_str[:-1]), size_str[-1]
    return n * {"M": 1, "G": 1024}[unit]
