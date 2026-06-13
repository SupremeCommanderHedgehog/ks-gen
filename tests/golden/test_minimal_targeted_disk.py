from pathlib import Path

from ks_gen.loader import load_host_config
from ks_gen.writer import build_bundle


def test_minimal_targeted_disk_part_lines_carry_ondisk():
    yaml_path = Path(__file__).parent / "minimal-targeted-disk.host.yaml"
    bundle = build_bundle(load_host_config(yaml_path, sets=[]))
    lines = bundle.ks_cfg.splitlines()
    part_lines = [line for line in lines if line.startswith("part ")]
    assert len(part_lines) == 4, f"expected 4 part lines, got {part_lines}"
    for line in part_lines:
        assert "--ondisk=sda" in line, f"missing --ondisk=sda on: {line}"


def test_stig_server_targeted_emits_ondisk_on_pv():
    yaml = (
        "system:\n  hostname: stigsrv.example.com\n"
        "user:\n  admin:\n    name: opsadmin\n"
        "    authorized_keys:\n"
        '      - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEY ops@bastion"\n'
        "    sudo: nopasswd_yes\n"
        "disk:\n  target: vda\n  preset: stig_server\n"
    )
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".host.yaml", delete=False) as fh:
        fh.write(yaml)
        path = Path(fh.name)
    try:
        bundle = build_bundle(load_host_config(path, sets=[]))
    finally:
        path.unlink()
    lines = bundle.ks_cfg.splitlines()
    pv_line = next(line for line in lines if line.startswith("part pv.01 "))
    assert "--ondisk=vda" in pv_line
