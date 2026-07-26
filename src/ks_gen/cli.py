from __future__ import annotations

import json as _json
import re
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
from ks_gen.verify.auth import resolve_sudo_auth
from ks_gen.verify.errors import VerifyError, error_label
from ks_gen.verify.fleet import FleetOptions, make_verify_one, parse_hosts_file, run_fleet
from ks_gen.verify.history import (
    read_history,
    read_host_history,
    record_from_report,
    render_history_json,
    render_history_table,
    write_record,
)
from ks_gen.verify.html import render_fleet_html, render_html
from ks_gen.verify.reconcile import VerifyReport
from ks_gen.verify.report import (
    render_fleet_json,
    render_fleet_table,
    render_json,
    render_table,
)
from ks_gen.verify.ssh import check_tools
from ks_gen.verify.suggest import AppendResult, Suggestion, apply_to_host_yaml, build_suggestions
from ks_gen.verify.transport import LocalTransport
from ks_gen.wizard import WizardError, run_wizard, write_initial
from ks_gen.writer import build_bundle, write_bundle

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="ks-gen — DISA STIG kickstart/autoinstall generator (AlmaLinux 9, Ubuntu 24.04)",
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
    # lint_kickstart validates ks.cfg invariants; skip for ubuntu2404 until
    # phase 4 introduces a user-data lint. alma8 produces a ks.cfg with the
    # same shape as alma9, so the same lint applies.
    if bundle.distro in ("alma9", "alma8"):
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
    distro: str = typer.Option("alma9", "--distro", help="Distro to list rules for."),
) -> None:
    catalog = load_rules(distro)
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
    # lint_kickstart validates ks.cfg invariants; skip for ubuntu2404 until
    # phase 4 introduces a user-data lint. alma8 produces a ks.cfg with the
    # same shape as alma9, so the same lint applies.
    if bundle.distro in ("alma9", "alma8"):
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
    network_install: bool | None = typer.Option(
        None,
        "--network-install/--no-network-install",
        help="Drop inst.repo=hd:LABEL from the boot menu so Anaconda uses the "
        "kickstart's url/repo instead of the ISO's own repo. Default: auto-"
        "detected from whether the kickstart has a `url` install source.",
    ),
) -> None:
    ks_text = ks.read_text(encoding="utf-8")
    ks_is_network = re.search(r"(?m)^url\s+--url=", ks_text) is not None
    if network_install is None:
        network_install = ks_is_network
    elif network_install != ks_is_network:
        typer.echo(
            "--network-install / --no-network-install contradicts the kickstart: "
            f"it {'has' if ks_is_network else 'has no'} a `url` install source. "
            "Regenerate the bundle (install.source) or drop the flag.",
            err=True,
        )
        raise typer.Exit(code=int(ExitCode.USAGE))

    try:
        build_iso(src, ks, tailoring, out, volid=volid, network_install=network_install)
    except IsoBuildError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=int(ExitCode.TOOL_MISSING)) from None
    typer.echo(f"Wrote {out}")


def _record_run(record_dir: Path, report: VerifyReport) -> None:
    """Persist one run to the history store. A write failure warns to stderr
    but never aborts the verify (the run already completed and rendered)."""
    try:
        write_record(record_dir, record_from_report(report))
    except ConfigError as e:
        typer.echo(f"ks-gen verify: warning: could not record run: {e}", err=True)


def _echo_apply_summary(result: AppendResult) -> None:
    if result.added:
        typer.echo(
            f"ks-gen verify: applied {len(result.added)} suggestion(s): "
            f"{', '.join(result.added)} (backup at {result.backup_path})",
            err=True,
        )
    if result.skipped_existing:
        typer.echo(
            f"ks-gen verify: skipped {len(result.skipped_existing)} already-present: "
            f"{', '.join(result.skipped_existing)}",
            err=True,
        )
    if result.skipped_regression:
        typer.echo(
            f"ks-gen verify: skipped {len(result.skipped_regression)} regression "
            f"(use --allow-regression to apply): {', '.join(result.skipped_regression)}",
            err=True,
        )
    if not (result.added or result.skipped_existing or result.skipped_regression):
        typer.echo("ks-gen verify: nothing to apply", err=True)


