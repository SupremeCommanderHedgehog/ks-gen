import textwrap

from typer.testing import CliRunner

from ks_gen.cli import app

YAML = textwrap.dedent(
    """\
    system: {hostname: web01.example.com}
    user:
      admin:
        name: opsadmin
        authorized_keys: ["ssh-ed25519 AAAA a@b"]
    """
)


def test_gen_writes_bundle(tmp_path):
    runner = CliRunner()
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(YAML, encoding="utf-8")
    out_dir = tmp_path / "out"
    result = runner.invoke(app, ["gen", "--config", str(cfg_path), "--out", str(out_dir)])
    assert result.exit_code == 0, result.output
    for name in ("ks.cfg", "tailoring.xml", "host.yaml", "exceptions.md"):
        assert (out_dir / name).is_file()


def test_gen_set_override_applies(tmp_path):
    runner = CliRunner()
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(YAML, encoding="utf-8")
    out_dir = tmp_path / "out"
    result = runner.invoke(
        app,
        ["gen", "--config", str(cfg_path), "--out", str(out_dir), "--set", "ssh.port=2222"],
    )
    assert result.exit_code == 0
    assert "Port 2222" in (out_dir / "ks.cfg").read_text()


def test_gen_fips_conflict_returns_3(tmp_path):
    runner = CliRunner()
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(YAML, encoding="utf-8")
    out_dir = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "gen",
            "--config",
            str(cfg_path),
            "--out",
            str(out_dir),
            "--set",
            "overrides.fips_mode=true",
        ],
    )
    assert result.exit_code == 3, result.output
