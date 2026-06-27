"""alma8 unattended_updates — re-exports the alma9 implementation.

`dnf-automatic` is the standard tool on both RHEL 8 and 9. The
unit file (`dnf-automatic.timer`), drop-in slot, conf format, and
the `needs-restarting -r`-driven reboot decision are unchanged.
"""

from __future__ import annotations

from ks_gen.rules.alma9.unattended_updates import RULE

__all__ = ["RULE"]
