from ks_gen.rules.ubuntu2404.ssh_keep_open import RULE


def test_applies_when_ensure_ufw_port_true(ubuntu_cfg_factory):
    # Default ubuntu2404 cfg has ensure_ufw_port=True.
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_does_not_apply_when_ensure_ufw_port_false(ubuntu_cfg_factory):
    from ks_gen.config import Overrides, SshKeepOpenCfg

    base = ubuntu_cfg_factory()
    cfg = base.model_copy(
        update={
            "overrides": Overrides(
                ssh_keep_open=SshKeepOpenCfg(ensure_ufw_port=False),
            )
        }
    )
    assert RULE.applies(cfg) is False


def test_emit_post_uses_ufw_with_configured_port(ubuntu_cfg_factory):
    from ks_gen.config import Ssh

    base = ubuntu_cfg_factory()
    cfg = base.model_copy(update={"ssh": Ssh(port=2222)})
    out = RULE.emit_post(cfg)
    assert "ufw allow 2222/tcp" in out
    # No SELinux analog, no firewalld; this rule is ufw-only.
    assert "semanage" not in out
    assert "firewall-offline-cmd" not in out


def test_emit_post_default_port_22(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "ufw allow 22/tcp" in out


def test_emit_packages_includes_ufw(ubuntu_cfg_factory):
    assert RULE.emit_packages(ubuntu_cfg_factory()) == ["ufw"]


def test_emit_tailoring_returns_empty(ubuntu_cfg_factory):
    # Deferred until ssg-ubuntu2404-ds.xml survey lands.
    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []


def test_exception_entry_returns_none(ubuntu_cfg_factory):
    assert RULE.exception_entry(ubuntu_cfg_factory()) is None


def test_id_and_summary_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules._meta import ssh_keep_open as meta

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY
