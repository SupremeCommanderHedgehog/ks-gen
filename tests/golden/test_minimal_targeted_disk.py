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


def test_minimal_targeted_disk_wipe_false_keeps_ignoredisk_and_bootdrive():
    """When wipe=False+target=sda, ignoredisk and --boot-drive emit, clearpart does not."""
    import tempfile

    yaml = (
        "system:\n  hostname: nowipetargeted.example.com\n"
        "user:\n  admin:\n    name: opsadmin\n"
        "    authorized_keys:\n"
        '      - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEYnowipe ops@bastion"\n'
        "    sudo: nopasswd_yes\n"
        "disk:\n  target: sda\n  wipe: false\n  preset: minimal\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".host.yaml", delete=False) as fh:
        fh.write(yaml)
        path = Path(fh.name)
    try:
        bundle = build_bundle(load_host_config(path, sets=[]))
    finally:
        path.unlink()
    ks = bundle.ks_cfg
    assert "ignoredisk --only-use=sda" in ks
    bootloader_line = next(line for line in ks.splitlines() if line.startswith("bootloader "))
    assert "--boot-drive=sda" in bootloader_line
    assert "clearpart" not in ks
    assert "zerombr" not in ks


def test_data_disks_wipe_extends_ignoredisk_and_clearpart_and_adds_part():
    import tempfile

    yaml = (
        "system:\n  hostname: twodisk.example.com\n"
        "user:\n  admin:\n    name: opsadmin\n"
        "    authorized_keys:\n"
        '      - "ssh-ed25519 AAAA test@bastion"\n'
        "    sudo: nopasswd_yes\n"
        "disk:\n"
        "  target: sda\n"
        "  preset: stig_server\n"
        "  data_disks:\n"
        "    - target: sdb\n"
        "      mount: /data\n"
        "      fstype: xfs\n"
        "      wipe: true\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".host.yaml", delete=False) as fh:
        fh.write(yaml)
        path = Path(fh.name)
    try:
        bundle = build_bundle(load_host_config(path, sets=[]))
    finally:
        path.unlink()
    ks = bundle.ks_cfg
    assert "ignoredisk --only-use=sda,sdb" in ks
    assert "clearpart --all --initlabel --drives=sda,sdb" in ks
    bootloader_line = next(line for line in ks.splitlines() if line.startswith("bootloader "))
    assert "--boot-drive=sda" in bootloader_line
    assert 'part /data --fstype=xfs --grow --size=1 --ondisk=sdb --fsoptions="nodev,nosuid"' in ks


def test_data_disks_preserve_omits_target_from_ignoredisk():
    import tempfile

    yaml = (
        "system:\n  hostname: presrv.example.com\n"
        "user:\n  admin:\n    name: opsadmin\n"
        "    authorized_keys:\n"
        '      - "ssh-ed25519 AAAA test@bastion"\n'
        "    sudo: nopasswd_yes\n"
        "disk:\n"
        "  target: sda\n"
        "  preset: stig_server\n"
        "  data_disks:\n"
        "    - target: disk/by-id/ata-PRESERVE_TEST_SDB\n"
        "      mount: /data\n"
        "      wipe: false\n"
        "      partition: 1\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".host.yaml", delete=False) as fh:
        fh.write(yaml)
        path = Path(fh.name)
    try:
        bundle = build_bundle(load_host_config(path, sets=[]))
    finally:
        path.unlink()
    ks = bundle.ks_cfg
    # preserve disk -> NOT in ignoredisk, NOT in clearpart drives, NO part line
    assert "ignoredisk --only-use=sda" in ks
    assert "ata-PRESERVE_TEST_SDB" not in ks.split("ignoredisk")[1].split("\n")[0]
    assert "clearpart --all --initlabel --drives=sda" in ks
    assert "--ondisk=disk/by-id/ata-PRESERVE_TEST_SDB" not in ks
    # The %post rule writes the fstab entry
    expected_fstab = (
        'echo "/dev/disk/by-id/ata-PRESERVE_TEST_SDB-part1 /data xfs nodev,nosuid 0 2"'
        " >> /etc/fstab"
    )
    assert expected_fstab in ks
