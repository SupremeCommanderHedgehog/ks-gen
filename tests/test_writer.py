import textwrap

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


def test_write_bundle_creates_files(tmp_path):
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(YAML, encoding="utf-8")
    cfg = load_host_config(cfg_path, sets=[])
    bundle = build_bundle(cfg)
    out = tmp_path / "out"
    write_bundle(bundle, out)
    for name in ("ks.cfg", "tailoring.xml", "host.yaml", "exceptions.md"):
        assert (out / name).is_file()


def test_admin_user_block_precedes_sshd_in_post(tmp_path):
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(YAML, encoding="utf-8")
    cfg = load_host_config(cfg_path, sets=[])
    bundle = build_bundle(cfg)
    admin_idx = bundle.ks_cfg.find("# ===== admin_user_and_keys =====")
    ssh_idx = bundle.ks_cfg.find("# ===== ssh_config_apply =====")
    assert admin_idx != -1 and ssh_idx != -1
    assert admin_idx < ssh_idx


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
