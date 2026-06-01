from ks_gen.rules._types import TailoringOp
from ks_gen.tailoring import build_tailoring_xml


def test_empty_ops_produces_skeleton():
    xml = build_tailoring_xml([], profile_id="xccdf_org.ssgproject.content_profile_stig")
    assert "<xccdf:Tailoring" in xml
    assert 'extends="xccdf_org.ssgproject.content_profile_stig"' in xml


def test_disable_rule_select_false():
    ops = [TailoringOp(rule_id="xccdf_org.ssgproject.content_rule_foo", action="disable")]
    xml = build_tailoring_xml(ops, profile_id="xccdf_org.ssgproject.content_profile_stig")
    assert '<xccdf:select idref="xccdf_org.ssgproject.content_rule_foo" selected="false"/>' in xml


def test_set_value_emits_set_value_element():
    ops = [
        TailoringOp(
            rule_id="xccdf_org.ssgproject.content_value_var_auditd_disk_full_action",
            action="set_value",
            value="SUSPEND",
        )
    ]
    xml = build_tailoring_xml(ops, profile_id="xccdf_org.ssgproject.content_profile_stig")
    assert (
        '<xccdf:set-value idref="xccdf_org.ssgproject.content_value_var_auditd_disk_full_action">'
        "SUSPEND</xccdf:set-value>" in xml
    )


def test_select_action_select_true():
    ops = [TailoringOp(rule_id="xccdf_org.ssgproject.content_rule_bar", action="select")]
    xml = build_tailoring_xml(ops, profile_id="xccdf_org.ssgproject.content_profile_stig")
    assert '<xccdf:select idref="xccdf_org.ssgproject.content_rule_bar" selected="true"/>' in xml
