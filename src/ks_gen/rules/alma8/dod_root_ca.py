"""alma8 dod_root_ca — re-exports the alma9 implementation.

Scaffolding-only rule: applies = not install (civilian default). emit_post
is empty in both alma9 and alma8. The meaningful work (emit_tailoring
disable of the SSG install_DoD_intermediate_certificates rule + paired
exception_entry) is deferred to the audit-story PR.
"""

from __future__ import annotations

from ks_gen.rules.alma9.dod_root_ca import RULE

__all__ = ["RULE"]
