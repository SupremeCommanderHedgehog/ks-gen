import textwrap

from typer.testing import CliRunner

from ks_gen.cli import app


def test_lint_subcommand_passes_on_generated_ks(tmp_path):
    runner = CliRunner()
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(
        textwrap.dedent(
            """\
            system: {hostname: x}
            user:
              admin:
                name: ops
                authorized_keys: ["ssh-ed25519 A a@b"]
            """
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    assert runner.invoke(app, ["gen", "-c", str(cfg_path), "-o", str(out_dir)]).exit_code == 0
    result = runner.invoke(app, ["lint", str(out_dir / "ks.cfg")])
    assert result.exit_code == 0, result.output


def test_lint_fails_on_garbage(tmp_path):
    runner = CliRunner()
    bad = tmp_path / "bad.cfg"
    bad.write_text("this is not a kickstart", encoding="utf-8")
    result = runner.invoke(app, ["lint", str(bad)])
    assert result.exit_code == 4
