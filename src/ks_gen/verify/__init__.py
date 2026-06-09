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

    Returns:
        A VerifyReport. Use `report.is_clean` for compliance and
        `report.has_tailoring_drift` for intent-vs-deployed drift.

    Raises:
        SudoPromptError, OscapInvocationError, ArfMissingError, ArfParseError,
        SshConnectError, ToolMissingError: same as v0.8.0.
        TailoringParseError: malformed deployed or re-rendered tailoring XML
            (only when `check_tailoring=True`). Message names the side.
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
