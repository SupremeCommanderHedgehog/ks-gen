from __future__ import annotations

import json as _json
import shlex
import tempfile
from pathlib import Path

import typer

from ks_gen.config import HostConfig
from ks_gen.iso import IsoBuildError, build_iso
from ks_gen.lint import lint_kickstart
from ks_gen.loader import ConfigError, ExitCode, load_host_config
from ks_gen.registry import load_rules
from ks_gen.verify import run_verify
from ks_gen.verify.errors import VerifyError
from ks_gen.verify.report import render_json, render_table
from ks_gen.verify.ssh import check_tools
from ks_gen.verify.suggest import build_suggestions
from ks_gen.wizard import WizardError, run_wizard, write_initial
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


@app.command(name="new", help="Interactive wizard: produce host.yaml + ks bundle.")
def new_cmd(
    out: Path = typer.Option(..., "--out", "-o", file_okay=False),  # noqa: B008
    non_interactive: bool = typer.Option(False, "--non-interactive"),
) -> None:
    try:
        cfg, yaml_text = run_wizard(interactive=not non_interactive)
    except WizardError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=int(ExitCode.USAGE)) from None
    host_dir = write_initial(out, cfg, yaml_text)
    bundle = build_bundle(cfg)
    write_bundle(bundle, host_dir)
    report = lint_kickstart(host_dir / "ks.cfg")
    if not report.ok:
        for f in report.failures:
            typer.echo(f"lint FAIL: {f}", err=True)
        raise typer.Exit(code=int(ExitCode.LINT_FAIL))
    typer.echo(f"Wrote bundle to {host_dir}")


@app.command(name="schema", help="Emit JSON Schema for host.yaml on stdout.")
def schema_cmd() -> None:
    typer.echo(_json.dumps(HostConfig.model_json_schema(), indent=2))


@app.command(name="iso", help="Repackage AlmaLinux DVD ISO with ks.cfg + tailoring embedded.")
def iso_cmd(
    src: Path = typer.Option(..., "--src", exists=True, dir_okay=False),  # noqa: B008
    ks: Path = typer.Option(..., "--ks", exists=True, dir_okay=False),  # noqa: B008
    tailoring: Path = typer.Option(..., "--tailoring", exists=True, dir_okay=False),  # noqa: B008
    out: Path = typer.Option(..., "--out", dir_okay=False),  # noqa: B008
    volid: str = typer.Option("ALMA9", "--volid"),
) -> None:
    try:
        build_iso(src, ks, tailoring, out, volid=volid)
    except IsoBuildError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=int(ExitCode.TOOL_MISSING)) from None
    typer.echo(f"Wrote {out}")


@app.command(
    name="verify",
    help="Re-run oscap on a deployed host and reconcile against host.yaml.",
)
def verify_cmd(
    host: str = typer.Option(..., "--host"),
    config: Path = typer.Option(  # noqa: B008
        ..., "--config", "-c", exists=True, dir_okay=False, readable=True
    ),
    user: str | None = typer.Option(
        None, "--user", help="SSH login user; defaults to cfg.user.admin.name."
    ),
    ssh_opts: str = typer.Option(
        "",
        "--ssh-opts",
        help="Extra args appended to every ssh/scp invocation (shell-quoted).",
    ),
    format_: str = typer.Option("table", "--format", help="Output format: table | json."),
    arf_out: Path | None = typer.Option(  # noqa: B008
        None,
        "--arf-out",
        file_okay=False,
        help="Persist pulled ARFs in this directory.",
    ),
    keep_arf: bool = typer.Option(
        False,
        "--keep-arf",
        help="Persist pulled ARFs in a new system temp directory (path is echoed).",
    ),
    no_drift: bool = typer.Option(
        False, "--no-drift", help="Skip the install-time ARF probe; compliance-only."
    ),
    suggest_exceptions: bool = typer.Option(
        False,
        "--suggest-exceptions",
        help="Render ready-to-paste ExceptionDecl YAML for new_fail and regression rules.",
    ),
    timeout: int = typer.Option(600, "--timeout", help="oscap run timeout in seconds."),
) -> None:
    if format_ not in ("table", "json"):
        typer.echo(f"--format must be 'table' or 'json', got: {format_!r}", err=True)
        raise typer.Exit(code=int(ExitCode.USAGE))

    try:
        cfg = load_host_config(config, sets=[])
    except ConfigError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=int(e.exit_code)) from None

    # ToolMissingError (exit_code=TOOL_MISSING=5) is caught here so it doesn't
    # fall through to the transport-failure handler inside _do. Don't fold this
    # handler into _do — that would relabel "ssh not on PATH" as transport.
    try:
        check_tools()
    except VerifyError as e:
        typer.echo(f"ks-gen verify: {e}", err=True)
        raise typer.Exit(code=int(e.exit_code)) from None

    resolved_user = user or cfg.user.admin.name
    extra_opts = shlex.split(ssh_opts) if ssh_opts else []

    def _do(workdir: Path) -> None:
        try:
            report = run_verify(
                cfg=cfg,
                host=host,
                user=resolved_user,
                workdir=workdir,
                no_drift=no_drift,
                ssh_extra_opts=extra_opts,
                timeout=timeout,
            )
        except VerifyError as e:
            # Only transport-class errors reach this handler (ToolMissingError
            # was caught earlier). Keep the "transport failure:" prefix
            # consistent so operator scripts can grep for it.
            label = type(e).__name__.removesuffix("Error").lower()
            typer.echo(f"ks-gen verify: transport failure: {label}: {e}", err=True)
            raise typer.Exit(code=int(e.exit_code)) from None

        suggestions = build_suggestions(report) if suggest_exceptions else None
        if format_ == "json":
            typer.echo(render_json(report, suggestions=suggestions))
        else:
            typer.echo(render_table(report, suggestions=suggestions))

        if not report.is_clean:
            raise typer.Exit(code=int(ExitCode.VERIFY_FAIL))

    if arf_out is not None or keep_arf:
        target = arf_out or Path(tempfile.mkdtemp(prefix="ksgen-verify-"))
        target.mkdir(parents=True, exist_ok=True)
        if arf_out is None:
            typer.echo(f"ks-gen verify: ARFs persisted under {target}", err=True)
        _do(target)
    else:
        with tempfile.TemporaryDirectory(prefix="ksgen-verify-") as tmpdir:
            _do(Path(tmpdir))


if __name__ == "__main__":
    app()
