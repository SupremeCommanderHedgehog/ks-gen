from ks_gen.rules.package_purge import RULE


def test_post_removes_excluded_packages(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "dnf -y remove" in out
    assert "telnet-server" in out
    assert "rsh-server" in out


def test_does_not_apply_when_excluded_is_empty(minimal_cfg):
    from ks_gen.config import Packages

    cfg = minimal_cfg.model_copy(update={"packages": Packages(excluded=[])})
    assert not RULE.applies(cfg)
