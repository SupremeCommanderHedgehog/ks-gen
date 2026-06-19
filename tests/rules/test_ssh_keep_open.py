from ks_gen.rules.alma9.ssh_keep_open import RULE


def test_applies_when_either_flag_set(minimal_cfg):
    assert RULE.applies(minimal_cfg)


def test_port_22_skips_semanage(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "semanage" not in out
    assert "firewall-offline-cmd --add-port=22/tcp" in out


def test_custom_port_runs_semanage(minimal_cfg):
    from ks_gen.config import Ssh

    cfg = minimal_cfg.model_copy(update={"ssh": Ssh(port=2222)})
    out = RULE.emit_post(cfg)
    assert "semanage port -a -t ssh_port_t -p tcp 2222" in out or "semanage port -m" in out
    assert "firewall-offline-cmd --add-port=2222/tcp" in out


def test_no_tailoring(minimal_cfg):
    assert RULE.emit_tailoring(minimal_cfg) == []
