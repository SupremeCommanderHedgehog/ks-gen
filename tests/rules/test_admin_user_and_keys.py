from ks_gen.rules.admin_user_and_keys import RULE


def test_applies_always(minimal_cfg):
    assert RULE.applies(minimal_cfg)


def test_emits_no_tailoring(minimal_cfg):
    assert RULE.emit_tailoring(minimal_cfg) == []


def test_post_creates_user_with_authorized_keys(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "useradd" in out
    assert "opsadmin" in out
    assert "wheel" in out
    assert ".ssh/authorized_keys" in out
    assert "ssh-ed25519 AAAA a@b" in out
    assert "chmod 600" in out
    assert "restorecon" in out


def test_post_writes_sudoers_fragment(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "/etc/sudoers.d/00-ks-gen-admin" in out


def test_no_exception_entry_unless_overridden(minimal_cfg):
    assert RULE.exception_entry(minimal_cfg) is None


def test_post_is_idempotent_via_guards(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    # We don't actually re-run; we just confirm guards exist that would
    # let the script be re-run without failure.
    assert "id -u" in out or "getent passwd" in out
