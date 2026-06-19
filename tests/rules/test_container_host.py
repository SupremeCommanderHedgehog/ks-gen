from ks_gen.config import Containers, ContainerUser
from ks_gen.rules.alma9.container_host import RULE


def test_container_host_rule_id_and_summary():
    assert RULE.id == "container_host"
    assert "rootless" in RULE.summary.lower() or "container" in RULE.summary.lower()


def test_container_host_rule_does_not_apply_by_default(minimal_cfg):
    assert RULE.applies(minimal_cfg) is False


def test_container_host_rule_applies_when_enabled(minimal_cfg):
    enabled_cfg = minimal_cfg.model_copy(update={"containers": Containers(enabled=True)})
    assert RULE.applies(enabled_cfg) is True


def test_container_host_emit_packages_returns_podman_stack(minimal_cfg):
    pkgs = RULE.emit_packages(minimal_cfg)
    assert "podman" in pkgs
    assert "crun" in pkgs
    assert "slirp4netns" in pkgs
    assert "fuse-overlayfs" in pkgs
    assert "containers-common" in pkgs
    assert "podman-plugins" in pkgs
    # semanage(8) for SELinux fcontext setup by the helper script
    assert "policycoreutils-python-utils" in pkgs


def test_container_host_emit_tailoring_is_empty(minimal_cfg):
    assert RULE.emit_tailoring(minimal_cfg) == []


def test_container_host_exception_entry_is_none(minimal_cfg):
    assert RULE.exception_entry(minimal_cfg) is None


def test_container_host_rule_is_discoverable():
    from ks_gen.registry import load_rules

    rule_ids = {r.id for r in load_rules("alma9")}
    assert "container_host" in rule_ids


def test_container_host_emit_post_drops_script_and_storage_conf(minimal_cfg):
    cfg = minimal_cfg.model_copy(update={"containers": Containers(enabled=True)})
    body = RULE.emit_post(cfg)

    # Script lands at /root with 0550 perms
    assert "cat > /root/create-rootless-user.sh <<'__KS_GEN_EOF__'" in body
    assert "chmod 0550 /root/create-rootless-user.sh" in body
    assert "chown root:root /root/create-rootless-user.sh" in body

    # storage.conf with rootless_storage_path pointing at the mirror
    assert "cat > /etc/containers/storage.conf <<'__KS_GEN_EOF__'" in body
    assert 'rootless_storage_path = "/srv/containers/$USER/storage"' in body


def test_container_host_emit_post_empty_users_still_drops_script(minimal_cfg):
    cfg = minimal_cfg.model_copy(update={"containers": Containers(enabled=True, users=[])})
    body = RULE.emit_post(cfg)

    assert "/root/create-rootless-user.sh" in body
    # No per-user provisioning calls when users list is empty
    assert "-l -c" not in body


def test_container_host_emit_post_provisions_each_user(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={
            "containers": Containers(
                enabled=True,
                users=[
                    ContainerUser(
                        name="webapp",
                        gecos="Web app workloads",
                        authorized_keys=["ssh-ed25519 K1 w@bastion"],
                    ),
                    ContainerUser(
                        name="dbproxy",
                        authorized_keys=["ssh-ed25519 K2 d@bastion"],
                    ),
                ],
            )
        }
    )
    body = RULE.emit_post(cfg)

    # Each user gets a script invocation with -l (linger always-on at kickstart)
    assert '/root/create-rootless-user.sh -l -c "Web app workloads" webapp' in body
    # gecos defaults to name when empty
    assert '/root/create-rootless-user.sh -l -c "dbproxy" dbproxy' in body

    # Per-user authorized_keys file written after the script call
    assert "install -d -m 0700 -o webapp -g webapp /home/webapp/.ssh" in body
    assert "/home/webapp/.ssh/authorized_keys" in body
    assert "install -d -m 0700 -o dbproxy -g dbproxy /home/dbproxy/.ssh" in body
    assert "/home/dbproxy/.ssh/authorized_keys" in body


def test_container_host_emit_post_handles_multiple_keys(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={
            "containers": Containers(
                enabled=True,
                users=[
                    ContainerUser(
                        name="webapp",
                        authorized_keys=[
                            "ssh-ed25519 KEY_ONE webapp@bastion",
                            "ssh-ed25519 KEY_TWO webapp@laptop",
                        ],
                    ),
                ],
            )
        }
    )
    body = RULE.emit_post(cfg)

    assert "ssh-ed25519 KEY_ONE webapp@bastion" in body
    assert "ssh-ed25519 KEY_TWO webapp@laptop" in body


def test_container_host_emit_post_no_quadlet_scaffold(minimal_cfg):
    # Kickstart-time provisioning never passes -q (Quadlet scaffold is
    # post-install only).
    cfg = minimal_cfg.model_copy(
        update={
            "containers": Containers(
                enabled=True,
                users=[ContainerUser(name="webapp", authorized_keys=["ssh-ed25519 K w@h"])],
            )
        }
    )
    body = RULE.emit_post(cfg)

    for line in body.splitlines():
        if line.strip().startswith("/root/create-rootless-user.sh "):
            assert " -q" not in line