def _write_html_report(html_out: Path, html_str: str) -> None:
    """Write the HTML report file, converting any OS error into a clean
    USAGE exit instead of a raw traceback. Callers invoke this before their
    own exit-code raise so the artifact still lands on a failing run.
    """
    try:
        html_out.write_text(html_str, encoding="utf-8")
    except OSError as e:
        typer.echo(f"ks-gen verify: cannot write --html-out {html_out}: {e}", err=True)
        raise typer.Exit(code=int(ExitCode.USAGE)) from e


def _emit_single_host_report(
    *,
    report: VerifyReport,
    suggestions: list[Suggestion] | None,
    format_: str,
    html_out: Path | None,
) -> None:
    """Render a single-host report to stdout per --format, and additionally
    write the HTML file when --html-out is set. The file write happens here
    (before the caller's exit-code raise) so the artifact lands on failing runs.
    """
    # Build the HTML once if either stdout OR the file needs it; this invariant
    # guarantees html_str is non-None wherever it is consumed below.
    html_str = None
    if format_ == "html" or html_out is not None:
        html_str = render_html(report, suggestions=suggestions)
    if format_ == "html":
        typer.echo(html_str)
    elif format_ == "json":
        typer.echo(render_json(report, suggestions=suggestions))
    else:
        typer.echo(render_table(report, suggestions=suggestions))
    if html_out is not None:
        assert html_str is not None
        _write_html_report(html_out, html_str)


def _run_fleet_cmd(
    *,
    hosts: Path,
    jobs: int,
    user: str | None,
    ssh_opts: str,
    format_: str,
    html_out: Path | None,
    no_drift: bool,
    check_tailoring: bool,
    timeout: int,
    ask_sudo_pass: bool,
    record: Path | None,
    rejected: dict[str, bool],
) -> None:
    bad = [flag for flag, present in rejected.items() if present]
    if bad:
        typer.echo(f"ks-gen verify: {', '.join(sorted(bad))} is not valid with --hosts", err=True)
        raise typer.Exit(code=int(ExitCode.USAGE))

    try:
        specs = parse_hosts_file(hosts)
    except ConfigError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=int(e.exit_code)) from None

    try:
        check_tools()
    except VerifyError as e:
        typer.echo(f"ks-gen verify: {e}", err=True)
        raise typer.Exit(code=int(e.exit_code)) from None

    try:
        sudo_auth = resolve_sudo_auth(ask_sudo_pass, user="fleet", host="fleet")
    except ConfigError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=int(e.exit_code)) from None

    extra_opts = shlex.split(ssh_opts) if ssh_opts else []
    opts = FleetOptions(
        no_drift=no_drift,
        check_tailoring=check_tailoring,
        ssh_extra_opts=extra_opts,
        timeout=timeout,
        sudo_auth=sudo_auth,
        fleet_user=user,
    )
    fleet = run_fleet(specs, jobs=jobs, verify_one=make_verify_one(opts))

    html_str = None
    if format_ == "html" or html_out is not None:
        html_str = render_fleet_html(fleet, jobs=jobs)
    if format_ == "html":
        typer.echo(html_str)
    elif format_ == "json":
        typer.echo(render_fleet_json(fleet))
    else:
        typer.echo(render_fleet_table(fleet, jobs=jobs))
    if html_out is not None:
        assert html_str is not None
        _write_html_report(html_out, html_str)

    if record is not None:
        for outcome in fleet.outcomes:
            if outcome.report is not None:
                _record_run(record, outcome.report)

    raise typer.Exit(code=fleet.aggregate_exit_code)


