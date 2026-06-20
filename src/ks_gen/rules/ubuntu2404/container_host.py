"""ubuntu2404 container_host rule (minimal port of alma9 sibling).

Drops the Ubuntu helper script (create-rootless-user-ubuntu.sh) at
/root for operator post-install use, writes /etc/containers/storage.conf
pinning rootless graphroot to /srv/containers/$USER/storage, and
provisions each configured container user via the helper (linger on,
Quadlet scaffold off at kickstart-time) with authorized_keys.

Differences from alma9:
  - Loads the Ubuntu helper script (no semanage / restorecon calls).
  - Drops the per-user `restorecon -R /home/<user>/.ssh` line.
  - Package list: podman, crun, slirp4netns, fuse-overlayfs.
    Ubuntu's `podman` package pulls `netavark`, `containers-storage`,
    and other transitive deps that alma9 names separately
    (containers-common, podman-plugins). `policycoreutils-python-utils`
    is dropped — Ubuntu uses AppArmor, not SELinux.

Known limitation: without a custom AppArmor profile extension for
/srv/containers, podman's stock `containers-default-X.Y.Z` profile
may DENY access to the per-user storage tree. Operators can
`--security-opt apparmor=unconfined` per-container as workaround
until the AppArmor follow-up PR lands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib.resources import files
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import container_host as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


# Loaded once at import time; embedded verbatim in every emit_post emission.
_SCRIPT = (
    files("ks_gen.assets").joinpath("create-rootless-user-ubuntu.sh").read_text(encoding="utf-8")
)


def _emit(cfg: HostConfig) -> str:
    parts: list[str] = []

    # Drop the helper script to /root for operator post-install use
    parts.append("# Install the rootless-container-user helper at /root for post-install use")
    parts.append("cat > /root/create-rootless-user.sh <<'__KS_GEN_EOF__'")
    parts.append(_SCRIPT.rstrip())
    parts.append("__KS_GEN_EOF__")
    parts.append("chown root:root /root/create-rootless-user.sh")
    parts.append("chmod 0550 /root/create-rootless-user.sh")
    parts.append("")

    # System-wide storage.conf: pin rootless graphroot under the mirror
    parts.append(
        "# System-wide storage.conf -- pins rootless graphroot to the /srv/containers mirror"
    )
    parts.append("install -d -m 0755 /etc/containers")
    parts.append("cat > /etc/containers/storage.conf <<'__KS_GEN_EOF__'")
    parts.append("[storage]")
    parts.append('driver = "overlay"')
    parts.append('rootless_storage_path = "/srv/containers/$USER/storage"')
    parts.append("__KS_GEN_EOF__")
    parts.append("chmod 0644 /etc/containers/storage.conf")

    # Provision each configured container user via the same script the
    # operator will use post-install. -l (linger) always on; -q (Quadlet
    # scaffold) intentionally off for kickstart-time creation.
    for u in cfg.containers.users:
        gecos = u.gecos or u.name
        parts.append("")
        parts.append(f"# Provision container user: {u.name}")
        parts.append(f'/root/create-rootless-user.sh -l -c "{gecos}" {u.name}')
        parts.append(f"install -d -m 0700 -o {u.name} -g {u.name} /home/{u.name}/.ssh")
        parts.append(f"cat > /home/{u.name}/.ssh/authorized_keys <<'__KS_GEN_EOF__'")
        parts.extend(u.authorized_keys)
        parts.append("__KS_GEN_EOF__")
        parts.append(f"chown {u.name}:{u.name} /home/{u.name}/.ssh/authorized_keys")
        parts.append(f"chmod 0600 /home/{u.name}/.ssh/authorized_keys")
        # No `restorecon -R /home/{user}/.ssh` — Ubuntu has no SELinux.

    return "\n".join(parts) + "\n"


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return cfg.containers.enabled

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        # Ubuntu's `podman` package transitively pulls netavark,
        # containers-storage, etc. — no need to declare them. Drops
        # alma9's containers-common, podman-plugins (RHEL packaging
        # only) and policycoreutils-python-utils (SELinux only).
        return [
            "podman",
            "crun",
            "slirp4netns",
            "fuse-overlayfs",
        ]

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return None


RULE: Rule = cast(Rule, _Rule())
