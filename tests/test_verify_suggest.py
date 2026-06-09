from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml
from syrupy.assertion import SnapshotAssertion

from ks_gen.verify.errors import SuggestApplyError
from ks_gen.verify.reconcile import VerifyReport, VerifyRow
from ks_gen.verify.suggest import (
    AppendResult,
    Suggestion,
    apply_to_host_yaml,
    build_suggestions,
    render_yaml,
)


def _report(*rows: VerifyRow, host: str = "h1") -> VerifyReport:
    return VerifyReport(
        host=host,
        user="ops",
        timestamp_utc="2026-06-09T12:00:00Z",
        rows=tuple(rows),
        install_baseline_available=True,
    )


def test_build_suggestions_filters_to_new_fail_and_regression():
    report = _report(
        VerifyRow("rule_a", "pass", "pass", False, "clean"),
        VerifyRow("rule_b", "fail", "fail", True, "expected_fail"),
        VerifyRow("rule_c", "error", None, False, "incomplete"),
        VerifyRow("rule_d", "fail", "fail", False, "new_fail"),
        VerifyRow("rule_e", "fail", "pass", False, "regression"),
    )
    out = build_suggestions(report)
    # only rule_d (new_fail) and rule_e (regression) become suggestions
    assert [s.decl.stig_rules_disabled[0] for s in out] == ["rule_d", "rule_e"]
    assert [s.category for s in out] == ["new_fail", "regression"]


def test_build_suggestions_id_format():
    report = _report(
        VerifyRow("rule_d", "fail", "fail", False, "new_fail"),
        VerifyRow("rule_e", "fail", "pass", False, "regression"),
    )
    out = build_suggestions(report)
    assert out[0].decl.id == "auto-new_fail-rule_d"
    assert out[1].decl.id == "auto-regression-rule_e"


def test_build_suggestions_reason_carries_run_context():
    report = _report(
        VerifyRow("rule_d", "fail", "pass", False, "regression"),
        host="web01.example.com",
    )
    suggestion = build_suggestions(report)[0]
    reason = suggestion.decl.reason
    assert reason.startswith("TODO:")
    assert "web01.example.com" in reason
    assert "2026-06-09" in reason
    assert "current=fail" in reason
    assert "install=pass" in reason
    assert "category=regression" in reason


def test_build_suggestions_stig_rules_disabled_is_single_id():
    report = _report(VerifyRow("rule_d", "fail", "fail", False, "new_fail"))
    suggestion = build_suggestions(report)[0]
    assert suggestion.decl.stig_rules_disabled == ["rule_d"]


def test_build_suggestions_empty_report_returns_empty_list():
    report = _report(VerifyRow("rule_a", "pass", "pass", False, "clean"))
    assert build_suggestions(report) == []


def test_build_suggestions_order_matches_report_row_order():
    # build_report sorts by rule_id; build_suggestions preserves that order
    report = _report(
        VerifyRow("rule_a", "fail", "fail", False, "new_fail"),
        VerifyRow("rule_b", "fail", "pass", False, "regression"),
        VerifyRow("rule_c", "fail", "fail", False, "new_fail"),
    )
    out = build_suggestions(report)
    assert [s.decl.stig_rules_disabled[0] for s in out] == ["rule_a", "rule_b", "rule_c"]


# --- render_yaml tests -----------------------------------------------------


def test_render_yaml_empty_suggestions_returns_empty_string():
    report = _report(VerifyRow("rule_a", "pass", "pass", False, "clean"))
    assert render_yaml([], report) == ""


def test_render_yaml_mixed_categories(snapshot: SnapshotAssertion):
    report = _report(
        VerifyRow("xccdf_rule_d", "fail", "fail", False, "new_fail"),
        VerifyRow("xccdf_rule_e", "fail", "pass", False, "regression"),
        host="web01.example.com",
    )
    suggestions = build_suggestions(report)
    assert render_yaml(suggestions, report) == snapshot


def test_render_yaml_header_includes_run_context():
    report = _report(
        VerifyRow("rule_d", "fail", "fail", False, "new_fail"),
        host="web01.example.com",
    )
    suggestions = build_suggestions(report)
    out = render_yaml(suggestions, report)
    assert out.startswith("## Suggested exception entries")
    assert "web01.example.com" in out
    assert "2026-06-09T12:00:00Z" in out
    assert "1 suggestion" in out  # singular


def test_render_yaml_header_pluralizes_count():
    report = _report(
        VerifyRow("rule_d", "fail", "fail", False, "new_fail"),
        VerifyRow("rule_e", "fail", "pass", False, "regression"),
    )
    out = render_yaml(build_suggestions(report), report)
    assert "2 suggestions" in out


# --- apply_to_host_yaml tests ---------------------------------------------

_BASE_HOST_YAML = textwrap.dedent(
    """\
    system: {hostname: h1}
    user:
      admin:
        name: ops
        authorized_keys: ["ssh-ed25519 A a@b"]
        sudo: nopasswd_yes
    """
)


