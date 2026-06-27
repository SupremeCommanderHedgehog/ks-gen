from ks_gen.rules.ubuntu2404.package_purge import RULE


def test_applies_when_enabled_and_has_excluded(ubuntu_cfg_factory):
    # Default cfg: enable=True, excluded=5 RHEL-flavored entries.
    # Both conditions satisfied → applies.
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_applies_short_circuits_when_disabled(ubuntu_cfg_factory):
    from ks_gen.config import Overrides, PackagePurgeCfg

    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "overrides": Overrides(
                package_purge=PackagePurgeCfg(enable=False),
            )
        }
    )
    assert RULE.applies(cfg) is False


def test_applies_short_circuits_when_excluded_empty(ubuntu_cfg_factory):
    # No work to do — even with enable=True, an empty excluded list
    # means the rule shouldn't run (would render a no-op apt command).
    from ks_gen.config import Packages

    cfg = ubuntu_cfg_factory().model_copy(update={"packages": Packages(excluded=[])})
    assert RULE.applies(cfg) is False


def test_post_uses_apt_get_purge(ubuntu_cfg_factory):
    # apt-get (not apt — `apt` is interactive and not script-safe).
    # -y is the non-interactive yes flag.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "apt-get -y purge" in out


def test_post_uses_debian_frontend_noninteractive(ubuntu_cfg_factory):
    # No TTY in late-commands. Without this, a conffile-removal
    # prompt would hang the install.
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "DEBIAN_FRONTEND=noninteractive" in out


def test_post_squashes_failures_with_or_true(ubuntu_cfg_factory):
    # Mirrors alma9. Squashes:
    #   exit 100 "Unable to locate package" (RHEL-flavored default
    #     excluded list against Ubuntu archive)
    #   exit 1   "package already removed" (re-run idempotency)
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "|| true" in out


def test_post_lists_all_default_excluded_packages(ubuntu_cfg_factory):
    # The 5 RHEL-flavored entries in Packages.excluded default — all
    # of them must reach the apt-get -y purge command. Cross-distro
    # name mapping is intentionally NOT done here; operators configure
    # Ubuntu-flavored names in host.yaml for real purges.
    out = RULE.emit_post(ubuntu_cfg_factory())
    for pkg in ("telnet-server", "rsh-server", "tftp-server", "vsftpd", "ypserv"):
        assert pkg in out


def test_post_reflects_excluded_override(ubuntu_cfg_factory):
    # Override is a full replacement, NOT a merge — operator gets
    # exactly the excluded list they specified.
    from ks_gen.config import Packages

    cfg = ubuntu_cfg_factory().model_copy(
        update={"packages": Packages(excluded=["apache2", "nginx"])}
    )
    out = RULE.emit_post(cfg)
    assert "apache2" in out
    assert "nginx" in out
    # Defaults MUST NOT leak in.
    assert "telnet-server" not in out
    assert "vsftpd" not in out


def test_emit_packages_returns_empty(ubuntu_cfg_factory):
    # apt-get ships with apt (Priority: required) — no apt deps needed
    # for the rule itself.
    assert RULE.emit_packages(ubuntu_cfg_factory()) == []


def test_protocol_contract(ubuntu_cfg_factory):
    from ks_gen.rules._meta import package_purge as meta

    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []
    assert RULE.exception_entry(ubuntu_cfg_factory()) is None
    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY
    assert RULE.depends_on == []
