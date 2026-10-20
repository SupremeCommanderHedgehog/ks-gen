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
        sudo: nopasswd_yes
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


def _gen_with_exception(tmp_path, rule_id):
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(
        YAML
        + textwrap.dedent(
            f"""\
            exceptions:
              - id: no-luks
                reason: cloud volumes are encrypted by the provider
                stig_rules_disabled: [{rule_id}]
            """
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    result = CliRunner().invoke(app, ["gen", "--config", str(cfg_path), "--out", str(out_dir)])
    return result, out_dir


def test_gen_rejects_exception_id_not_in_datastream(tmp_path):
    """#69: a bare id deselects nothing, so gen refuses rather than claim a waiver."""
    result, out_dir = _gen_with_exception(tmp_path, "encrypt_partitions")
    assert result.exit_code == 2, result.output
    assert "did you mean 'xccdf_org.ssgproject.content_rule_encrypt_partitions'" in result.output
    assert not (out_dir / "tailoring.xml").exists()


def test_gen_accepts_full_exception_id(tmp_path):
    result, out_dir = _gen_with_exception(
        tmp_path, "xccdf_org.ssgproject.content_rule_encrypt_partitions"
    )
    assert result.exit_code == 0, result.output
    assert "warning" not in result.output
    assert "content_rule_encrypt_partitions" in (out_dir / "tailoring.xml").read_text()
