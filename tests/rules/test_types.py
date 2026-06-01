from ks_gen.rules._types import ExceptionEntry, TailoringOp


def test_tailoring_op_disable():
    op = TailoringOp(rule_id="xccdf_org.ssgproject.content_rule_foo", action="disable")
    assert op.action == "disable"
    assert op.value is None


def test_tailoring_op_set_value():
    op = TailoringOp(
        rule_id="xccdf_org.ssgproject.content_value_bar",
        action="set_value",
        value="900",
    )
    assert op.value == "900"


def test_tailoring_op_set_value_requires_value():
    import pytest

    with pytest.raises(ValueError, match="set_value requires a value"):
        TailoringOp(rule_id="x", action="set_value")


def test_exception_entry_fields():
    entry = ExceptionEntry(
        rule_id="faillock_safety",
        summary="unlock_time=900 instead of STIG default 0",
        stig_rules_disabled=["xccdf_org.ssgproject.content_rule_pam_faillock_even_deny_root"],
        reason="Prevents permanent lockout of remote admin.",
    )
    assert entry.rule_id == "faillock_safety"
    assert len(entry.stig_rules_disabled) == 1
