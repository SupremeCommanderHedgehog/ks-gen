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
