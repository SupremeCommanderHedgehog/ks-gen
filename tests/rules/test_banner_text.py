from ks_gen.rules.alma9.banner_text import RULE


def test_post_writes_issue_files(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "/etc/issue" in out
    assert "/etc/issue.net" in out
    assert "/etc/motd" in out
    assert "private computer system" in out


def test_tailoring_disables_banner_content_rules(minimal_cfg):
    ops = RULE.emit_tailoring(minimal_cfg)
    disabled = {o.rule_id for o in ops if o.action == "disable"}
    assert any("banner_etc_issue" in r for r in disabled)
    assert any("banner_etc_issue_net" in r for r in disabled)


def test_post_does_not_contain_dod_text(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "U.S. Government" not in out
    assert "USG" not in out


def test_exception_entry_always_present(minimal_cfg):
    assert RULE.exception_entry(minimal_cfg) is not None
