from __future__ import annotations

import json as _json
from pathlib import Path

import typer

from ks_gen.config import HostConfig
from ks_gen.lint import lint_kickstart
from ks_gen.loader import ConfigError, ExitCode, load_host_config
from ks_gen.registry import load_rules
from ks_gen.writer import build_bundle, write_bundle

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="ks-gen — DISA STIG AlmaLinux kickstart generator",
)


@app.command(
    name="gen", help="Render ks.cfg + tailoring.xml + exceptions.md + host.yaml from a config."
)
def gen(
    config: Path = typer.Option(  # noqa: B008
        ..., "--config", "-c", exists=True, dir_okay=False, readable=True
    ),
    out: Path = typer.Option(..., "--out", "-o", file_okay=False),  # noqa: B008
    set_: list[str] = typer.Option([], "--set", help="Dotted-path overrides, KEY=VALUE."),  # noqa: B008
) -> None:
    try:
        cfg = load_host_config(config, sets=set_)
    except ConfigError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=int(e.exit_code)) from None
    bundle = build_bundle(cfg)
    write_bundle(bundle, out)
    report = lint_kickstart(out / "ks.cfg")
    if not report.ok:
        for f in report.failures:
            typer.echo(f"lint FAIL: {f}", err=True)
        raise typer.Exit(code=int(ExitCode.LINT_FAIL))
    typer.echo(f"Wrote bundle to {out}")


@app.command(name="lint", help="Validate a generated ks.cfg.")
def lint_cmd(
    ks_path: Path = typer.Argument(..., exists=True, dir_okay=False),  # noqa: B008
) -> None:
    report = lint_kickstart(ks_path)
    if report.ok:
        typer.echo("OK")
        return
    for f in report.failures:
        typer.echo(f"FAIL: {f}", err=True)
    raise typer.Exit(code=int(ExitCode.LINT_FAIL))


@app.command(name="rules", help="List the shipped rule catalog.")
def rules_cmd(
    id_: str | None = typer.Option(None, "--id", help="Show detail for one rule id."),
    format_: str = typer.Option("table", "--format", help="table | json"),
) -> None:
    catalog = load_rules()
    if id_:
        match = next((r for r in catalog if r.id == id_), None)
        if not match:
            typer.echo(f"unknown rule id: {id_}", err=True)
            raise typer.Exit(code=int(ExitCode.USAGE))
        typer.echo(f"id: {match.id}")
        typer.echo(f"summary: {match.summary}")
        typer.echo(f"depends_on: {match.depends_on}")
        typer.echo(f"stig_rules_affected ({len(match.stig_rules_affected)}):")
        for rid in match.stig_rules_affected:
            typer.echo(f"  - {rid}")
        return
    if format_ == "json":
        typer.echo(
            _json.dumps(
                [
                    {
                        "id": r.id,
                        "summary": r.summary,
                        "depends_on": r.depends_on,
                        "stig_rules_affected": r.stig_rules_affected,
                    }
                    for r in catalog
                ],
                indent=2,
            )
        )
        return
    width = max(len(r.id) for r in catalog)
    typer.echo(f"{'ID':<{width}}  AFFECTS  SUMMARY")
    for r in catalog:
        typer.echo(f"{r.id:<{width}}  {len(r.stig_rules_affected):<7}  {r.summary}")


@app.command(name="schema", help="Emit JSON Schema for host.yaml on stdout.")
def schema_cmd() -> None:
    typer.echo(_json.dumps(HostConfig.model_json_schema(), indent=2))


if __name__ == "__main__":
    app()
