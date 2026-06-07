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
    fetch_idx = text.find(
        "%post --nochroot --erroronfail --log=/mnt/sysimage/root/ks-post-oscap-fetch.log"
    )
    oscap_idx = text.find("%post --erroronfail --log=/root/ks-post-oscap.log")
    if fetch_idx == -1:
        failures.append("missing: %post --nochroot oscap fetch block")
    if oscap_idx == -1:
        failures.append("missing: %post oscap remediation block")
    else:
        if "oscap xccdf eval --remediate" not in text[oscap_idx:]:
            failures.append("missing: oscap remediation invocation in %post oscap block")
        if "--tailoring-file /root/tailoring.xml" not in text[oscap_idx:]:
            failures.append("missing: --tailoring-file reference in %post oscap block")
        if "--fetch-remote-resources" not in text[oscap_idx:]:
            failures.append("missing: --fetch-remote-resources flag in %post oscap block")
    # If both blocks are present, check ordering and fetch-region content.
    if fetch_idx != -1 and oscap_idx != -1:
        if fetch_idx >= oscap_idx:
            failures.append("ordering: oscap fetch block must precede oscap eval block")
        else:
            fetch_region = text[fetch_idx:oscap_idx]
            if "hd:LABEL=*)" not in fetch_region:
                failures.append("missing: hd:LABEL= branch in oscap fetch case")
            if (
                "cp /run/install/repo/tailoring.xml /mnt/sysimage/root/tailoring.xml"
                not in fetch_region
            ):
                failures.append("missing: hd: cp from /run/install/repo in oscap fetch case")
    return failures


def lint_kickstart(path: Path) -> LintReport:
    text = Path(path).read_text(encoding="utf-8")
    ok, msg = _ksvalidator_ok(path)
    failures = [] if ok else [msg]
    failures.extend(_internal_checks(text))
    return LintReport(ok=not failures, failures=failures)
