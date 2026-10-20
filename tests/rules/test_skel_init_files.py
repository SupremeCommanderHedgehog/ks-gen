"""skel_init_files tightens /etc/skel so every new home meets the STIG (#131)."""

from __future__ import annotations

import shutil
import stat
import subprocess

import pytest

from ks_gen.registry import load_rules
from ks_gen.rules.alma9.skel_init_files import SKEL
from ks_gen.ssg_ids import RULE_PREFIX
from ks_gen.topo import topo_sort

_ALMA = ["alma8", "alma9", "alma10"]


def _rule(distro):
    return next(r for r in load_rules(distro) if r.id == "skel_init_files")


def _gnu_find() -> bool:
    find = shutil.which("find")
    if find is None:
        return False
    probe = [find, ".", "-maxdepth", "0", "-regextype", "posix-extended"]
    return subprocess.run(probe, capture_output=True).returncode == 0


@pytest.mark.skipif(not _gnu_find(), reason="needs GNU find (-regextype), as on AlmaLinux")
def test_post_tightens_skel_init_files_only(tmp_path, minimal_cfg):
    """Run the emitted %post against a stand-in skel: init files lose group
    write/exec and all other bits, owner bits survive, and nothing that isn't
    a top-level init file is touched."""
    skel = tmp_path / "skel"
    (skel / ".config").mkdir(parents=True)
    modes = {".bashrc": 0o644, ".bash_profile": 0o664, ".bash_logout": 0o644,
             ".kshrc": 0o777, ".zshrc": 0o600, "README": 0o644,
             ".config/app.conf": 0o644, ".backup.old": 0o644,
             ".suidrc": 0o4740, ".sgidrc": 0o2640, ".stickyrc": 0o1600}  # fmt: skip
    for name, mode in modes.items():
        (skel / name).touch()
        (skel / name).chmod(mode)

    script = _rule("alma9").emit_post(minimal_cfg)
    assert f"find {SKEL}/ " in script
    script = script.replace(SKEL, str(skel))
    subprocess.run(["bash", "-euo", "pipefail", "-c", script], check=True)

    after = {name: stat.S_IMODE((skel / name).stat().st_mode) for name in modes}
    assert after == {
        ".bashrc": 0o640, ".bash_profile": 0o640, ".bash_logout": 0o640,
        ".kshrc": 0o740, ".zshrc": 0o600,
        # "0740 or less permissive" rules out the special bits too.
        ".suidrc": 0o740, ".sgidrc": 0o640, ".stickyrc": 0o600,
        "README": 0o644,  # not a dotfile
        ".config/app.conf": 0o644,  # not directly in skel
        ".backup.old": 0o644,  # '.' isn't in the STIG's [\w\- ] class
    }  # fmt: skip


@pytest.mark.parametrize("distro", _ALMA)
def test_runs_before_anything_that_creates_a_home(distro):
    order = [r.id for r in topo_sort(load_rules(distro))]
    skel = order.index("skel_init_files")
    assert skel < order.index("admin_user_and_keys")
    assert skel < order.index("container_host")


@pytest.mark.parametrize(
    ("distro", "rid"),
    [
        ("alma8", "file_permission_user_init_files_root"),
        ("alma9", "file_permission_user_init_files_root"),
        ("alma10", "file_permission_user_init_files"),
    ],
)
def test_declares_the_distros_stig_init_file_rule(distro, rid, minimal_cfg):
    """Declared rules are ones ks-gen enforces, so verify never suggests
    waiving them (#87). Selection per distro is checked against the
    datastreams by tests/test_rule_ids_selected_by_stig.py."""
    rule = _rule(distro)
    assert rule.stig_rules_affected == [RULE_PREFIX + rid]
    assert rule.applies(minimal_cfg)
    assert rule.emit_tailoring(minimal_cfg) == []
    assert rule.exception_entry(minimal_cfg) is None


@pytest.mark.parametrize("missing", ["absent", "not-a-dir"])
def test_post_never_fails_the_install(tmp_path, minimal_cfg, missing):
    """It runs before admin_user_and_keys under `set -e` and --erroronfail, so
    a problem here must not abort %post before the admin exists."""
    skel = tmp_path / "skel"
    if missing == "not-a-dir":
        skel.write_text("", encoding="utf-8")
    script = _rule("alma9").emit_post(minimal_cfg).replace(SKEL, str(skel))
    proc = subprocess.run(["bash", "-euo", "pipefail", "-c", script], capture_output=True)
    assert proc.returncode == 0, proc.stderr
