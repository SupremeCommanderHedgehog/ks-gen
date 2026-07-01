from ks_gen.rules.alma9.admin_user_and_keys import RULE


def test_applies_always(minimal_cfg):
    assert RULE.applies(minimal_cfg)


def test_password_hash_not_exposed_to_shell_expansion(minimal_cfg):
    # A SHA-512 crypt hash contains `$6$...` segments. The %post block runs
    # under `set -euxo pipefail`, so any unescaped `$6` in a double-quoted
    # string is treated as positional parameter 6 -> "unbound variable" ->
    # fatal install abort (observed live on the cougar build, 2026-06-30).
    # The hash must be single-quoted so bash passes it through literally.
    pw = "$6$YJbKhp9Lbll716tN$nt1RtJC4hspS1m4Oc6htcTbfY5eWl"
    admin = minimal_cfg.user.admin.model_copy(update={"password": pw, "sudo": "nopasswd_no"})
    cfg = minimal_cfg.model_copy(
        update={"user": minimal_cfg.user.model_copy(update={"admin": admin})}
    )
    out = RULE.emit_post(cfg)
    name = admin.name
    assert "chpasswd -e" in out
    assert f"'{name}:{pw}'" in out
    assert f'"{name}:{pw}"' not in out


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
