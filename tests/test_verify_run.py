from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from ks_gen.config import AdminUser, ExceptionDecl, HostConfig, System, User
from ks_gen.verify import run_verify
from ks_gen.verify.remote import CollectedArfs

FIXTURES = Path(__file__).parent / "fixtures"


def _cfg() -> HostConfig:
    return HostConfig(
        system=System(hostname="h"),
        user=User(admin=AdminUser(name="ops", authorized_keys=["k a@b"], sudo="nopasswd_yes")),
        exceptions=[
            ExceptionDecl(
                id="rule-d-accepted",
                reason="known-failing on STIG-strict cloud baseline",
                stig_rules_disabled=["xccdf_org.ssgproject.content_rule_rule_d"],
            ),
        ],
    )


def test_run_verify_end_to_end_drives_real_arf_through_reconcile(tmp_path: Path) -> None:
    current = (FIXTURES / "arf-mixed.xml").read_text(encoding="utf-8")
    install = (FIXTURES / "arf-install-baseline.xml").read_text(encoding="utf-8")

    with patch(
        "ks_gen.verify.collect_arfs",
        return_value=CollectedArfs(current_text=current, install_text=install),
    ):
        report = run_verify(
            cfg=_cfg(),
            host="h",
            user="ops",
            workdir=tmp_path,
            no_drift=False,
            ssh_extra_opts=[],
            timeout=600,
        )

    by_id = {r.rule_id: r for r in report.rows}
    # rule_d declared as exception → expected_fail
    assert by_id["xccdf_org.ssgproject.content_rule_rule_d"].category == "expected_fail"
    # rule_e: install=pass, current=fail, no exception → regression
    assert by_id["xccdf_org.ssgproject.content_rule_rule_e"].category == "regression"
    # rule_f: install=pass, current=error → incomplete
    assert by_id["xccdf_org.ssgproject.content_rule_rule_f"].category == "incomplete"
    # rule_a/b/c: pass → clean
    for rid in ("rule_a", "rule_b", "rule_c"):
        assert by_id[f"xccdf_org.ssgproject.content_rule_{rid}"].category == "clean"
    assert report.install_baseline_available is True
    assert report.is_clean is False


def test_run_verify_install_text_none_degrades_gracefully(tmp_path: Path) -> None:
    current = (FIXTURES / "arf-clean.xml").read_text(encoding="utf-8")
    with patch(
        "ks_gen.verify.collect_arfs",
        return_value=CollectedArfs(current_text=current, install_text=None),
    ):
        report = run_verify(
            cfg=_cfg(),
            host="h",
            user="ops",
            workdir=tmp_path,
            no_drift=True,
            ssh_extra_opts=[],
            timeout=600,
        )
    assert report.install_baseline_available is False
    assert report.is_clean is True
