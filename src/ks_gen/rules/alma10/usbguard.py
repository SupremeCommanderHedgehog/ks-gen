"""alma10 usbguard — re-exports the alma9 implementation.

Verified portable against ssg-almalinux10-ds.xml (scap-security-guide
0.1.81) and AlmaLinux 10 BaseOS/AppStream repodata: every SSG rule ID
this rule references still exists and is selected by the stig profile,
and every package it installs is still packaged for AL10.

If AL10 ever diverges here, replace this re-export with a real
implementation and add the rule to _DIVERGENT in tests/test_registry.py.
"""

from __future__ import annotations

from ks_gen.rules.alma9.usbguard import RULE

__all__ = ["RULE"]
