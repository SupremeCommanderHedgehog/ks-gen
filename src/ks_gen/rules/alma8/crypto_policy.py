"""alma8 crypto_policy — re-exports the alma9 implementation.

`update-crypto-policies` shipped in RHEL 8.0 (the original delivery
vehicle) and works the same way on AL8 and AL9. The underlying openssl
differs (1.1.1 on AL8, 3.0 on AL9), but the rule's operator-visible
effect — flipping the system crypto policy — is identical. Ed25519
host-key generation (`ssh-keygen -t ed25519`) works on both.

If the audit-story PR surfaces an alma9-vs-alma8 divergence in
specific openssl.cnf or sshd_config drop-in path, this re-export
becomes a real implementation at that time.
"""

from __future__ import annotations

from ks_gen.rules.alma9.crypto_policy import RULE

__all__ = ["RULE"]
