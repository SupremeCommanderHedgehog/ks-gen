from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from ks_gen.config import AdminUser, ExceptionDecl, HostConfig, System, User
from ks_gen.rules._types import TailoringOp
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


def test_run_verify_check_tailoring_false_leaves_field_none(tmp_path: Path) -> None:
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
            check_tailoring=False,
            ssh_extra_opts=[],
            timeout=600,
        )

    assert report.tailoring_drift is None


def test_run_verify_check_tailoring_true_attaches_drift_report(tmp_path: Path) -> None:
    from ks_gen.tailoring import build_tailoring_xml

    current = (FIXTURES / "arf-clean.xml").read_text(encoding="utf-8")
    # Hand-craft a "deployed" tailoring with an extra disable op — drift.
    deployed_xml = build_tailoring_xml(
        [
            TailoringOp(
                rule_id="xccdf_org.ssgproject.content_rule_synthetic_drift",
                action="disable",
            )
        ],
        profile_id="xccdf_org.ssgproject.content_profile_stig",
    )

    with (
        patch(
            "ks_gen.verify.collect_arfs",
            return_value=CollectedArfs(current_text=current, install_text=None),
        ),
        patch(
            "ks_gen.verify.collect_deployed_tailoring",
            return_value=deployed_xml,
        ),
    ):
        report = run_verify(
            cfg=_cfg(),
            host="h",
            user="ops",
            workdir=tmp_path,
            no_drift=True,
            check_tailoring=True,
            ssh_extra_opts=[],
            timeout=600,
        )

    assert report.tailoring_drift is not None
    # The synthetic_drift rule is in deployed but not expected → removed.
    assert any(
        op.rule_id == "xccdf_org.ssgproject.content_rule_synthetic_drift"
        for op in report.tailoring_drift.removed
    )
    assert report.has_tailoring_drift is True


def test_run_verify_check_tailoring_true_clean_when_matching(tmp_path: Path) -> None:
    from ks_gen.writer import render_tailoring

    cfg = _cfg()
    current = (FIXTURES / "arf-clean.xml").read_text(encoding="utf-8")
    deployed_xml = render_tailoring(cfg)

    with (
        patch(
            "ks_gen.verify.collect_arfs",
            return_value=CollectedArfs(current_text=current, install_text=None),
        ),
        patch(
            "ks_gen.verify.collect_deployed_tailoring",
            return_value=deployed_xml,
        ),
    ):
        report = run_verify(
            cfg=cfg,
            host="h",
            user="ops",
            workdir=tmp_path,
            no_drift=True,
            check_tailoring=True,
            ssh_extra_opts=[],
            timeout=600,
        )

    assert report.tailoring_drift is not None
    assert report.has_tailoring_drift is False


def test_run_verify_wraps_deployed_parse_failure_with_side_name(tmp_path: Path) -> None:
    """When the deployed XML fails to parse, the raised TailoringParseError
    names the deployed side so the operator knows where to look."""
    import pytest

    from ks_gen.verify.errors import TailoringParseError

    cfg = _cfg()

    with (
        patch(
            "ks_gen.verify.collect_arfs",
            return_value=CollectedArfs(current_text="<TestResult/>", install_text=None),
        ),
        patch(
            "ks_gen.verify.collect_deployed_tailoring",
            return_value="<not-xml",  # garbage; parse_tailoring_xml will raise
        ),
        pytest.raises(TailoringParseError, match=r"deployed tailoring at /root/tailoring\.xml"),
    ):
        run_verify(
            cfg=cfg,
            host="h",
            user="ops",
            workdir=tmp_path,
            no_drift=True,
            check_tailoring=True,
            ssh_extra_opts=[],
            timeout=600,
        )


def test_run_verify_wraps_expected_parse_failure_with_renderer_message(tmp_path: Path) -> None:
    """When the re-rendered XML fails to parse (renderer bug), the raised
    TailoringParseError names the renderer side."""
    import pytest

    from ks_gen.verify.errors import TailoringParseError
    from ks_gen.writer import render_tailoring

    cfg = _cfg()
    # Build a valid deployed XML; corrupt the renderer output by patching it.
    deployed_xml = render_tailoring(cfg)

    with (
        patch(
            "ks_gen.verify.collect_arfs",
            return_value=CollectedArfs(current_text="<TestResult/>", install_text=None),
        ),
        patch(
            "ks_gen.verify.collect_deployed_tailoring",
            return_value=deployed_xml,
        ),
        patch(
            "ks_gen.verify.render_tailoring",
            return_value="<garbage-from-renderer",
        ),
        pytest.raises(TailoringParseError, match="re-rendered tailoring"),
    ):
        run_verify(
            cfg=cfg,
            host="h",
            user="ops",
            workdir=tmp_path,
            no_drift=True,
            check_tailoring=True,
            ssh_extra_opts=[],
            timeout=600,
        )
