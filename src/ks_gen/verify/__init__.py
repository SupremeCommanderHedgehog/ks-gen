"""Post-install host verification — re-run oscap, reconcile against host.yaml."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from ks_gen.config import HostConfig
from ks_gen.exceptions_report import expected_failure_rule_ids
from ks_gen.verify.arf import parse_arf
from ks_gen.verify.errors import TailoringParseError
from ks_gen.verify.reconcile import VerifyReport, build_report
from ks_gen.verify.remote import collect_arfs, collect_deployed_tailoring
from ks_gen.verify.tailoring_drift import (
    compare_tailorings,
    parse_tailoring_xml,
)
from ks_gen.writer import render_tailoring


def run_verify(
    *,
    cfg: HostConfig,
    host: str,
    user: str,
    workdir: Path,
    no_drift: bool = False,
    check_tailoring: bool = False,
    ssh_extra_opts: list[str] | None = None,
    timeout: int = 600,
) -> VerifyReport:
    """Re-run oscap on `host` and reconcile against `cfg`'s exception set.

    SSHs to `host` as `user` (requires passwordless sudo), runs
    `oscap xccdf eval` against the install-time `/root/tailoring.xml`, pulls
    both the fresh ARF and (unless `no_drift`) the install-time ARF at
    `/root/oscap-remediation-results.xml`, then categorizes each rule as
    clean / expected_fail / new_fail / regression / incomplete.

    When `check_tailoring` is True, also pulls `/root/tailoring.xml`, re-renders
    the expected tailoring from `cfg`, and attaches a `TailoringDriftReport` to
    the returned report. The pull happens before the compliance run so a
    missing tailoring fails fast.

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
            returned report has `install_baseline_available=False`.
        check_tailoring: when True, pull `/root/tailoring.xml` from `host`,
            re-render the expected tailoring from `cfg`, and attach a
            `TailoringDriftReport` to the returned report. The pull happens
            before the compliance run so a missing tailoring fails fast.
        ssh_extra_opts: extra args appended to every `ssh`/`scp` invocation
            (e.g. `["-F", "/path/to/ssh_config"]`). `None` is normalized to
            an empty list.
        timeout: oscap-run timeout in seconds (default 600). The ssh and
            scp transport calls themselves are uncapped.

    Returns:
        A VerifyReport. Use `report.is_clean` for an at-a-glance pass/fail
        and `report.has_tailoring_drift` for intent-vs-deployed drift.

    Raises:
        SudoPromptError: passwordless sudo unavailable for `user` on `host`.
        OscapInvocationError: tailoring missing, oscap exit not in {0, 2},
            or `cfg.meta.scap_content` not installed on `host`.
        ArfMissingError: oscap reported success but the ARF file is empty
            or absent.
        ArfParseError: ARF text is not well-formed XML or has no TestResult.
        SshConnectError: ssh/scp transport failure.
        ToolMissingError: system `ssh` or `scp` not on PATH.
        TailoringParseError: malformed deployed or re-rendered tailoring XML
            (only when `check_tailoring=True`). Message names the side
            ("deployed tailoring at /root/tailoring.xml" or "re-rendered
            tailoring") so the operator knows whether to suspect host
            tampering or a ks-gen renderer regression.
    """
    extra_opts = ssh_extra_opts or []

    tailoring_drift = None
    if check_tailoring:
        deployed_xml = collect_deployed_tailoring(
            host=host,
            user=user,
            workdir=workdir,
            ssh_extra_opts=extra_opts,
        )
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
        host=host,
        user=user,
        workdir=workdir,
        no_drift=no_drift,
        ssh_extra_opts=extra_opts,
        timeout=timeout,
    )
    current = parse_arf(arfs.current_text)
    install = parse_arf(arfs.install_text) if arfs.install_text is not None else None
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
        # VerifyReport is frozen — rebuild with the new field.
        report = replace(report, tailoring_drift=tailoring_drift)
    return report


__all__ = ["VerifyReport", "run_verify"]
