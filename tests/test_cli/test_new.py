import textwrap

from typer.testing import CliRunner

from ks_gen.cli import app


def test_new_runs_with_scripted_stdin(tmp_path):
    runner = CliRunner()
    # Minimal happy path: accept all defaults except hostname and one key.
    # Wizard sequence: Hostname, Timezone, Locale, Admin username, Sudo mode,
    # SSH key(s), SSH port, Crypto policy.
    # Wizard prompts (9 total):
    #   Hostname (required), Timezone, Locale, Admin username, Sudo mode,
    #   SSH key (required, no default), stop-key blank, SSH port, Crypto policy.
    # NOTE: The plan's fixture had an extra blank after opsadmin causing the
    # second blank to hit the required SSH-key prompt and raise WizardError.
    # Fixed: only one blank between opsadmin (sudo default) and the key.
    stdin = textwrap.dedent(
        """\
        web01.example.com


        opsadmin

        ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA test@laptop



        """
    )
    out_dir = tmp_path / "out"
    result = runner.invoke(
        app,
        ["new", "--out", str(out_dir)],
        input=stdin,
    )
    assert result.exit_code == 0, result.output
    for name in ("ks.cfg", "tailoring.xml", "host.yaml", "exceptions.md"):
        assert (out_dir / "web01.example.com" / name).is_file()


def test_new_non_interactive_errors_without_required_fields(tmp_path):
    runner = CliRunner()
    result = runner.invoke(app, ["new", "--out", str(tmp_path / "x"), "--non-interactive"])
    assert result.exit_code != 0
