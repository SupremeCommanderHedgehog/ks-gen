from __future__ import annotations

from pathlib import Path

from ks_gen.config import DiskLuks, LuksPreset


def resolve_passphrase(luks: DiskLuks) -> str | None:
    """Return the literal LUKS passphrase, or None if preset == NONE.

    Raises FileNotFoundError if passphrase_file is set but missing.
    Raises ValueError if the file is empty after whitespace strip.
    """
    if luks.preset == LuksPreset.NONE:
        return None
    if luks.passphrase is not None:
        return luks.passphrase
    # Validator guarantees passphrase_file is set if passphrase isn't.
    assert luks.passphrase_file is not None
    p = Path(luks.passphrase_file)
    content = p.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"disk.luks.passphrase_file '{p}' is empty after whitespace strip")
    return content


def kickstart_passphrase_quoted(passphrase: str) -> str:
    """Escape and double-quote for kickstart's --passphrase= flag.

    Backslash and double-quote are the only chars needing escape.
    Order matters: escape backslash first, then double-quote.
    """
    escaped = passphrase.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
