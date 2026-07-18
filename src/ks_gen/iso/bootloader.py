from __future__ import annotations

import re

from ks_gen.iso._menu import (
    GRUB_UNATTENDED_ENTRY,
    IDEMPOTENCY_MARKER,
    ISOLINUX_UNATTENDED_ENTRY,
)


class BootloaderRewriteError(ValueError):
    pass


def _inst_repo_arg(volid: str, network_install: bool) -> str:
    """The `inst.repo=hd:LABEL=<volid>` boot arg, or "" for a network install
    (which sources packages from the kickstart's url/repo, not the ISO)."""
    return "" if network_install else f" inst.repo=hd:LABEL={volid}"


def rewrite_isolinux(
    text: str, *, volid: str, timeout: int = 5, network_install: bool = False
) -> str:
    if IDEMPOTENCY_MARKER in text:
        return text

    if not re.search(r"^label\s+\S+", text, flags=re.MULTILINE):
        raise BootloaderRewriteError("no `label` keyword found in isolinux.cfg")

    text = re.sub(r"^[ \t]*menu\s+default\s*$\r?\n?", "", text, flags=re.MULTILINE)

    timeout_units = timeout * 10
    text, n = re.subn(
        r"^timeout\s+\d+\s*$",
        f"timeout {timeout_units}",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if n == 0:
        text = f"timeout {timeout_units}\n" + text

    match = re.search(r"^label\s+\S+", text, flags=re.MULTILINE)
    assert match is not None  # verified above; edits only delete `menu default`
    repo = _inst_repo_arg(volid, network_install)
    entry = ISOLINUX_UNATTENDED_ENTRY.format(marker=IDEMPOTENCY_MARKER, volid=volid, repo=repo)
    return text[: match.start()] + entry + "\n" + text[match.start() :]


def rewrite_grub(text: str, *, volid: str, timeout: int = 5, network_install: bool = False) -> str:
    if IDEMPOTENCY_MARKER in text:
        return text

    if not re.search(r"^menuentry\s+", text, flags=re.MULTILINE):
        raise BootloaderRewriteError("no `menuentry` keyword found in grub.cfg")

    text, n = re.subn(
        r"^set\s+timeout=\d+\s*$",
        f"set timeout={timeout}",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if n == 0:
        text = f"set timeout={timeout}\n" + text

    text, n = re.subn(
        r"^set\s+default=.*$",
        'set default="0"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if n == 0:
        text = 'set default="0"\n' + text

    match = re.search(r"^menuentry\s+", text, flags=re.MULTILINE)
    assert match is not None  # verified above
    repo = _inst_repo_arg(volid, network_install)
    entry = GRUB_UNATTENDED_ENTRY.format(marker=IDEMPOTENCY_MARKER, volid=volid, repo=repo)
    return text[: match.start()] + entry + "\n" + text[match.start() :]
