"""skel_init_files — tighten /etc/skel's init files to the STIG's 0740 (#131).

AlmaLinux's /etc/skel ships .bashrc, .bash_profile and .bash_logout at 0644,
and `useradd --create-home` copies them into every new home as they are. The
stig init-file rule (file_permission_user_init_files_root on AL8/AL9,
file_permission_user_init_files on AL10) requires every user's init files to
be 0740 or stricter, so each such home fails it. oscap's remediation fixes
the homes that exist when it runs, but not skel, so:

- users created later with plain `useradd -m` fail the rule;
- so does the admin user when admin_user_and_keys' %post `useradd` fallback
  creates it, because that %post runs after oscap's.

Fixing skel once fixes both. admin_user_and_keys and container_host depend
on this rule, so this %post runs before either creates a home.
create-rootless-user.sh still tightens per user, to repair accounts that
already exist (#49).

The name pattern is the STIG's var_user_initialization_files_regex,
^\\.[\\w\\- ]+$, applied to regular files directly in /etc/skel. Only the
offending bits are stripped: group write/exec, all of other, and
setuid/setgid/sticky, which "0740 or less permissive" excludes too. The same
match is in create-rootless-user.sh and the harness's smoke-check.sh
(loose_init_files); keep the three in step. skel is root's, so root's chmod is safe here,
unlike in a user's own home.

This runs before admin_user_and_keys (which depends on it), whose %post
must not be kept from running: %post is `set -e` with --erroronfail, and no admin means no way in.
So a failure here only warns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import skel_init_files as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp
from ks_gen.ssg_ids import RULE_PREFIX

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

SKEL = "/etc/skel"
_INIT_FILES_ROOT_RULE = f"{RULE_PREFIX}file_permission_user_init_files_root"


@dataclass(frozen=True)
class SkelInitFiles:
    """`stig_rules_affected`: the distro's stig init-file rule."""

    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=lambda: [_INIT_FILES_ROOT_RULE])

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return "\n".join(
            [
                f"# Tighten {SKEL}'s init files to 0740 or stricter, before any home is",
                "# created from it here (STIG var_user_initialization_files_regex) (#131)",
                "# Never fatal: admin_user_and_keys runs after this, and must.",
                f"if [ -d {SKEL} ]; then",
                f"  LC_ALL=C find {SKEL}/ -maxdepth 1 -type f -regextype posix-extended \\",
                "    -regex '.*/\\.[[:alnum:]_ -]+' -perm /7037 \\",
                "    -exec chmod u-s,g-wxs,o-rwxt {} + \\",
                f"    || echo 'ks-gen: warning: could not tighten {SKEL} init files' >&2",
                "fi",
                "",
            ]
        )

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return None


RULE: Rule = cast(Rule, SkelInitFiles())
