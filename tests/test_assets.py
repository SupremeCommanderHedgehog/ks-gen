from importlib.resources import files


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
