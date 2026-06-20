from ks_gen.rules.ubuntu2404.faillock_safety import RULE


def test_post_writes_faillock_conf_path(ubuntu_cfg_factory):
    # Same /etc/security/faillock.conf path as alma9 — file ships in
    # libpam-modules (essential package) so this works in the chroot.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/security/faillock.conf" in out
