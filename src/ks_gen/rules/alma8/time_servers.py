"""alma8 time_servers — re-exports the alma9 implementation.

chrony is the default time daemon on both releases. /etc/chrony.conf
syntax is the same. The makestep / server directives haven't drifted.
"""

from __future__ import annotations

from ks_gen.rules.alma9.time_servers import RULE

__all__ = ["RULE"]
