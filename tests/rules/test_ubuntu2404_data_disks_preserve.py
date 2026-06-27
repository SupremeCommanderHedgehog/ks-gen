from ks_gen.config import DataDisk, Disk
from ks_gen.rules.ubuntu2404.data_disks_preserve import RULE


def test_rule_metadata():
    assert RULE.id == "data_disks_preserve"
    assert RULE.depends_on == []
    assert RULE.stig_rules_affected == []


def test_rule_does_not_apply_with_no_data_disks(ubuntu_cfg_factory):
    assert RULE.applies(ubuntu_cfg_factory()) is False


def test_rule_does_not_apply_when_all_data_disks_wiped(ubuntu_cfg_factory):
    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "disk": Disk(
                target="sda",
                data_disks=[DataDisk(target="sdb", mount="/data", wipe=True)],
            )
        }
    )
    assert RULE.applies(cfg) is False


def test_rule_applies_when_any_data_disk_preserved(ubuntu_cfg_factory):
    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "disk": Disk(
                target="sda",
                data_disks=[
                    DataDisk(target="sdb", mount="/data", wipe=False, partition_label="keep")
                ],
            )
        }
    )
    assert RULE.applies(cfg) is True


def test_rule_emit_post_preserve_by_partition_number(ubuntu_cfg_factory):
    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "disk": Disk(
                target="sda",
                data_disks=[
                    DataDisk(
                        target="disk/by-id/ata-WDC_FOO",
                        mount="/data",
                        wipe=False,
                        partition=2,
                    )
                ],
            )
        }
    )
    body = RULE.emit_post(cfg)
    assert "mkdir -p /data" in body
    assert (
        'echo "/dev/disk/by-id/ata-WDC_FOO-part2 /data xfs nodev,nosuid 0 2" >> /etc/fstab' in body
    )
    assert "mount -a" in body


def test_rule_emit_post_preserve_by_uuid(ubuntu_cfg_factory):
    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "disk": Disk(
                target="sda",
                data_disks=[
                    DataDisk(
                        target="sdb",
                        mount="/data",
                        wipe=False,
                        partition_uuid="0f2a-1c3b-4d5e-6f7a",
                    )
                ],
            )
        }
    )
    body = RULE.emit_post(cfg)
    assert 'echo "UUID=0f2a-1c3b-4d5e-6f7a /data xfs nodev,nosuid 0 2" >> /etc/fstab' in body


def test_rule_emit_post_preserve_by_label(ubuntu_cfg_factory):
    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "disk": Disk(
                target="sda",
                data_disks=[
                    DataDisk(
                        target="sdb",
                        mount="/data",
                        wipe=False,
                        partition_label="preserve_test",
                    )
                ],
            )
        }
    )
    body = RULE.emit_post(cfg)
    assert 'echo "LABEL=preserve_test /data xfs nodev,nosuid 0 2" >> /etc/fstab' in body


def test_rule_emit_post_uses_defaults_when_fsoptions_null(ubuntu_cfg_factory):
    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "disk": Disk(
                target="sda",
                data_disks=[
                    DataDisk(
                        target="disk/by-id/ata-CHEAPSSD",
                        mount="/data",
                        wipe=False,
                        partition=1,
                        fsoptions=None,
                    )
                ],
            )
        }
    )
    body = RULE.emit_post(cfg)
    assert 'echo "/dev/disk/by-id/ata-CHEAPSSD-part1 /data xfs defaults 0 2" >> /etc/fstab' in body


def test_rule_emit_post_only_includes_preserved_disks(ubuntu_cfg_factory):
    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "disk": Disk(
                target="sda",
                data_disks=[
                    DataDisk(target="sdb", mount="/wiped"),
                    DataDisk(
                        target="sdc",
                        mount="/data",
                        wipe=False,
                        partition_label="keep",
                    ),
                ],
            )
        }
    )
    body = RULE.emit_post(cfg)
    assert "/wiped" not in body
    assert "LABEL=keep /data xfs" in body


def test_rule_emit_post_handles_multiple_preserved_disks(ubuntu_cfg_factory):
    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "disk": Disk(
                target="sda",
                data_disks=[
                    DataDisk(
                        target="sdb",
                        mount="/data",
                        wipe=False,
                        partition_label="data_lbl",
                    ),
                    DataDisk(
                        target="sdc",
                        mount="/archive",
                        wipe=False,
                        partition_uuid="abcd-1234",
                    ),
                ],
            )
        }
    )
    body = RULE.emit_post(cfg)
    assert "mkdir -p /data" in body
    assert "mkdir -p /archive" in body
    assert "LABEL=data_lbl /data xfs" in body
    assert "UUID=abcd-1234 /archive xfs" in body


def test_rule_emit_post_drops_restorecon(ubuntu_cfg_factory):
    # Key Ubuntu port assertion. SELinux file labels have no Ubuntu
    # analog; the alma9 rule's trailing `restorecon -R <mounts>` line
    # is removed. AppArmor has no per-path relabel operation.
    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "disk": Disk(
                target="sda",
                data_disks=[
                    DataDisk(
                        target="sdb",
                        mount="/data",
                        wipe=False,
                        partition_label="data_lbl",
                    ),
                    DataDisk(
                        target="sdc",
                        mount="/archive",
                        wipe=False,
                        partition_uuid="abcd-1234",
                    ),
                ],
            )
        }
    )
    body = RULE.emit_post(cfg)
    assert "restorecon" not in body
    # And the body's last meaningful line is `mount -a` (no trailing relabel).
    assert body.rstrip().endswith("mount -a")


def test_rule_emit_packages_is_empty(ubuntu_cfg_factory):
    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "disk": Disk(
                target="sda",
                data_disks=[
                    DataDisk(
                        target="disk/by-id/ata-CHEAPSSD",
                        mount="/data",
                        wipe=False,
                        partition=1,
                    )
                ],
            )
        }
    )
    assert RULE.emit_packages(cfg) == []


def test_rule_protocol_contract(ubuntu_cfg_factory):
    from ks_gen.rules._meta import data_disks_preserve as meta

    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []
    assert RULE.exception_entry(ubuntu_cfg_factory()) is None
    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY


def test_rule_is_discoverable():
    from ks_gen.registry import load_rules

    rule_ids = {r.id for r in load_rules("ubuntu2404")}
    assert "data_disks_preserve" in rule_ids