def _write_host_yaml(tmp_path: Path, text: str = _BASE_HOST_YAML) -> Path:
    p = tmp_path / "host.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def _new_fail_report() -> VerifyReport:
    return _report(
        VerifyRow("rule_d", "fail", "fail", False, "new_fail"),
        VerifyRow("rule_e", "fail", "pass", False, "regression"),
    )


def test_apply_appends_new_fail_to_empty_exceptions(tmp_path: Path):
    host_yaml = _write_host_yaml(tmp_path)
    suggestions = build_suggestions(_new_fail_report())

    result = apply_to_host_yaml(
        suggestions=suggestions,
        host_yaml_path=host_yaml,
        allow_regression=False,
    )

    assert isinstance(result, AppendResult)
    assert result.added == ("auto-new_fail-rule_d",)
    assert result.skipped_existing == ()
    assert result.skipped_regression == ("auto-regression-rule_e",)
    assert result.path == host_yaml
    assert result.backup_path == host_yaml.with_suffix(".yaml.bak")

    after = yaml.safe_load(host_yaml.read_text(encoding="utf-8"))
    assert len(after["exceptions"]) == 1
    assert after["exceptions"][0]["id"] == "auto-new_fail-rule_d"
    assert after["exceptions"][0]["stig_rules_disabled"] == ["rule_d"]


def test_apply_is_idempotent_when_id_already_present(tmp_path: Path):
    host_yaml = _write_host_yaml(tmp_path)
    suggestions = build_suggestions(_new_fail_report())

    # First apply: writes one suggestion.
    apply_to_host_yaml(suggestions=suggestions, host_yaml_path=host_yaml, allow_regression=False)
    mtime_after_first = host_yaml.stat().st_mtime_ns

    # Second apply with same suggestions: nothing to add (already present).
    result = apply_to_host_yaml(
        suggestions=suggestions, host_yaml_path=host_yaml, allow_regression=False
    )

    assert result.added == ()
    assert result.skipped_existing == ("auto-new_fail-rule_d",)
    assert result.skipped_regression == ("auto-regression-rule_e",)
    assert host_yaml.stat().st_mtime_ns == mtime_after_first  # no second write


def test_apply_preserves_pre_existing_exceptions(tmp_path: Path):
    pre = textwrap.dedent(
        """\
        system: {hostname: h1}
        user:
          admin:
            name: ops
            authorized_keys: ["ssh-ed25519 A a@b"]
            sudo: nopasswd_yes
        exceptions:
          - id: legacy-fips-deviation
            reason: "approved by security 2026-01-01"
            stig_rules_disabled: [rule_x]
        """
    )
    host_yaml = _write_host_yaml(tmp_path, pre)
    suggestions = build_suggestions(_new_fail_report())

    apply_to_host_yaml(suggestions=suggestions, host_yaml_path=host_yaml, allow_regression=False)

    after = yaml.safe_load(host_yaml.read_text(encoding="utf-8"))
    ids = [e["id"] for e in after["exceptions"]]
    assert "legacy-fips-deviation" in ids
    assert "auto-new_fail-rule_d" in ids
    assert len(after["exceptions"]) == 2


def test_apply_allow_regression_true_writes_regressions(tmp_path: Path):
    host_yaml = _write_host_yaml(tmp_path)
    suggestions = build_suggestions(_new_fail_report())

    result = apply_to_host_yaml(
        suggestions=suggestions,
        host_yaml_path=host_yaml,
        allow_regression=True,
    )

    assert result.added == ("auto-new_fail-rule_d", "auto-regression-rule_e")
    assert result.skipped_regression == ()

    after = yaml.safe_load(host_yaml.read_text(encoding="utf-8"))
    ids = [e["id"] for e in after["exceptions"]]
    assert ids == ["auto-new_fail-rule_d", "auto-regression-rule_e"]


def test_apply_allow_regression_false_skips_regressions_only(tmp_path: Path):
    host_yaml = _write_host_yaml(tmp_path)
    suggestions = build_suggestions(_new_fail_report())

    result = apply_to_host_yaml(
        suggestions=suggestions,
        host_yaml_path=host_yaml,
        allow_regression=False,
    )

    # new_fail flowed through, regression was held back
    assert result.added == ("auto-new_fail-rule_d",)
    assert result.skipped_regression == ("auto-regression-rule_e",)

    after = yaml.safe_load(host_yaml.read_text(encoding="utf-8"))
    ids = [e["id"] for e in after["exceptions"]]
    assert ids == ["auto-new_fail-rule_d"]


# --- backup file behavior tests -------------------------------------------


