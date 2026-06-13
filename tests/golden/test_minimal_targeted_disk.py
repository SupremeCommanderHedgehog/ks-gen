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


def test_stig_server_targeted_emits_ondisk_on_all_part_lines():
    yaml_path = Path(__file__).parent / "stig-server-targeted-disk.host.yaml"
    bundle = build_bundle(load_host_config(yaml_path, sets=[]))
    lines = bundle.ks_cfg.splitlines()
    part_lines = [line for line in lines if line.startswith("part ")]
    assert len(part_lines) == 3, f"expected 3 part lines, got {part_lines}"
    for line in part_lines:
        assert "--ondisk=vda" in line, f"missing --ondisk=vda on: {line}"


def test_minimal_targeted_disk_emits_ignoredisk():
    yaml_path = Path(__file__).parent / "minimal-targeted-disk.host.yaml"
    bundle = build_bundle(load_host_config(yaml_path, sets=[]))
    assert "ignoredisk --only-use=sda" in bundle.ks_cfg


def test_minimal_targeted_disk_clearpart_carries_drives():
    yaml_path = Path(__file__).parent / "minimal-targeted-disk.host.yaml"
    bundle = build_bundle(load_host_config(yaml_path, sets=[]))
    assert "clearpart --all --initlabel --drives=sda" in bundle.ks_cfg


def test_minimal_targeted_disk_bootloader_carries_boot_drive():
    yaml_path = Path(__file__).parent / "minimal-targeted-disk.host.yaml"
    bundle = build_bundle(load_host_config(yaml_path, sets=[]))
    bootloader_line = next(
        line for line in bundle.ks_cfg.splitlines() if line.startswith("bootloader ")
    )
    assert "--boot-drive=sda" in bootloader_line
