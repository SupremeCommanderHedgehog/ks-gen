"""alma10 crypto_policy — re-exports the alma9 implementation.

This was a real divergence when alma9 still disabled
`sshd_use_approved_ciphers` (absent from ssg-almalinux10-ds.xml). #61
replaced that ID on alma9 with the four `harden_sshd_{ciphers,macs}_*` rules,
all of which the AL10 stig profile selects too, so the two distros now emit
identical tailoring.

alma8 still diverges — it additionally selects
`sshd_use_approved_kex_ordered_stig`.
"""

from __future__ import annotations

from ks_gen.rules.alma9.crypto_policy import RULE

__all__ = ["RULE"]
