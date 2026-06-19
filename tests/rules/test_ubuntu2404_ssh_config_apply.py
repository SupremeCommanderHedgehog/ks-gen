from ks_gen.rules.ubuntu2404.ssh_config_apply import RULE


def test_depends_on_admin_and_keep_open(ubuntu_cfg_factory):
    assert "admin_user_and_keys" in RULE.depends_on
    assert "ssh_keep_open" in RULE.depends_on


def test_post_writes_drop_in_config(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/ssh/sshd_config.d/00-ks-gen.conf" in out
    assert "Port 22" in out
    assert "PermitRootLogin no" in out
    assert "PasswordAuthentication no" in out
    assert "ClientAliveInterval 600" in out
    assert "ClientAliveCountMax 1" in out
    assert "MaxAuthTries 4" in out
    assert "UsePAM yes" in out


def test_post_validates_with_sshd_t(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "sshd -t" in out


def test_post_does_not_restart_sshd_during_install(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "systemctl restart sshd" not in out
    assert "systemctl reload sshd" not in out
    assert "systemctl restart ssh" not in out
    assert "systemctl reload ssh" not in out


def test_post_drop_in_is_mode_600(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "chmod 600 /etc/ssh/sshd_config.d/00-ks-gen.conf" in out


def test_post_emits_banner_directive_when_motd_in_apply_to(ubuntu_cfg_factory):
    # Default ubuntu cfg.banner.apply_to includes "motd"; phase 3.1's
    # banner_text rule maps motd -> /etc/ssh/sshd-banner. ssh_config_apply
    # must point sshd's Banner directive at that file so the banner
    # actually surfaces on SSH login.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "Banner /etc/ssh/sshd-banner" in out


def test_post_omits_banner_directive_when_motd_excluded(ubuntu_cfg_factory):
    # If the operator drops "motd" from apply_to, banner_text won't write
    # /etc/ssh/sshd-banner — so we must not point sshd at a missing file.
    from ks_gen.config import Banner

    base = ubuntu_cfg_factory()
    cfg = base.model_copy(
        update={
            "banner": Banner(
                text=base.banner.text,
                apply_to=["issue", "issue_net", "gdm"],
            )
        }
    )
    out = RULE.emit_post(cfg)
    assert "Banner /etc/ssh/sshd-banner" not in out


def test_post_uses_configured_port(ubuntu_cfg_factory):
    from ks_gen.config import Ssh

    base = ubuntu_cfg_factory()
    cfg = base.model_copy(update={"ssh": Ssh(port=2222)})
    out = RULE.emit_post(cfg)
    assert "Port 2222" in out
    assert "Port 22\n" not in out


def test_applies_always_true(ubuntu_cfg_factory):
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_emit_tailoring_returns_empty_deferred(ubuntu_cfg_factory):
    # Deferred until ssg-ubuntu2404-ds.xml survey lands.
    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []


def test_exception_entry_returns_none_deferred(ubuntu_cfg_factory):
    # Deferred until ssg-ubuntu2404-ds.xml survey lands.
    assert RULE.exception_entry(ubuntu_cfg_factory()) is None


def test_emit_packages_is_empty(ubuntu_cfg_factory):
    # openssh-server is installed by default on Ubuntu Server; no apt deps.
    assert RULE.emit_packages(ubuntu_cfg_factory()) == []


def test_id_and_summary_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules._meta import ssh_config_apply as meta

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY
