import json

from typer.testing import CliRunner

from ks_gen.cli import app


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
