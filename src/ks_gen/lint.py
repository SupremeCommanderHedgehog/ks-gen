from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LintReport:
    ok: bool
    failures: list[str] = field(default_factory=list)


def _ksvalidator_ok(path: Path) -> tuple[bool, str]:
    try:
        from pykickstart.parser import KickstartParser
        from pykickstart.version import makeVersion
    except ImportError as e:
        return False, f"pykickstart unavailable: {e}"
    try:
        parser = KickstartParser(makeVersion())
        parser.readKickstart(str(path))
        return True, ""
    except Exception as e:
        return False, f"ksvalidator: {e}"


def _internal_checks(text: str) -> list[str]:
    failures: list[str] = []
    if "authorized_keys" not in text:
        failures.append("missing: authorized_keys write in %post")
    a = text.find("# ===== admin_user_and_keys =====")
    s = text.find("# ===== ssh_config_apply =====")
    if a == -1:
        failures.append("missing: admin_user_and_keys post block")
    if s == -1:
        failures.append("missing: ssh_config_apply post block")
    if a != -1 and s != -1 and a >= s:
        failures.append("ordering: admin_user_and_keys must precede ssh_config_apply")
    if "tailoring-path = /tailoring.xml" not in text:
        failures.append("missing: %addon does not reference tailoring.xml")
    return failures


def lint_kickstart(path: Path) -> LintReport:
    text = Path(path).read_text(encoding="utf-8")
    ok, msg = _ksvalidator_ok(path)
    failures = [] if ok else [msg]
    failures.extend(_internal_checks(text))
    return LintReport(ok=not failures, failures=failures)
