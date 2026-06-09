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


def test_run_verify_capture_to_writes_current_arf(tmp_path: Path) -> None:
    """When capture_to is set, the current ARF is written to that path."""
    from ks_gen.verify import run_verify
    from ks_gen.verify.remote import CollectedArfs

    current = (FIXTURES / "arf-clean.xml").read_text(encoding="utf-8")
    install = (FIXTURES / "arf-install-baseline.xml").read_text(encoding="utf-8")
    out = tmp_path / "captured.arf.xml"

    with patch(
        "ks_gen.verify.collect_arfs",
        return_value=CollectedArfs(current_text=current, install_text=install),
    ):
        report = run_verify(
            cfg=_cfg(),
            host="h",
            user="ops",
            workdir=tmp_path,
            capture_to=out,
            ssh_extra_opts=[],
            timeout=600,
        )

    assert out.exists()
    assert out.read_text(encoding="utf-8") == current
    assert report.baseline is None  # capture mode doesn't populate baseline


def test_run_verify_baseline_path_uses_file_instead_of_install(tmp_path: Path) -> None:
    """When baseline_path is set, the captured file replaces install ARF and
    collect_arfs is called with no_drift=True."""
    from ks_gen.verify import run_verify
    from ks_gen.verify.remote import CollectedArfs

    current = (FIXTURES / "arf-mixed.xml").read_text(encoding="utf-8")
    baseline_arf = (FIXTURES / "arf-install-baseline.xml").read_text(encoding="utf-8")
    baseline_path = tmp_path / "baseline.arf.xml"
    baseline_path.write_text(baseline_arf, encoding="utf-8")

    captured_kwargs: dict[str, object] = {}

    def fake_collect(**kwargs: object) -> CollectedArfs:
        captured_kwargs.update(kwargs)
        return CollectedArfs(current_text=current, install_text=None)

    with patch("ks_gen.verify.collect_arfs", side_effect=fake_collect):
        report = run_verify(
            cfg=_cfg(),
            host="h",
            user="ops",
            workdir=tmp_path,
            baseline_path=baseline_path,
            ssh_extra_opts=[],
            timeout=600,
        )

    assert captured_kwargs["no_drift"] is True
    assert report.baseline is not None
    assert report.baseline.path == str(baseline_path)
    # rule_e was pass in install baseline, fail in mixed → regression
    by_id = {r.rule_id: r for r in report.rows}
    assert by_id["xccdf_org.ssgproject.content_rule_rule_e"].category == "regression"


def test_run_verify_baseline_path_populates_orphans(tmp_path: Path) -> None:
    """Stale baseline: rules in baseline absent from current become orphans."""
    from ks_gen.verify import run_verify
    from ks_gen.verify.remote import CollectedArfs

    # Build a current ARF with only rule_a; baseline has rule_a + rule_stale.
    current_xml = (
        '<?xml version="1.0"?>'
        '<TestResult xmlns="http://checklists.nist.gov/xccdf/1.2">'
        '<rule-result idref="xccdf_org.ssgproject.content_rule_rule_a">'
        "<result>pass</result>"
        "</rule-result>"
        "</TestResult>"
    )
    baseline_xml = (
        '<?xml version="1.0"?>'
        '<TestResult xmlns="http://checklists.nist.gov/xccdf/1.2">'
        '<rule-result idref="xccdf_org.ssgproject.content_rule_rule_a">'
        "<result>pass</result>"
        "</rule-result>"
        '<rule-result idref="xccdf_org.ssgproject.content_rule_rule_stale">'
        "<result>pass</result>"
        "</rule-result>"
        "</TestResult>"
    )
    baseline_path = tmp_path / "stale.arf.xml"
    baseline_path.write_text(baseline_xml, encoding="utf-8")

    with patch(
        "ks_gen.verify.collect_arfs",
        return_value=CollectedArfs(current_text=current_xml, install_text=None),
    ):
        report = run_verify(
            cfg=_cfg(),
            host="h",
            user="ops",
            workdir=tmp_path,
            baseline_path=baseline_path,
            ssh_extra_opts=[],
            timeout=600,
        )

    assert report.baseline is not None
    assert report.baseline.orphans == ("xccdf_org.ssgproject.content_rule_rule_stale",)


def test_run_verify_baseline_path_and_capture_to_both_set_raises(tmp_path: Path) -> None:
    """Library-layer mutual-exclusion check."""
    import pytest

    from ks_gen.loader import ConfigError, ExitCode
    from ks_gen.verify import run_verify

    baseline_path = tmp_path / "b.arf"
    capture_to = tmp_path / "c.arf"
    baseline_path.write_text("<TestResult/>", encoding="utf-8")

    with pytest.raises(ConfigError) as exc_info:
        run_verify(
            cfg=_cfg(),
            host="h",
            user="ops",
            workdir=tmp_path,
            baseline_path=baseline_path,
            capture_to=capture_to,
            ssh_extra_opts=[],
            timeout=600,
        )
    assert exc_info.value.exit_code == ExitCode.USAGE
    assert "mutually exclusive" in str(exc_info.value)


def test_run_verify_capture_to_parent_missing_raises_config_error(tmp_path: Path) -> None:
    """capture_to with a nonexistent parent dir should raise ConfigError(USAGE)
    before any SSH or file I/O."""
    import pytest

    from ks_gen.loader import ConfigError, ExitCode
    from ks_gen.verify import run_verify

    out = tmp_path / "does-not-exist" / "captured.arf"

    with pytest.raises(ConfigError) as exc_info:
        run_verify(
            cfg=_cfg(),
            host="h",
            user="ops",
            workdir=tmp_path,
            capture_to=out,
            ssh_extra_opts=[],
            timeout=600,
        )
    assert exc_info.value.exit_code == ExitCode.USAGE
    assert "parent directory" in str(exc_info.value)


def test_run_verify_baseline_path_composes_with_check_tailoring(tmp_path: Path) -> None:
    """When both --baseline and --check-tailoring are set, BaselineReport AND
    TailoringDriftReport are both attached. Compliance reconcile uses the
    captured baseline; tailoring drift compares against the host."""
    from ks_gen.tailoring import build_tailoring_xml
    from ks_gen.verify import run_verify
    from ks_gen.verify.remote import CollectedArfs
    from ks_gen.writer import render_tailoring

    current = (FIXTURES / "arf-clean.xml").read_text(encoding="utf-8")
    baseline_arf = (FIXTURES / "arf-install-baseline.xml").read_text(encoding="utf-8")
    baseline_path = tmp_path / "b.arf.xml"
    baseline_path.write_text(baseline_arf, encoding="utf-8")

    cfg = _cfg()
    # Synthetic deployed tailoring: matches cfg + one extra disable → drift.
    deployed_xml = build_tailoring_xml(
        [TailoringOp("xccdf_org.ssgproject.content_rule_synthetic_drift", "disable")],
        profile_id="xccdf_org.ssgproject.content_profile_stig",
    )
    _ = render_tailoring(cfg)  # warm any deferred imports — matches existing test pattern

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
            check_tailoring=True,
            baseline_path=baseline_path,
            ssh_extra_opts=[],
            timeout=600,
        )

    # Both attached.
    assert report.baseline is not None
    assert report.baseline.path == str(baseline_path)
    assert report.tailoring_drift is not None
    assert report.has_tailoring_drift is True
