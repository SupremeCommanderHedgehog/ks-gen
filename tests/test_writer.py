import textwrap

import pytest

from ks_gen.loader import load_host_config
from ks_gen.writer import Bundle, build_bundle, write_bundle

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


def test_bundle_alma9_requires_ks_cfg_and_rejects_user_data():
    # alma9 bundle MUST have ks_cfg set; MUST NOT have user_data or meta_data.
    Bundle(
        distro="alma9",
        tailoring_xml="<x/>",
        host_yaml="meta: {}\n",
        exceptions_md="# x\n",
        ks_cfg="cmdline\n%end\n",
    )  # OK
    with pytest.raises(ValueError, match="alma9 bundle requires ks_cfg"):
        Bundle(
            distro="alma9",
            tailoring_xml="<x/>",
            host_yaml="meta: {}\n",
            exceptions_md="# x\n",
            ks_cfg=None,
        )
    with pytest.raises(ValueError, match="alma9 bundle must not set user_data"):
        Bundle(
            distro="alma9",
            tailoring_xml="<x/>",
            host_yaml="meta: {}\n",
            exceptions_md="# x\n",
            ks_cfg="cmdline\n",
            user_data="#cloud-config\n",
        )


def test_bundle_ubuntu2404_requires_user_data_meta_data_and_rejects_ks_cfg():
    # ubuntu2404 bundle MUST have user_data AND meta_data; MUST NOT have ks_cfg.
    Bundle(
        distro="ubuntu2404",
        tailoring_xml="<x/>",
        host_yaml="meta: {}\n",
        exceptions_md="# x\n",
        user_data="#cloud-config\nautoinstall: {version: 1}\n",
        meta_data="instance-id: x\n",
    )  # OK
    with pytest.raises(ValueError, match="ubuntu2404 bundle requires user_data"):
        Bundle(
            distro="ubuntu2404",
            tailoring_xml="<x/>",
            host_yaml="meta: {}\n",
            exceptions_md="# x\n",
            user_data=None,
            meta_data="instance-id: x\n",
        )
    with pytest.raises(ValueError, match="ubuntu2404 bundle requires meta_data"):
        Bundle(
            distro="ubuntu2404",
            tailoring_xml="<x/>",
            host_yaml="meta: {}\n",
            exceptions_md="# x\n",
            user_data="#cloud-config\n",
            meta_data=None,
        )
    with pytest.raises(ValueError, match="ubuntu2404 bundle must not set ks_cfg"):
        Bundle(
            distro="ubuntu2404",
            tailoring_xml="<x/>",
            host_yaml="meta: {}\n",
            exceptions_md="# x\n",
            user_data="#cloud-config\n",
            meta_data="instance-id: x\n",
            ks_cfg="cmdline\n",
        )


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
