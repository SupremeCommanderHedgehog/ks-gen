import json

from typer.testing import CliRunner

from ks_gen.cli import app
from ks_gen.loader import ExitCode


def test_rules_default_lists_ids():
    result = CliRunner().invoke(app, ["rules"])
    assert result.exit_code == 0
    assert "admin_user_and_keys" in result.output
    assert "crypto_policy" in result.output


def test_rules_id_filter_returns_detail():
    result = CliRunner().invoke(app, ["rules", "--id", "crypto_policy"])
    assert result.exit_code == 0
    assert "crypto_policy" in result.output
    assert "depends_on" in result.output or "Affects" in result.output


def test_rules_json_format_parses():
    result = CliRunner().invoke(app, ["rules", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert any(r["id"] == "admin_user_and_keys" for r in data)


def test_rules_lists_every_supported_alma_distro():
    for distro in ("alma8", "alma9", "alma10"):
        result = CliRunner().invoke(app, ["rules", "--distro", distro])
        assert result.exit_code == 0, distro
        assert "crypto_policy" in result.output, distro


def test_rules_rejects_the_removed_ubuntu_distro():
    """#103: an empty catalog with exit 0 would read as "no rules" to a script."""
    result = CliRunner().invoke(app, ["rules", "--distro", "ubuntu2404"])
    assert result.exit_code == ExitCode.USAGE
    assert "no longer supported" in result.stderr


def test_rules_rejects_an_unknown_distro():
    result = CliRunner().invoke(app, ["rules", "--distro", "alma7"])
    assert result.exit_code == ExitCode.USAGE
    assert "unknown distro: alma7" in result.stderr
