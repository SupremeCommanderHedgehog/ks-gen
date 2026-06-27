"""alma8 container_host — re-exports the alma9 implementation.

podman/crun/containers-common are available on RHEL 8.x in the AppStream
repo. /etc/containers/storage.conf, the rootless-storage-path knob, and
the SELinux fcontext equivalence are all the same. policycoreutils-python-utils
provides semanage on both. RHEL 8's podman 4.x is older than RHEL 9's but
the operator-facing rule behavior (script drop + storage.conf + per-user
provisioning) is unchanged.
"""

from __future__ import annotations

from ks_gen.rules.alma9.container_host import RULE

__all__ = ["RULE"]
