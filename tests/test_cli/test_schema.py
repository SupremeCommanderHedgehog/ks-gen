import json

from typer.testing import CliRunner

from ks_gen.cli import app


def test_schema_emits_jsonschema():
    result = CliRunner().invoke(app, ["schema"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["title"] == "HostConfig"
    assert "system" in data["properties"]
