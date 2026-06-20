from ks_gen.rules.ubuntu2404.kernel_module_blacklist import RULE


def test_post_writes_modprobe_blacklist_conf_path(ubuntu_cfg_factory):
    # /etc/modprobe.d/ is the canonical drop-in directory on both
    # Debian-family and RHEL-family systems — modprobe reads every
    # *.conf file there at module-load time. The "ks-gen-" prefix
    # avoids collision with Debian-shipped blacklist-*.conf files.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/modprobe.d/ks-gen-blacklist.conf" in out
