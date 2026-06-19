from ks_gen.rules.alma9.ssh_config_apply import RULE


def test_depends_on_admin_and_keep_open(minimal_cfg):
    assert "admin_user_and_keys" in RULE.depends_on
    assert "ssh_keep_open" in RULE.depends_on


def test_post_writes_drop_in_config(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "/etc/ssh/sshd_config.d/00-ks-gen.conf" in out
    assert "Port 22" in out
    assert "PermitRootLogin no" in out
    assert "PasswordAuthentication no" in out
    assert "ClientAliveInterval 600" in out
    assert "MaxAuthTries 4" in out
    assert "UsePAM yes" in out


def test_post_validates_with_sshd_t(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "sshd -t" in out


def test_post_does_not_restart_sshd_during_install(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "systemctl restart sshd" not in out
    assert "systemctl reload sshd" not in out
