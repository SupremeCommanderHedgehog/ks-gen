from importlib.resources import files

import pytest


@pytest.mark.parametrize(
    "asset",
    ["create-rootless-user.sh", "create-rootless-user-ubuntu.sh"],
)
def test_linger_falls_back_to_marker_file_in_chroot(asset):
    # Regression: `loginctl enable-linger` fails inside anaconda's %post
    # install chroot (no logind/D-Bus). Under the script's `set -e` that
    # non-zero exit aborted the whole %post, leaving a half-installed,
    # unbootable system. The call must be guarded and fall back to writing
    # the linger marker file directly so a first real container install
    # completes. See fix/rootless-linger-chroot.
    script = files("ks_gen.assets").joinpath(asset).read_text(encoding="utf-8")
    assert "if ! loginctl enable-linger" in script, (
        f"{asset}: unguarded `loginctl enable-linger` will abort %post in a chroot"
    )
    assert "/var/lib/systemd/linger/" in script, (
        f"{asset}: missing the marker-file fallback for chroot linger"
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