def _run_local_cmd(
    *,
    config: Path | None,
    format_: str,
    html_out: Path | None,
    no_drift: bool,
    check_tailoring: bool,
    baseline: Path | None,
    capture_baseline: Path | None,
    suggest_exceptions: bool,
    arf_out: Path | None,
    keep_arf: bool,
    timeout: int,
    record: Path | None,
    rejected: dict[str, bool],
) -> None:
    bad = [flag for flag, present in rejected.items() if present]
    if bad:
        typer.echo(f"ks-gen verify: {', '.join(sorted(bad))} is not valid with --local", err=True)
        raise typer.Exit(code=int(ExitCode.USAGE))
    if config is None:
        typer.echo("ks-gen verify: --config is required with --local", err=True)
        raise typer.Exit(code=int(ExitCode.USAGE))
    if baseline is not None and capture_baseline is not None:
        typer.echo(
            "ks-gen verify: --baseline and --capture-baseline are mutually exclusive", err=True
        )
        raise typer.Exit(code=int(ExitCode.USAGE))

    try:
        cfg = load_host_config(config, sets=[])
    except ConfigError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=int(e.exit_code)) from None

    # Preflight (root + oscap) up front so tool/root errors get a clean,
    # non-transport message + correct exit code (mirrors check_tools() in the
    # remote path). collect_arfs calls preflight again — idempotent.
    try:
        LocalTransport().preflight()
    except (ConfigError, VerifyError) as e:
        typer.echo(f"ks-gen verify: {e}", err=True)
        raise typer.Exit(code=int(e.exit_code)) from None

    def _do(workdir: Path) -> None:
        try:
            report = run_verify(
                cfg=cfg,
                host="",
                user="",
                workdir=workdir,
                local=True,
                no_drift=no_drift,
                check_tailoring=check_tailoring,
                baseline_path=baseline,
                capture_to=capture_baseline,
                timeout=timeout,
            )
        except ConfigError as e:
            typer.echo(f"ks-gen verify: {e}", err=True)
            raise typer.Exit(code=int(e.exit_code)) from None
        except VerifyError as e:
            label = error_label(e)
            typer.echo(f"ks-gen verify: transport failure: {label}: {e}", err=True)
            raise typer.Exit(code=int(e.exit_code)) from None

        suggestions = build_suggestions(report) if suggest_exceptions else None
        _emit_single_host_report(
            report=report,
            suggestions=suggestions,
            format_=format_,
            html_out=html_out,
        )

        if record is not None:
            _record_run(record, report)

        if not report.is_clean:
            raise typer.Exit(code=int(ExitCode.VERIFY_FAIL))
        if report.has_tailoring_drift:
            raise typer.Exit(code=int(ExitCode.TAILORING_DRIFT))

    if arf_out is not None or keep_arf:
        target = arf_out or Path(tempfile.mkdtemp(prefix="ksgen-verify-"))
        target.mkdir(parents=True, exist_ok=True)
        if arf_out is None:
            typer.echo(f"ks-gen verify: ARFs persisted under {target}", err=True)
        _do(target)
    else:
        with tempfile.TemporaryDirectory(prefix="ksgen-verify-") as tmpdir:
            _do(Path(tmpdir))


