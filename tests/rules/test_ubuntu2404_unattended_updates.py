from ks_gen.rules.ubuntu2404.unattended_updates import RULE


def test_nightly_writes_20auto_upgrades_path_and_content(ubuntu_cfg_factory):
    # /etc/apt/apt.conf.d/20auto-upgrades is the canonical Debian/Ubuntu
    # file that flips periodic apt-daily logic from "off" to "on" — both
    # keys must be "1" to actually enable unattended-upgrades.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "/etc/apt/apt.conf.d/20auto-upgrades" in out
    assert 'APT::Periodic::Update-Package-Lists "1";' in out
    assert 'APT::Periodic::Unattended-Upgrade "1";' in out
