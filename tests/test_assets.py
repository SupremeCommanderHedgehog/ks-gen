import getpass
import os
import shlex
import shutil
import stat
import subprocess
from importlib.resources import files

import pytest


def test_linger_falls_back_to_marker_file_in_chroot():
    # Regression: `loginctl enable-linger` fails inside anaconda's %post
    # install chroot (no logind/D-Bus). Under the script's `set -e` that
    # non-zero exit aborted the whole %post, leaving a half-installed,
    # unbootable system. The call must be guarded and fall back to writing
    # the linger marker file directly so a first real container install
    # completes. See fix/rootless-linger-chroot.
    script = files("ks_gen.assets").joinpath("create-rootless-user.sh").read_text(encoding="utf-8")
    assert "if ! loginctl enable-linger" in script, (
        "unguarded `loginctl enable-linger` will abort %post in a chroot"
    )
    assert "/var/lib/systemd/linger/" in script, (
        "missing the marker-file fallback for chroot linger"
    )


def test_create_rootless_user_script_is_shipped():
    script = files("ks_gen.assets").joinpath("create-rootless-user.sh").read_text(encoding="utf-8")
    assert script.startswith("#!/usr/bin/env bash")
    assert 'CONTAINERS_ROOT="/srv/containers"' in script
    assert "create-rootless-user.sh" in script  # mentioned in usage banner


def test_create_rootless_user_script_is_executable_text():
    # We embed the script via a heredoc in %post; it must be plain text
    # without any null bytes or BOM that would break the heredoc.
    raw = files("ks_gen.assets").joinpath("create-rootless-user.sh").read_bytes()
    assert b"\x00" not in raw
    assert not raw.startswith(b"\xef\xbb\xbf")  # no UTF-8 BOM


def _stub(bindir, name, body):
    path = bindir / name
    path.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8")
    path.chmod(0o755)


def _gnu_find() -> bool:
    find = shutil.which("find")
    if find is None:
        return False
    proc = subprocess.run(
        [find, ".", "-maxdepth", "0", "-regextype", "posix-extended"], capture_output=True
    )
    return proc.returncode == 0


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
@pytest.mark.skipif(not _gnu_find(), reason="needs GNU find (-regextype), as on AlmaLinux")
@pytest.mark.parametrize("existing", [False, True], ids=["new-user", "existing-user"])
def test_init_files_tightened_to_stig_0740(tmp_path, existing):
    """#49: useradd's /etc/skel dotfiles land at 0644, which fails STIG
    file_permission_user_init_files_root (0740 or stricter, every user)."""
    # The script's find filters on -user, so the account must really exist:
    # provision the user running the test, whose files these are anyway.
    user = getpass.getuser()
    home = tmp_path / "home" / user
    bindir = tmp_path / "bin"
    bindir.mkdir()
    outside = tmp_path / "outside"
    privdrop = tmp_path / "setpriv.args"
    skel = {".bashrc": 0o644, ".bash_profile": 0o664, ".bash_logout": 0o644,
            ".cshrc": 0o777, ".tcshrc": 0o600, ".suidrc": 0o4740}  # fmt: skip
    # The home as useradd leaves it, plus three files that are not init files
    # and must keep their 0644: one a level down, one not a dotfile, and one
    # outside the home that a dotfile symlinks to. chmod follows symlinks, so
    # touching that one would mean the script can be pointed at any file.
    q = shlex.quote
    populate = " && ".join(
        [
            f"mkdir -p {q(f'{home}/.config')}",
            f"touch {q(str(outside))}",
            f"chmod 644 {q(str(outside))}",
        ]
        + [f"touch {q(f'{home}/{n}')} && chmod {m:o} {q(f'{home}/{n}')}" for n, m in skel.items()]
        + [
            f"touch {q(f'{home}/{n}')} && chmod 644 {q(f'{home}/{n}')}"
            for n in (".config/app.conf", "notes.txt")
        ]
        + [f"ln -s {q(str(outside))} {q(f'{home}/.profile')}"]
    )
    # Root-only or host-specific commands, stubbed so the real script runs as
    # the test user. useradd stands in for skel copying; `id <user>` reports
    # whether the account already exists. setpriv records its arguments, so the
    # test can tell the privilege drop happened, then runs its command as is.
    # Bare `id -u` is the root preflight; `id -u/-g <user>` feed setpriv.
    _stub(
        bindir,
        "id",
        f'case "$1$#" in -u1) echo 0 ;; -u2|-g2) echo 1000 ;; *) exit {int(not existing)} ;; esac',
    )
    _stub(bindir, "useradd", populate)
    _stub(bindir, "getent", f'echo "{user}:x:1000:1000::{home}:/bin/bash"')
    for name in ("semanage", "mountpoint", "restorecon", "usermod", "install"):
        _stub(bindir, name, "exit 0")
    _stub(bindir, "runuser", "exit 1")
    skip_opts = 'while [ "$1" != -- ]; do shift; done; shift'
    _stub(bindir, "setpriv", f'echo "$*" > {q(str(privdrop))}; {skip_opts}; exec "$@"')
    if existing:
        subprocess.run([shutil.which("bash") or "bash", "-c", populate], check=True)

    script = files("ks_gen.assets").joinpath("create-rootless-user.sh")
    proc = subprocess.run(
        [shutil.which("bash") or "bash", str(script), user],
        capture_output=True,
        text=True,
        env={"PATH": f"{bindir}:{os.environ['PATH']}"},
    )
    assert proc.returncode == 0, proc.stderr

    modes = {name: stat.S_IMODE((home / name).stat().st_mode) for name in skel}
    # Only group-write/exec and other bits are stripped; owner bits survive.
    assert modes == {".bashrc": 0o640, ".bash_profile": 0o640, ".bash_logout": 0o640,
                     ".cshrc": 0o740, ".tcshrc": 0o600, ".suidrc": 0o740}  # fmt: skip
    for untouched in (home / ".config" / "app.conf", home / "notes.txt", outside):
        assert stat.S_IMODE(untouched.stat().st_mode) == 0o644, untouched
    # Root must not chmod in a home the user controls: find (and its chmod)
    # runs with the user's uid and gid.
    assert privdrop.read_text(encoding="utf-8").split()[:4] == [
        "--reuid",
        "1000",
        "--regid",
        "1000",
    ]