@app.command(
    name="verify",
    help="Re-run oscap on a deployed host and reconcile against host.yaml.",
)
def verify_cmd(
    host: str | None = typer.Option(None, "--host"),
    hosts: Path | None = typer.Option(  # noqa: B008
        None,
        "--hosts",
        exists=True,
        dir_okay=False,
        readable=True,
        help=(
            "Fleet mode: file of '[user@]host  path/to/host.yaml' lines. "
            "Mutually exclusive with --host/--config."
        ),
    ),
    jobs: int = typer.Option(
        5, "--jobs", min=1, help="Max concurrent hosts in fleet mode (default 5)."
    ),
    local: bool = typer.Option(
        False,
        "--local",
        help=(
            "Run the check on THIS host (no SSH). Requires root and --config. "
            "Rejects --host/--hosts/--user/--ssh-opts/--ask-sudo-pass/--apply."
        ),
    ),
    config: Path | None = typer.Option(  # noqa: B008
        None, "--config", "-c", exists=True, dir_okay=False, readable=True
    ),
    user: str | None = typer.Option(
        None, "--user", help="SSH login user; defaults to cfg.user.admin.name."
    ),
    ssh_opts: str = typer.Option(
        "",
        "--ssh-opts",
        help="Extra args appended to every ssh invocation (shell-quoted).",
    ),
    format_: str = typer.Option("table", "--format", help="Output format: table | json | html."),
    arf_out: Path | None = typer.Option(  # noqa: B008
        None,
        "--arf-out",
        file_okay=False,
        help="Persist pulled ARFs in this directory.",
    ),
    html_out: Path | None = typer.Option(  # noqa: B008
        None,
        "--html-out",
        dir_okay=False,
        help=(
            "Also write a self-contained HTML report to this file "
            "(parent directory must already exist)."
        ),
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
    apply: bool = typer.Option(
        False,
        "--apply",
        help=(
            "Append the suggestions to host.yaml after a backup + schema "
            "round-trip. Implies --suggest-exceptions. Regression-category "
            "suggestions require --allow-regression."
        ),
    ),
    allow_regression: bool = typer.Option(
        False,
        "--allow-regression",
        help=(
            "Allow --apply to write regression-category suggestions. No effect "
            "without --apply; the safety story is intentional."
        ),
    ),
    check_tailoring: bool = typer.Option(
        False,
        "--check-tailoring",
        help=(
            "Re-render the expected tailoring locally and diff against the host's "
            "/root/tailoring.xml. Reports drift as a separate section; exit 8 if "
            "drift is detected and compliance is otherwise clean."
        ),
    ),
    capture_baseline: Path | None = typer.Option(  # noqa: B008
        None,
        "--capture-baseline",
        help=(
            "Write the freshly-captured ARF to this path on the workstation. "
            "Use the saved file later via --baseline. Mutually exclusive with --baseline."
        ),
    ),
    baseline: Path | None = typer.Option(  # noqa: B008
        None,
        "--baseline",
        help=(
            "Use this workstation-side ARF as the drift baseline instead of the "
            "host's /root/oscap-remediation-results.xml. Skips the install-ARF "
            "pull. Mutually exclusive with --capture-baseline."
        ),
    ),
    record: Path | None = typer.Option(  # noqa: B008
        None,
        "--record",
        file_okay=False,
        help=(
            "Append a slim record of this run to <dir>/<host>.jsonl for trend "
            "tracking. Works in all modes. Read it back with 'ks-gen verify-history'."
        ),
    ),
    timeout: int = typer.Option(600, "--timeout", help="oscap run timeout in seconds."),
    ask_sudo_pass: bool = typer.Option(
        False,
        "--ask-sudo-pass",
        help=(
            "Use password-based sudo on the host: read the password from "
            "KSGEN_SUDO_PASSWORD, or prompt if unset. Default is passwordless "
            "(sudo -n). Never pass the password via --ssh-opts."
        ),
    ),
) -> None:
    if format_ not in ("table", "json", "html"):
        typer.echo(f"--format must be 'table', 'json', or 'html', got: {format_!r}", err=True)
        raise typer.Exit(code=int(ExitCode.USAGE))

    if html_out is not None and not html_out.parent.is_dir():
        typer.echo(
            f"ks-gen verify: --html-out parent is not an existing directory: {html_out.parent}",
            err=True,
        )
        raise typer.Exit(code=int(ExitCode.USAGE))

    if sum([host is not None, hosts is not None, local]) != 1:
        typer.echo("ks-gen verify: exactly one of --host / --hosts / --local is required", err=True)
        raise typer.Exit(code=int(ExitCode.USAGE))

    if hosts is not None:
        _run_fleet_cmd(
            hosts=hosts,
            jobs=jobs,
            user=user,
            ssh_opts=ssh_opts,
            format_=format_,
            html_out=html_out,
            no_drift=no_drift,
            check_tailoring=check_tailoring,
            timeout=timeout,
            ask_sudo_pass=ask_sudo_pass,
            record=record,
            rejected={
                "--config": config is not None,
                "--suggest-exceptions": suggest_exceptions,
                "--apply": apply,
                "--allow-regression": allow_regression,
                "--baseline": baseline is not None,
                "--capture-baseline": capture_baseline is not None,
                "--arf-out": arf_out is not None,
                "--keep-arf": keep_arf,
            },
        )
        return

    if local:
        _run_local_cmd(
            config=config,
            format_=format_,
            html_out=html_out,
            no_drift=no_drift,
            check_tailoring=check_tailoring,
            baseline=baseline,
            capture_baseline=capture_baseline,
            suggest_exceptions=suggest_exceptions,
            arf_out=arf_out,
            keep_arf=keep_arf,
            timeout=timeout,
            record=record,
            rejected={
                "--user": user is not None,
                "--ssh-opts": bool(ssh_opts),
                "--ask-sudo-pass": ask_sudo_pass,
                "--apply": apply,
                "--allow-regression": allow_regression,
            },
        )
        return

    # ---- single-host mode from here on ----
    if config is None:
        typer.echo("ks-gen verify: --config is required with --host", err=True)
        raise typer.Exit(code=int(ExitCode.USAGE))

    # Mode-selection above guarantees exactly one of --host/--hosts; after
    # the fleet branch returned, host is not None.  One assertion here lets
    # mypy propagate the narrowing through the rest of single-host code.
    assert host is not None

    if allow_regression and not apply:
        typer.echo(
            "ks-gen verify: --allow-regression has no effect without --apply",
            err=True,
        )

    if baseline is not None and capture_baseline is not None:
        typer.echo(
            "ks-gen verify: --baseline and --capture-baseline are mutually exclusive",
            err=True,
        )
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

    try:
        sudo_auth = resolve_sudo_auth(ask_sudo_pass, user=resolved_user, host=host)
    except ConfigError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=int(e.exit_code)) from None

    def _do(workdir: Path) -> None:
        try:
            report = run_verify(
                cfg=cfg,
                host=host,
                user=resolved_user,
                workdir=workdir,
                no_drift=no_drift,
                check_tailoring=check_tailoring,
                baseline_path=baseline,
                capture_to=capture_baseline,
                ssh_extra_opts=extra_opts,
                timeout=timeout,
                sudo_auth=sudo_auth,
            )
        except ConfigError as e:
            typer.echo(f"ks-gen verify: {e}", err=True)
            raise typer.Exit(code=int(e.exit_code)) from None
        except VerifyError as e:
            # Only transport-class errors reach this handler (ToolMissingError
            # was caught earlier). Keep the "transport failure:" prefix
            # consistent so operator scripts can grep for it.
            label = error_label(e)
            typer.echo(f"ks-gen verify: transport failure: {label}: {e}", err=True)
            raise typer.Exit(code=int(e.exit_code)) from None

        want_suggestions = suggest_exceptions or apply
        suggestions = build_suggestions(report) if want_suggestions else None
        _emit_single_host_report(
            report=report,
            suggestions=suggestions,
            format_=format_,
            html_out=html_out,
        )

        # Note: `suggestions` here is guaranteed non-None when `apply` is set
        # (we built it above via `want_suggestions`). Use `is not None` rather
        # than a truthiness check so the "clean report + --apply" case still
        # calls apply_to_host_yaml(), which then prints "nothing to apply".
        if apply and suggestions is not None:
            try:
                apply_result = apply_to_host_yaml(
                    suggestions=suggestions,
                    host_yaml_path=config,
                    allow_regression=allow_regression,
                )
            except VerifyError as e:
                typer.echo(f"ks-gen verify: apply failed: {e}", err=True)
                raise typer.Exit(code=int(e.exit_code)) from None
            _echo_apply_summary(apply_result)

        if record is not None:
            _record_run(record, report)

        if not report.is_clean:
            raise typer.Exit(code=int(ExitCode.VERIFY_FAIL))
        if report.has_tailoring_drift:
            raise typer.Exit(code=int(ExitCode.TAILORING_DRIFT))

    if arf_out is not None or keep_arf:
        target = arf_out or Path(tempfile.mkdtemp(prefix="ksgen-verify-"))
        target.mkdir(parents=True, exist_ok=True)
        if arf_out is None:
            typer.echo(f"ks-gen verify: ARFs persisted under {target}", err=True)
        _do(target)
    else:
        with tempfile.TemporaryDirectory(prefix="ksgen-verify-") as tmpdir:
            _do(Path(tmpdir))


