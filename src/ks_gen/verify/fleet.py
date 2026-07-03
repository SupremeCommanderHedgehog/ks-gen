"""Fleet / batch verify — parse a hosts file and fan out run_verify over SSH."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ks_gen.loader import ConfigError, ExitCode, load_host_config
from ks_gen.verify import run_verify
from ks_gen.verify.auth import SudoAuth
from ks_gen.verify.errors import VerifyError, error_label
from ks_gen.verify.reconcile import VerifyReport

HostStatus = Literal["clean", "verify_fail", "drift", "transport"]


@dataclass(frozen=True)
class HostSpec:
    host: str
    user: str | None
    config_path: Path
    lineno: int


@dataclass(frozen=True)
class HostError:
    label: str
    message: str
    exit_code: ExitCode


@dataclass(frozen=True)
class HostOutcome:
    spec: HostSpec
    report: VerifyReport | None
    error: HostError | None
    user: str | None = None  # resolved SSH user actually used/attempted

    @property
    def status(self) -> HostStatus:
        if self.error is not None:
            if self.error.exit_code == ExitCode.VERIFY_FAIL:
                return "verify_fail"
            return "transport"
        assert self.report is not None
        if not self.report.is_clean:
            return "verify_fail"
        if self.report.has_tailoring_drift:
            return "drift"
        return "clean"


@dataclass(frozen=True)
class FleetReport:
    outcomes: tuple[HostOutcome, ...]

    @property
    def aggregate_exit_code(self) -> int:
        statuses = {o.status for o in self.outcomes}
        if "verify_fail" in statuses:
            return int(ExitCode.VERIFY_FAIL)
        if "transport" in statuses:
            return int(ExitCode.TRANSPORT_FAIL)
        if "drift" in statuses:
            return int(ExitCode.TAILORING_DRIFT)
        return int(ExitCode.OK)

    def status_counts(self) -> dict[str, int]:
        counts = {"clean": 0, "verify_fail": 0, "drift": 0, "transport": 0}
        for o in self.outcomes:
            counts[o.status] += 1
        return counts


@dataclass(frozen=True)
class FleetOptions:
    no_drift: bool
    check_tailoring: bool
    ssh_extra_opts: list[str]
    timeout: int
    sudo_auth: SudoAuth
    fleet_user: str | None


def parse_hosts_file(path: Path) -> list[HostSpec]:
    """Parse a fleet hosts file into validated HostSpecs.

    Each non-blank, non-`#` line holds exactly two whitespace-separated
    fields: `[user@]host` and a path to that host's host.yaml (resolved
    relative to the hosts file's own directory). Blank lines and full-line
    `#` comments are skipped.

    The hosts file is operator-authored, so all authoring errors — a line
    without exactly two fields, a missing/unreadable config, or a config
    that fails to load — are collected and raised together as one
    ConfigError(USAGE) naming every offending line, before any SSH runs.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"cannot read hosts file {path}: {e}", ExitCode.USAGE) from e

    base = path.parent
    specs: list[HostSpec] = []
    errors: list[str] = []

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 2:
            errors.append(
                f"line {lineno}: expected '<[user@]host> <config.yaml>', got {len(fields)} field(s)"
            )
            continue
        target, cfg_field = fields
        user: str | None = None
        host = target
        if "@" in target:
            user, host = target.split("@", 1)
            if not user or not host:
                errors.append(f"line {lineno}: malformed user@host: {target!r}")
                continue
        cfg_path = (base / cfg_field).resolve()
        if not cfg_path.is_file():
            errors.append(f"line {lineno}: config not found: {cfg_field}")
            continue
        try:
            load_host_config(cfg_path, sets=[])
        except ConfigError as e:
            errors.append(f"line {lineno}: config {cfg_field} failed to load: {e}")
            continue
        specs.append(HostSpec(host=host, user=user, config_path=cfg_path, lineno=lineno))

    if errors:
        raise ConfigError("invalid hosts file:\n  " + "\n  ".join(errors), ExitCode.USAGE)
    if not specs:
        raise ConfigError(f"hosts file has no host entries: {path}", ExitCode.USAGE)
    return specs


def run_fleet(
    specs: list[HostSpec],
    *,
    jobs: int,
    verify_one: Callable[[HostSpec], HostOutcome],
) -> FleetReport:
    """Run `verify_one` for every spec concurrently and collect outcomes.

    Concurrency is capped at `jobs` worker threads (threads, not processes:
    the per-host work is subprocess/SSH-bound, so the GIL is released during
    `subprocess.run`). A `verify_one` that raises is caught and recorded as a
    transport-class `HostError` so one dead host never aborts the fleet.
    Outcomes are returned in the input `specs` order regardless of completion
    order, for deterministic output.
    """
    results: dict[int, HostOutcome] = {}

    def _guarded(index: int, spec: HostSpec) -> None:
        try:
            results[index] = verify_one(spec)
        except Exception as e:  # isolation is the whole point
            results[index] = HostOutcome(
                spec=spec,
                report=None,
                error=HostError(
                    label=error_label(e),
                    message=str(e),
                    exit_code=ExitCode.TRANSPORT_FAIL,
                ),
            )

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        for i, spec in enumerate(specs):
            pool.submit(_guarded, i, spec)

    return FleetReport(outcomes=tuple(results[i] for i in range(len(specs))))


def make_verify_one(opts: FleetOptions) -> Callable[[HostSpec], HostOutcome]:
    """Build the per-host worker `run_fleet` fans out.

    Each call loads the host's config, resolves its SSH user
    (inline user@ > opts.fleet_user > cfg.user.admin.name), runs the
    single-host `run_verify` in a fresh temp workdir, and converts any
    VerifyError / ConfigError into a transport-class HostOutcome. The temp
    dir is cleaned up on exit; ARFs are not persisted in fleet mode.
    """

    def verify_one(spec: HostSpec) -> HostOutcome:
        try:
            cfg = load_host_config(spec.config_path, sets=[])
        except (VerifyError, ConfigError) as e:
            # cfg unavailable — resolve user as far as we can
            return HostOutcome(
                spec=spec,
                report=None,
                error=HostError(label=error_label(e), message=str(e), exit_code=e.exit_code),
                user=spec.user or opts.fleet_user,
            )
        user = spec.user or opts.fleet_user or cfg.user.admin.name
        try:
            with tempfile.TemporaryDirectory(prefix="ksgen-fleet-") as tmp:
                report = run_verify(
                    cfg=cfg,
                    host=spec.host,
                    user=user,
                    workdir=Path(tmp),
                    no_drift=opts.no_drift,
                    check_tailoring=opts.check_tailoring,
                    ssh_extra_opts=opts.ssh_extra_opts,
                    timeout=opts.timeout,
                    sudo_auth=opts.sudo_auth,
                )
            return HostOutcome(spec=spec, report=report, error=None, user=user)
        except (VerifyError, ConfigError) as e:
            return HostOutcome(
                spec=spec,
                report=None,
                error=HostError(label=error_label(e), message=str(e), exit_code=e.exit_code),
                user=user,
            )

    return verify_one
