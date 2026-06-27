from ks_gen.rules.alma9.time_servers import RULE


def test_post_writes_chrony_conf(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "/etc/chrony.conf" in out
    assert "server pool.ntp.org iburst" in out


def test_post_handles_multiple_servers(minimal_cfg):
    from ks_gen.config import Time

    cfg = minimal_cfg.model_copy(update={"time": Time(servers=["a.example", "b.example"])})
    out = RULE.emit_post(cfg)
    assert "server a.example iburst" in out
    assert "server b.example iburst" in out


def test_no_dod_servers_in_output(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "usno" not in out.lower()
    assert "navy.mil" not in out.lower()
