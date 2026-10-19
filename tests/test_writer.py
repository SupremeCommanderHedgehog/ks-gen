import textwrap

import yaml

from ks_gen.loader import load_host_config
from ks_gen.writer import build_bundle, write_bundle

YAML = textwrap.dedent(
    """\
    system: {hostname: web01.example.com}
    user:
      admin:
        name: opsadmin
        authorized_keys: ["ssh-ed25519 AAAA a@b"]
        sudo: nopasswd_yes
    """
)


def test_build_bundle_returns_four_artifacts(tmp_path):
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(YAML, encoding="utf-8")
    cfg = load_host_config(cfg_path, sets=[])
    bundle = build_bundle(cfg)
    assert "%post" in bundle.ks_cfg
    assert "<xccdf:Tailoring" in bundle.tailoring_xml
    assert "MODERN" in bundle.exceptions_md or "MODERN" in bundle.ks_cfg
    assert bundle.host_yaml.startswith("meta:") or "system:" in bundle.host_yaml


def test_host_yaml_omits_the_derived_fips_mode(tmp_path):
    """#84: dumping the derived value is what let it go stale — a bundle
    generated now must not carry the key at all, and must still round-trip."""
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(
        YAML.replace("system:", "crypto: {policy: STIG}\nsystem:").replace(
            "ssh-ed25519 AAAA a@b", "ssh-rsa AAAA a@b"
        ),
        encoding="utf-8",
    )
    cfg = load_host_config(cfg_path, sets=[])
    assert cfg.kernel_fips is True
    dumped = yaml.safe_load(build_bundle(cfg).host_yaml)
    assert "fips_mode" not in dumped["overrides"]

    out = tmp_path / "regen.yaml"
    out.write_text(yaml.safe_dump(dumped), encoding="utf-8")
    assert load_host_config(out, sets=[]).kernel_fips is True


def test_host_yaml_drops_the_deprecated_ufw_key(tmp_path):
    """#103: a stale ensure_ufw_port loads, but regenerating sheds it."""
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(
        YAML.replace("system:", "overrides: {ssh_keep_open: {ensure_ufw_port: true}}\nsystem:"),
        encoding="utf-8",
    )
    dumped = yaml.safe_load(build_bundle(load_host_config(cfg_path, sets=[])).host_yaml)
    assert "ensure_ufw_port" not in dumped["overrides"]["ssh_keep_open"]
    assert dumped["overrides"]["ssh_keep_open"]["ensure_firewalld_port"] is True


def test_write_bundle_creates_files(tmp_path):
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(YAML, encoding="utf-8")
    cfg = load_host_config(cfg_path, sets=[])
    bundle = build_bundle(cfg)
    out = tmp_path / "out"
    write_bundle(bundle, out)
    for name in ("ks.cfg", "tailoring.xml", "host.yaml", "exceptions.md"):
        assert (out / name).is_file()


def test_declared_exceptions_disable_rules_in_tailoring(tmp_path):
    # Operator-declared exceptions (cfg.exceptions) must actually deselect the
    # named STIG rules in tailoring.xml, not merely document them in
    # exceptions.md. Regression for the GUI-removal case: the STIG
    # xwindows_* rules stripped the desktop because the declared exception
    # never reached the oscap tailoring.
    rid1 = "xccdf_org.ssgproject.content_rule_xwindows_remove_packages"
    rid2 = "xccdf_org.ssgproject.content_rule_xwindows_runlevel_target"
    yaml_text = YAML + textwrap.dedent(
        f"""\
        exceptions:
          - id: gui-workstation-keep-x
            reason: "Approved dev workstation; GUI required."
            stig_rules_disabled:
              - {rid1}
              - {rid2}
        """
    )
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(yaml_text, encoding="utf-8")
    cfg = load_host_config(cfg_path, sets=[])
    bundle = build_bundle(cfg)
    assert f'<xccdf:select idref="{rid1}" selected="false"/>' in bundle.tailoring_xml
    assert f'<xccdf:select idref="{rid2}" selected="false"/>' in bundle.tailoring_xml
    # existing behavior preserved: still documented in exceptions.md
    assert rid1 in bundle.exceptions_md


def test_admin_user_block_precedes_sshd_in_post(tmp_path):
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(YAML, encoding="utf-8")
    cfg = load_host_config(cfg_path, sets=[])
    bundle = build_bundle(cfg)
    admin_idx = bundle.ks_cfg.find("# ===== admin_user_and_keys =====")
    ssh_idx = bundle.ks_cfg.find("# ===== ssh_config_apply =====")
    assert admin_idx != -1 and ssh_idx != -1
    assert admin_idx < ssh_idx


