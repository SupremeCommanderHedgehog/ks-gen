from ks_gen.rules.ubuntu2404.time_servers import RULE


def test_post_writes_chrony_conf_at_ubuntu_path(ubuntu_cfg_factory):
    # Ubuntu's chrony package owns /etc/chrony/ as a directory; the
    # config file lives at /etc/chrony/chrony.conf (not /etc/chrony.conf
    # as on RHEL). Strict path assertion catches drift.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/chrony/chrony.conf" in out
    # Bare /etc/chrony.conf (no subdirectory) is the alma9 path — must
    # not appear in the ubuntu output.
    assert "/etc/chrony.conf\n" not in out
    assert "/etc/chrony.conf " not in out


def test_post_writes_server_lines_for_default_pool(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "server pool.ntp.org iburst" in out


def test_post_handles_multiple_servers(ubuntu_cfg_factory):
    from ks_gen.config import Time

    cfg = ubuntu_cfg_factory().model_copy(update={"time": Time(servers=["a.example", "b.example"])})
    out = RULE.emit_post(cfg)
    assert "server a.example iburst" in out
    assert "server b.example iburst" in out


def test_post_no_dod_servers_in_output(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "usno" not in out.lower()
    assert "navy.mil" not in out.lower()
