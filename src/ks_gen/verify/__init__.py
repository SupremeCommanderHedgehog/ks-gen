"""Post-install host verification — re-run oscap, reconcile against host.yaml."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from ks_gen.config import HostConfig
from ks_gen.exceptions_report import expected_failure_rule_ids
from ks_gen.verify.arf import parse_arf
from ks_gen.verify.reconcile import VerifyReport, build_report
from ks_gen.verify.remote import collect_arfs


def run_verify(
    *,
    cfg: HostConfig,
    host: str,
    user: str,
    workdir: Path,
    no_drift: bool = False,
    ssh_extra_opts: list[str] | None = None,
    timeout: int = 600,
) -> VerifyReport:
    expected = expected_failure_rule_ids(cfg)
    arfs = collect_arfs(
        cfg=cfg,
        host=host,
        user=user,
        workdir=workdir,
        no_drift=no_drift,
        ssh_extra_opts=ssh_extra_opts or [],
        timeout=timeout,
    )
    current = parse_arf(arfs.current_text)
    install = parse_arf(arfs.install_text) if arfs.install_text else None
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return build_report(
        current=current,
        install=install,
        expected_failures=expected,
        host=host,
        user=user,
        timestamp_utc=timestamp,
    )


__all__ = ["run_verify"]
