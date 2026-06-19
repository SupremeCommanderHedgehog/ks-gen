import textwrap

from typer.testing import CliRunner

from ks_gen.cli import app

UBUNTU_YAML = textwrap.dedent(
    """\
    distro: ubuntu2404
    system: {hostname: u24-cli-test}
    user:
      admin:
        name: ops
        authorized_keys: ["ssh-ed25519 AAAA a@b"]
        sudo: nopasswd_yes
    """
)


def test_gen_ubuntu2404_writes_seed_files_and_skips_kickstart_lint(tmp_path):
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(UBUNTU_YAML, encoding="utf-8")
    out_dir = tmp_path / "out"
    result = CliRunner().invoke(app, ["gen", "--config", str(cfg_path), "--out", str(out_dir)])
    assert result.exit_code == 0, result.output
    # Five expected files; ks.cfg is NOT one of them.
    for name in ("user-data", "meta-data", "tailoring.xml", "host.yaml", "exceptions.md"):
        assert (out_dir / name).is_file(), f"missing {name}: {result.output}"
    assert not (out_dir / "ks.cfg").exists()
    assert "Wrote bundle to" in result.output