@app.command(
    name="verify-history",
    help="Show run-over-run trends from a --record history directory.",
)
def verify_history_cmd(
    record_dir: Path = typer.Argument(  # noqa: B008
        ..., help="Directory of <host>.jsonl records written by 'verify --record'."
    ),
    host: str | None = typer.Option(
        None, "--host", help="Show only this host (default: every host in the dir)."
    ),
    format_: str = typer.Option("table", "--format", help="Output format: table | json."),
) -> None:
    if format_ not in ("table", "json"):
        typer.echo(f"--format must be 'table' or 'json', got: {format_!r}", err=True)
        raise typer.Exit(code=int(ExitCode.USAGE))

    if host is not None:
        host_path = record_dir / f"{host}.jsonl"
        if not host_path.is_file():
            typer.echo(
                f"ks-gen verify-history: no history for host {host!r} in {record_dir}",
                err=True,
            )
            raise typer.Exit(code=int(ExitCode.USAGE))

    try:
        if host is not None:
            history = {host: read_host_history(record_dir / f"{host}.jsonl")}
        else:
            history = read_history(record_dir)
    except ConfigError as e:
        typer.echo(f"ks-gen verify-history: {e}", err=True)
        raise typer.Exit(code=int(e.exit_code)) from None

    if format_ == "json":
        typer.echo(render_history_json(history))
    else:
        blocks = [render_history_table(h, recs) for h, recs in sorted(history.items())]
        typer.echo("\n".join(blocks))


if __name__ == "__main__":
    app()
