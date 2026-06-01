from __future__ import annotations

from pathlib import Path

import typer

from ks_gen.lint import lint_kickstart
from ks_gen.loader import ConfigError, ExitCode, load_host_config
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


if __name__ == "__main__":
    app()