def test_apply_writes_backup_matching_pre_apply_content(tmp_path: Path):
    host_yaml = _write_host_yaml(tmp_path)
    pre_content = host_yaml.read_text(encoding="utf-8")
    suggestions = build_suggestions(_new_fail_report())

    apply_to_host_yaml(suggestions=suggestions, host_yaml_path=host_yaml, allow_regression=False)

    backup = host_yaml.with_suffix(".yaml.bak")
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == pre_content


def test_apply_overwrites_existing_backup(tmp_path: Path):
    host_yaml = _write_host_yaml(tmp_path)
    suggestions_v1 = build_suggestions(_new_fail_report())

    # First apply creates .bak from the original
    apply_to_host_yaml(suggestions=suggestions_v1, host_yaml_path=host_yaml, allow_regression=False)
    # Now main has 1 entry; .bak has 0
    backup = host_yaml.with_suffix(".yaml.bak")
    assert "exceptions" not in yaml.safe_load(backup.read_text(encoding="utf-8")) or yaml.safe_load(
        backup.read_text(encoding="utf-8")
    ).get("exceptions") in (None, [])

    # Second apply with a different rule overwrites .bak with the
    # now-1-entry main
    new_report = _report(VerifyRow("rule_f", "fail", "fail", False, "new_fail"))
    suggestions_v2 = build_suggestions(new_report)
    apply_to_host_yaml(suggestions=suggestions_v2, host_yaml_path=host_yaml, allow_regression=False)

    backup_after = yaml.safe_load(backup.read_text(encoding="utf-8"))
    backup_ids = [e["id"] for e in backup_after["exceptions"]]
    assert backup_ids == ["auto-new_fail-rule_d"]  # the previous main state


def test_apply_no_op_does_not_create_backup(tmp_path: Path):
    host_yaml = _write_host_yaml(tmp_path)
    # No failing rows -> no suggestions -> nothing to apply
    suggestions: list[Suggestion] = []

    apply_to_host_yaml(suggestions=suggestions, host_yaml_path=host_yaml, allow_regression=False)

    backup = host_yaml.with_suffix(".yaml.bak")
    assert not backup.exists()


# --- error path tests --------------------------------------------------------


def test_apply_refuses_yaml_list_at_top_level(tmp_path: Path):
    host_yaml = tmp_path / "host.yaml"
    host_yaml.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    suggestions = build_suggestions(_new_fail_report())

    with pytest.raises(SuggestApplyError, match="not a YAML mapping"):
        apply_to_host_yaml(
            suggestions=suggestions,
            host_yaml_path=host_yaml,
            allow_regression=False,
        )

    # Original file untouched
    assert host_yaml.read_text(encoding="utf-8") == "- not\n- a\n- mapping\n"
    assert not (tmp_path / "host.yaml.bak").exists()


def test_apply_refuses_invalid_yaml_syntax(tmp_path: Path):
    host_yaml = tmp_path / "host.yaml"
    host_yaml.write_text("key: : : ::\n  broken\n", encoding="utf-8")
    suggestions = build_suggestions(_new_fail_report())

    with pytest.raises(SuggestApplyError, match="not valid YAML"):
        apply_to_host_yaml(
            suggestions=suggestions,
            host_yaml_path=host_yaml,
            allow_regression=False,
        )

    assert not (tmp_path / "host.yaml.bak").exists()


def test_apply_refuses_schema_rejecting_candidate(tmp_path: Path):
    # host.yaml is loadable as YAML but violates HostConfig (no admin keys
    # with an unset password). When we try to append, candidate validation
    # fails. No write, no backup.
    bad = textwrap.dedent(
        """\
        system: {hostname: h1}
        user:
          admin:
            name: ops
            # neither password nor authorized_keys -> pydantic rejects
        """
    )
    host_yaml = _write_host_yaml(tmp_path, bad)
    pre_content = host_yaml.read_text(encoding="utf-8")
    suggestions = build_suggestions(_new_fail_report())

    with pytest.raises(SuggestApplyError, match="would fail validation"):
        apply_to_host_yaml(
            suggestions=suggestions,
            host_yaml_path=host_yaml,
            allow_regression=False,
        )

    assert host_yaml.read_text(encoding="utf-8") == pre_content
    assert not (tmp_path / "host.yaml.bak").exists()


def test_apply_with_empty_host_yaml_file_treats_as_empty_mapping(tmp_path: Path):
    host_yaml = tmp_path / "host.yaml"
    host_yaml.write_text("", encoding="utf-8")
    # Empty file -> data = {} -> candidate = {"exceptions": [...]}
    # But the candidate must still satisfy HostConfig, which requires
    # `system` and `user.admin` — so validation will reject. Verify the
    # specific failure surfaces as SuggestApplyError, not a raw pydantic
    # ValidationError.
    suggestions = build_suggestions(_new_fail_report())

    with pytest.raises(SuggestApplyError, match="would fail validation"):
        apply_to_host_yaml(
            suggestions=suggestions,
            host_yaml_path=host_yaml,
            allow_regression=False,
        )
