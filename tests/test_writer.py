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
