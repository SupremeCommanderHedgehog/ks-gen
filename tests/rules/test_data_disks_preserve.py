from ks_gen.config import DataDisk, Disk
from ks_gen.rules.alma9.data_disks_preserve import RULE


def test_data_disks_preserve_rule_metadata():
    assert RULE.id == "data_disks_preserve"
    assert RULE.depends_on == []
    assert RULE.stig_rules_affected == []


def test_rule_does_not_apply_with_no_data_disks(minimal_cfg):
    assert RULE.applies(minimal_cfg) is False


def test_rule_does_not_apply_when_all_data_disks_wiped(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={
            "disk": Disk(
                target="sda",
                data_disks=[DataDisk(target="sdb", mount="/data", wipe=True)],
            )
        }
    )
    assert RULE.applies(cfg) is False


def test_rule_applies_when_any_data_disk_preserved(minimal_cfg):
    cfg = minimal_cfg.model_copy(
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


def test_rule_emit_post_preserve_by_partition_number(minimal_cfg):
    cfg = minimal_cfg.model_copy(
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
    assert "restorecon -R /data" in body


def test_rule_emit_post_preserve_by_uuid(minimal_cfg):
    cfg = minimal_cfg.model_copy(
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


def test_rule_emit_post_preserve_by_label(minimal_cfg):
    cfg = minimal_cfg.model_copy(
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


def test_rule_emit_post_uses_defaults_when_fsoptions_null(minimal_cfg):
    cfg = minimal_cfg.model_copy(
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


def test_rule_emit_post_only_includes_preserved_disks(minimal_cfg):
    cfg = minimal_cfg.model_copy(
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


def test_rule_emit_post_handles_multiple_preserved_disks(minimal_cfg):
    cfg = minimal_cfg.model_copy(
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
    # restorecon takes both mounts on one line
    assert "restorecon -R /data /archive" in body


def test_rule_emit_packages_is_empty(minimal_cfg):
    cfg = minimal_cfg.model_copy(
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


def test_rule_emit_tailoring_is_empty(minimal_cfg):
    assert RULE.emit_tailoring(minimal_cfg) == []


def test_rule_exception_entry_is_none(minimal_cfg):
    assert RULE.exception_entry(minimal_cfg) is None


def test_rule_is_discoverable():
    from ks_gen.registry import load_rules

    rule_ids = {r.id for r in load_rules("alma9")}
    assert "data_disks_preserve" in rule_ids
