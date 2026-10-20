"""alma10 rngd_entropy — re-exports the alma9 implementation.

AL10's stig profile selects none of sshd_use_strong_rng,
package_rng-tools_installed or service_rngd_enabled, and its kernel's
/dev/random does not block once the CRNG is initialised, so the rule never
applies here either (#118).

If AL10 ever diverges here, replace this re-export with a real
implementation and add the rule to _DIVERGENT in tests/test_registry.py.
"""

from __future__ import annotations

from ks_gen.rules.alma9.rngd_entropy import RULE

__all__ = ["RULE"]
