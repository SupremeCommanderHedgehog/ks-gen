"""Post-install host verification — re-run oscap, reconcile against host.yaml."""

from __future__ import annotations

import getpass
import socket
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from ks_gen.config import HostConfig
from ks_gen.exceptions_report import expected_failure_rule_ids
from ks_gen.loader import ConfigError, ExitCode
from ks_gen.verify.arf import RuleResult, parse_arf
from ks_gen.verify.auth import PASSWORDLESS, SudoAuth
from ks_gen.verify.baseline import BaselineReport, orphan_rule_ids, read_baseline
from ks_gen.verify.errors import TailoringParseError
from ks_gen.verify.reconcile import VerifyReport, build_report
from ks_gen.verify.remote import collect_arfs, collect_deployed_tailoring
from ks_gen.verify.tailoring_drift import (
    compare_tailorings,
    parse_tailoring_xml,
)
from ks_gen.verify.transport import LocalTransport, SshTransport, Transport
from ks_gen.writer import render_tailoring


def run_verify(
    *,
    cfg: HostConfig,
    host: str,
    user: str,
    workdir: Path,
    no_drift: bool = False,
    check_tailoring: bool = False,
    baseline_path: Path | None = None,
    capture_to: Path | None = None,
    ssh_extra_opts: list[str] | None = None,
    timeout: int = 600,
    sudo_auth: SudoAuth = PASSWORDLESS,
    local: bool = False,
) -> VerifyReport:
    """Re-run oscap on `host` and reconcile against `cfg`'s exception set.

    SSHs to `host` as `user` (passwordless sudo by default; pass a password-mode
    `sudo_auth` for password sudo), runs
    `oscap xccdf eval` against the install-time `/root/tailoring.xml`, pulls
    both the fresh ARF and (unless `no_drift`) the install-time ARF at
    `/root/oscap-remediation-results.xml`, then categorizes each rule as
    clean / expected_fail / new_fail / regression / incomplete.

    When `check_tailoring` is True, also pulls `/root/tailoring.xml`, re-renders
    the expected tailoring from `cfg`, and attaches a `TailoringDriftReport` to
    the returned report. The pull happens before the compliance run so a
    missing tailoring fails fast.

    When `baseline_path` is set, the captured ARF at that path replaces the
    install-time ARF for reconcile (the install pull is skipped entirely),
    and a `BaselineReport` is attached to the returned report. When
    `capture_to` is set, the fresh-current ARF is written to that path
    AFTER the normal install-driven verify report is built. `baseline_path`
    and `capture_to` are mutually exclusive.

    Args:
        cfg: HostConfig loaded from the operator's host.yaml. The exception
            set is derived from cfg.exceptions + each applicable rule's
            exception_entry().
        host, user: SSH target.
        workdir: scratch directory for the pulled ARFs (existing or to be
            created by the caller). Files are not cleaned up by this
            function — the caller decides via `tempfile.TemporaryDirectory`
            or `--arf-out`/`--keep-arf`.
        no_drift: skip the install-time-ARF probe and pull entirely; the
            returned report has `install_baseline_available=False`. Forced
            True internally when `baseline_path` is set (the captured
            baseline already fills the install slot).
        check_tailoring: when True, pull `/root/tailoring.xml` from `host`,
            re-render the expected tailoring from `cfg`, and attach a
            `TailoringDriftReport` to the returned report. The pull happens
            before the compliance run so a missing tailoring fails fast.
        baseline_path: workstation path to a previously-captured ARF.
            Replaces the install-time ARF for drift reconcile. The
            `BaselineReport` attached to the returned report carries the
            path, captured timestamp, and orphan rule_ids.
        capture_to: workstation path to write the fresh-current ARF.
            The normal verify report still prints (install-driven reconcile);
            this just persists `arfs.current_text` for later use via
            `--baseline`.
        ssh_extra_opts: extra args appended to every `ssh` invocation
            (e.g. `["-F", "/path/to/ssh_config"]`). `None` is normalized to
            an empty list.
        sudo_auth: credential controlling how remote commands elevate.
            Defaults to passwordless (`sudo -n`); a password-mode `SudoAuth`
            runs `sudo -S` and feeds the password over stdin.
        local: run the check on THIS host via LocalTransport (requires root);
            the passed host/user are ignored and re-derived from the local
            machine (socket.gethostname()/getpass.getuser()).
        timeout: oscap-run timeout in seconds (default 600). The ssh
            transport calls themselves are uncapped.

    Returns:
        A VerifyReport. Use `report.is_clean` for an at-a-glance pass/fail,
        `report.has_tailoring_drift` for intent-vs-deployed drift, and
        `report.baseline` to see which captured baseline drove the report
        (None means install ARF, or nothing, was used).

    Raises:
        ConfigError(USAGE): both `baseline_path` and `capture_to` set, or
            the baseline path is missing/unreadable/not a regular file.
        SudoPromptError: sudo unavailable — passwordless missing, or wrong password.
        OscapInvocationError: tailoring missing, oscap exit not in {0, 2},
            or `cfg.meta.scap_content` not installed on `host`.
        ArfMissingError: oscap reported success but the ARF file is empty
            or absent, OR the captured baseline file is 0 bytes.
        ArfParseError: ARF text is not well-formed XML or has no TestResult.
        SshConnectError: ssh transport failure.
        ToolMissingError: system `ssh` not on PATH.
        TailoringParseError: malformed deployed or re-rendered tailoring XML
            (only when `check_tailoring=True`). Message names the side.
    """
    if baseline_path is not None and capture_to is not None:
        raise ConfigError(
            "--baseline and --capture-baseline are mutually exclusive",
            ExitCode.USAGE,
        )

    if capture_to is not None and not capture_to.parent.is_dir():
        raise ConfigError(
            f"--capture-baseline parent directory does not exist: {capture_to.parent}",
            ExitCode.USAGE,
        )

    transport: Transport
    if local:
        transport = LocalTransport()
        # NB: derived before preflight; on a root shell getpass.getuser() always resolves.
        host = socket.gethostname()
        user = getpass.getuser()
    else:
        extra_opts = ssh_extra_opts or []
        transport = SshTransport(
            host=host, user=user, ssh_extra_opts=extra_opts, sudo_auth=sudo_auth
        )

    # Load baseline first (fail fast on missing/malformed before any SSH).
    baseline_loaded = read_baseline(baseline_path) if baseline_path is not None else None
    effective_no_drift = no_drift or baseline_loaded is not None

    tailoring_drift = None
    if check_tailoring:
        deployed_xml = collect_deployed_tailoring(transport=transport, workdir=workdir)
        expected_xml = render_tailoring(cfg)
        try:
            parsed_deployed = parse_tailoring_xml(deployed_xml)
        except TailoringParseError as e:
            raise TailoringParseError(
                f"failed to parse deployed tailoring at /root/tailoring.xml: {e}"
            ) from e
        try:
            parsed_expected = parse_tailoring_xml(expected_xml)
        except TailoringParseError as e:
            raise TailoringParseError(
                f"failed to parse re-rendered tailoring (ks-gen renderer bug?): {e}"
            ) from e
        tailoring_drift = compare_tailorings(parsed_expected, parsed_deployed)

    expected = expected_failure_rule_ids(cfg)
    arfs = collect_arfs(
        cfg=cfg,
        transport=transport,
        workdir=workdir,
        no_drift=effective_no_drift,
        timeout=timeout,
    )
    current = parse_arf(arfs.current_text)

    # `install` slot: prefer the loaded baseline; else fall back to the
    # install ARF (when present).
    install: dict[str, RuleResult] | None = None
    if baseline_loaded is not None:
        install = baseline_loaded.results
    elif arfs.install_text is not None:
        install = parse_arf(arfs.install_text)

    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = build_report(
        current=current,
        install=install,
        expected_failures=expected,
        host=host,
        user=user,
        timestamp_utc=timestamp,
    )

    if tailoring_drift is not None:
        report = replace(report, tailoring_drift=tailoring_drift)

    if baseline_loaded is not None:
        baseline_report = BaselineReport(
            path=str(baseline_path),
            captured_utc=baseline_loaded.captured_utc,
            orphans=orphan_rule_ids(baseline_loaded.results, current),
        )
        report = replace(report, baseline=baseline_report)

    if capture_to is not None:
        capture_to.write_text(arfs.current_text, encoding="utf-8", newline="\n")

    return report


__all__ = ["VerifyReport", "run_verify"]