def test_top_level_user_line_locked_when_password_null(tmp_path):
    # Anaconda's GUI requires a top-level `user` directive; without one the
    # User Creation pane comes up blank on USB-mode installs even when %post
    # creates the user. Lockout-resistance contract is preserved via --lock.
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(YAML, encoding="utf-8")
    cfg = load_host_config(cfg_path, sets=[])
    bundle = build_bundle(cfg)
    assert "user --name=opsadmin --lock --groups=wheel" in bundle.ks_cfg
    assert "--password=" not in bundle.ks_cfg.split("user --name=opsadmin")[1].split("\n")[0]


def test_top_level_user_line_password_iscrypted_when_set(tmp_path):
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(
        textwrap.dedent(
            """\
            system: {hostname: web01.example.com}
            user:
              admin:
                name: opsadmin
                password: "$6$abc$xyz"
                sudo: nopasswd_yes
            # A keyless admin is only a legal host when the console is declared (#76).
            overrides: {console_login_only: true}
            """
        ),
        encoding="utf-8",
    )
    cfg = load_host_config(cfg_path, sets=[])
    bundle = build_bundle(cfg)
    user_line = next(
        line for line in bundle.ks_cfg.splitlines() if line.startswith("user --name=opsadmin")
    )
    assert "--password=$6$abc$xyz" in user_line
    assert "--iscrypted" in user_line
    assert "--lock" not in user_line


def test_rule_packages_land_in_packages_block_when_required_omits_them(tmp_path):
    # Regression for #53: a user-supplied packages.required that omits
    # dnf-automatic / dnf-utils must NOT silently break the unattended_updates
    # %post block — the rule now declares its own packages.
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(
        textwrap.dedent(
            """\
            system: {hostname: web01.example.com}
            user:
              admin:
                name: opsadmin
                authorized_keys: ["ssh-ed25519 AAAA a@b"]
                sudo: nopasswd_yes
            packages:
              required: [scap-security-guide, openscap-scanner, aide, audit, rsyslog, chrony, firewalld, sudo, policycoreutils-python-utils]
            """  # noqa: E501
        ),
        encoding="utf-8",
    )
    cfg = load_host_config(cfg_path, sets=[])
    # Sanity: defaults overridden — required does NOT contain the rule's deps.
    assert "dnf-automatic" not in cfg.packages.required
    assert "dnf-utils" not in cfg.packages.required

    bundle = build_bundle(cfg)
    pkgs_block = bundle.ks_cfg.split("%packages", 1)[1].split("%end", 1)[0]
    assert "\ndnf-automatic\n" in pkgs_block
    assert "\ndnf-utils\n" in pkgs_block


def test_rule_packages_are_deduped_against_required(tmp_path):
    # When packages.required already contains the rule's deps, the rendered
    # %packages block must list each package exactly once.
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(YAML, encoding="utf-8")
    cfg = load_host_config(cfg_path, sets=[])
    assert "dnf-automatic" in cfg.packages.required  # comes from defaults
    bundle = build_bundle(cfg)
    pkgs_block = bundle.ks_cfg.split("%packages", 1)[1].split("%end", 1)[0]
    assert pkgs_block.count("\ndnf-automatic\n") == 1
    assert pkgs_block.count("\ndnf-utils\n") == 1


def test_build_bundle_alma9_default_unchanged_when_distro_omitted(tmp_path):
    # Regression guard for the dispatch refactor: a config with no `distro:`
    # still defaults to alma9 and produces a ks_cfg-bearing bundle.
    yaml_text = textwrap.dedent(
        """\
        system: {hostname: alma-default}
        user:
          admin:
            name: ops
            authorized_keys: ["ssh-ed25519 AAAA a@b"]
            sudo: nopasswd_yes
        """
    )
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(yaml_text, encoding="utf-8")
    cfg = load_host_config(cfg_path, sets=[])
    bundle = build_bundle(cfg)
    assert bundle.distro == "alma9"
    assert bundle.ks_cfg is not None
    assert "%post" in bundle.ks_cfg


def test_render_tailoring_matches_build_bundle_tailoring_xml() -> None:
    """render_tailoring(cfg) produces the same XML as build_bundle(cfg).tailoring_xml,
    modulo the embedded timestamp in <xccdf:version time="...">."""
    import re

    from ks_gen.config import AdminUser, HostConfig, System, User
    from ks_gen.writer import build_bundle, render_tailoring

    cfg = HostConfig(
        system=System(hostname="h"),
        user=User(
            admin=AdminUser(name="ops", authorized_keys=["ssh-ed25519 A a@b"], sudo="nopasswd_yes")
        ),
    )
    bundle_xml = build_bundle(cfg).tailoring_xml
    direct_xml = render_tailoring(cfg)

    # Strip the timestamp before comparison — datetime.now(UTC) embedded in
    # the version header differs between the two renders.
    strip = re.compile(r'time="[^"]*"')
    assert strip.sub('time=""', bundle_xml) == strip.sub('time=""', direct_xml)
