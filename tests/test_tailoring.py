from ks_gen.rules._types import TailoringOp
from ks_gen.skeleton import render_skeleton
from ks_gen.tailoring import TAILORED_PROFILE_ID, build_tailoring_xml


def test_empty_ops_produces_skeleton():
    xml = build_tailoring_xml(
        [],
        profile_id="xccdf_org.ssgproject.content_profile_stig",
        scap_content="ssg-almalinux9-ds.xml",
    )
    assert "<xccdf:Tailoring" in xml
    assert 'extends="xccdf_org.ssgproject.content_profile_stig"' in xml


def test_disable_rule_select_false():
    ops = [TailoringOp(rule_id="xccdf_org.ssgproject.content_rule_foo", action="disable")]
    xml = build_tailoring_xml(
        ops,
        profile_id="xccdf_org.ssgproject.content_profile_stig",
        scap_content="ssg-almalinux9-ds.xml",
    )
    assert '<xccdf:select idref="xccdf_org.ssgproject.content_rule_foo" selected="false"/>' in xml


def test_set_value_emits_set_value_element():
    ops = [
        TailoringOp(
            rule_id="xccdf_org.ssgproject.content_value_var_auditd_disk_full_action",
            action="set_value",
            value="SUSPEND",
        )
    ]
    xml = build_tailoring_xml(
        ops,
        profile_id="xccdf_org.ssgproject.content_profile_stig",
        scap_content="ssg-almalinux9-ds.xml",
    )
    assert (
        '<xccdf:set-value idref="xccdf_org.ssgproject.content_value_var_auditd_disk_full_action">'
        "SUSPEND</xccdf:set-value>" in xml
    )


def test_select_action_select_true():
    ops = [TailoringOp(rule_id="xccdf_org.ssgproject.content_rule_bar", action="select")]
    xml = build_tailoring_xml(
        ops,
        profile_id="xccdf_org.ssgproject.content_profile_stig",
        scap_content="ssg-almalinux9-ds.xml",
    )
    assert '<xccdf:select idref="xccdf_org.ssgproject.content_rule_bar" selected="true"/>' in xml


def test_benchmark_href_uses_scap_content_alma():
    xml = build_tailoring_xml(
        [],
        profile_id="xccdf_org.ssgproject.content_profile_stig",
        scap_content="ssg-almalinux9-ds.xml",
    )
    assert '<xccdf:benchmark href="/usr/share/xml/scap/ssg/content/ssg-almalinux9-ds.xml"/>' in xml


def test_benchmark_href_uses_scap_content_ubuntu():
    xml = build_tailoring_xml(
        [],
        profile_id="xccdf_org.ssgproject.content_profile_stig",
        scap_content="ssg-ubuntu2404-ds.xml",
    )
    assert '<xccdf:benchmark href="/usr/share/xml/scap/ssg/content/ssg-ubuntu2404-ds.xml"/>' in xml
    assert "ssg-almalinux9-ds.xml" not in xml


def test_generated_profile_id_matches_the_exported_constant():
    """#65: the id emitted here is the id every oscap --profile must name."""
    xml = build_tailoring_xml(
        [],
        profile_id="xccdf_org.ssgproject.content_profile_stig",
        scap_content="ssg-almalinux9-ds.xml",
    )
    assert f'<xccdf:Profile id="{TAILORED_PROFILE_ID}"' in xml


def test_kickstart_oscap_evaluates_the_tailored_profile(minimal_cfg):
    """Naming the base profile loads the tailoring and silently ignores it.

    Confirmed on real AL10 hardware: the ARF reported
    testresult_...content_profile_stig and every disabled rule was still
    scanned. This is the regression pin for that.
    """
    ks = render_skeleton(minimal_cfg, post_blocks=[])
    assert f"--profile {TAILORED_PROFILE_ID}" in ks
    assert "--profile xccdf_org.ssgproject.content_profile_stig" not in ks


def test_verify_oscap_command_evaluates_the_BASE_profile(minimal_cfg):
    """The opposite of the install path, on purpose.

    verify must see the full rule set to reconcile against host.yaml. A rule
    the deployed tailoring deselects returns `notselected`, which reconcile
    treats as clean — so scanning the tailored profile would let a stale or
    hand-edited on-host tailoring shrink the scan meant to police it.
    """
    from ks_gen.verify.remote import _oscap_command

    cmd = _oscap_command(minimal_cfg)
    assert "--profile xccdf_org.ssgproject.content_profile_stig" in cmd
    assert TAILORED_PROFILE_ID not in cmd
    # ...but it still passes the tailoring, which --check-tailoring diffs.
    assert "--tailoring-file /root/tailoring.xml" in cmd
