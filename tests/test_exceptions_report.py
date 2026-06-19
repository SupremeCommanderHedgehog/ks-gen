from ks_gen.exceptions_report import render_exceptions_md
from ks_gen.registry import load_rules
from ks_gen.topo import topo_sort


def test_report_lists_applied_rules(minimal_cfg):
    rules = [r for r in topo_sort(load_rules(minimal_cfg.distro)) if r.applies(minimal_cfg)]
    md = render_exceptions_md(minimal_cfg, rules)
    assert "# Exceptions report" in md
    assert "admin_user_and_keys" in md
    assert "crypto_policy" in md


def test_report_lists_disabled_xccdf_rules(minimal_cfg):
    rules = [r for r in topo_sort(load_rules(minimal_cfg.distro)) if r.applies(minimal_cfg)]
    md = render_exceptions_md(minimal_cfg, rules)
    assert "banner_etc_issue" in md
    assert "sshd_use_approved_ciphers" in md


def test_report_includes_declared_exceptions(minimal_cfg):
    from ks_gen.config import ExceptionDecl

    cfg = minimal_cfg.model_copy(
        update={
            "exceptions": [
                ExceptionDecl(
                    id="no-luks",
                    reason="Cloud volumes encrypted by provider.",
                    stig_rules_disabled=["xccdf_org.ssgproject.content_rule_encrypt_partitions"],
                )
            ]
        }
    )
    rules = [r for r in topo_sort(load_rules(cfg.distro)) if r.applies(cfg)]
    md = render_exceptions_md(cfg, rules)
    assert "no-luks" in md
    assert "encrypt_partitions" in md


def test_report_counts_summary(minimal_cfg):
    rules = [r for r in topo_sort(load_rules(minimal_cfg.distro)) if r.applies(minimal_cfg)]
    md = render_exceptions_md(minimal_cfg, rules)
    assert "Applied rules:" in md
    assert "Tailored XCCDF rules:" in md
    assert "Declared exceptions:" in md


def test_expected_failure_rule_ids_includes_rule_exceptions(minimal_cfg):
    from ks_gen.exceptions_report import expected_failure_rule_ids

    ids = expected_failure_rule_ids(minimal_cfg)
    assert "xccdf_org.ssgproject.content_rule_banner_etc_issue" in ids
    assert "xccdf_org.ssgproject.content_rule_sshd_use_approved_ciphers" in ids


def test_expected_failure_rule_ids_includes_declared_exceptions(minimal_cfg):
    from ks_gen.config import ExceptionDecl
    from ks_gen.exceptions_report import expected_failure_rule_ids

    cfg = minimal_cfg.model_copy(
        update={
            "exceptions": [
                ExceptionDecl(
                    id="no-luks",
                    reason="Cloud volumes encrypted by provider.",
                    stig_rules_disabled=["xccdf_org.ssgproject.content_rule_encrypt_partitions"],
                )
            ]
        }
    )
    ids = expected_failure_rule_ids(cfg)
    assert "xccdf_org.ssgproject.content_rule_encrypt_partitions" in ids


def test_expected_failure_rule_ids_returns_a_set(minimal_cfg):
    from ks_gen.exceptions_report import expected_failure_rule_ids

    ids = expected_failure_rule_ids(minimal_cfg)
    assert isinstance(ids, set)
    assert all(isinstance(rid, str) for rid in ids)
