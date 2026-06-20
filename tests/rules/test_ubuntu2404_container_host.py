from ks_gen.config import Containers, ContainerUser
from ks_gen.rules.ubuntu2404.container_host import RULE


def test_container_host_rule_id_and_summary():
    assert RULE.id == "container_host"
    assert "rootless" in RULE.summary.lower() or "container" in RULE.summary.lower()


def test_container_host_rule_does_not_apply_by_default(ubuntu_cfg_factory):
    assert RULE.applies(ubuntu_cfg_factory()) is False


def test_container_host_rule_applies_when_enabled(ubuntu_cfg_factory):
    cfg = ubuntu_cfg_factory().model_copy(update={"containers": Containers(enabled=True)})
    assert RULE.applies(cfg) is True


def test_container_host_emit_packages_returns_ubuntu_podman_stack(ubuntu_cfg_factory):
    pkgs = RULE.emit_packages(ubuntu_cfg_factory())
    # Ubuntu-available subset
    assert "podman" in pkgs
    assert "crun" in pkgs
    assert "slirp4netns" in pkgs
    assert "fuse-overlayfs" in pkgs
    # alma9-only / SELinux-only packages MUST NOT leak in
    assert "containers-common" not in pkgs
    assert "podman-plugins" not in pkgs
    assert "policycoreutils-python-utils" not in pkgs


def test_container_host_emit_tailoring_is_empty(ubuntu_cfg_factory):
    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []


def test_container_host_exception_entry_is_none(ubuntu_cfg_factory):
    assert RULE.exception_entry(ubuntu_cfg_factory()) is None


def test_container_host_emit_post_drops_script_and_storage_conf(ubuntu_cfg_factory):
    cfg = ubuntu_cfg_factory().model_copy(update={"containers": Containers(enabled=True)})
    body = RULE.emit_post(cfg)

    # Script lands at /root with 0550 perms
    assert "cat > /root/create-rootless-user.sh <<'__KS_GEN_EOF__'" in body
    assert "chmod 0550 /root/create-rootless-user.sh" in body
    assert "chown root:root /root/create-rootless-user.sh" in body

    # storage.conf with rootless_storage_path pointing at the mirror
    assert "cat > /etc/containers/storage.conf <<'__KS_GEN_EOF__'" in body
    assert 'rootless_storage_path = "/srv/containers/$USER/storage"' in body


def test_container_host_emit_post_empty_users_still_drops_script(ubuntu_cfg_factory):
    cfg = ubuntu_cfg_factory().model_copy(update={"containers": Containers(enabled=True, users=[])})
    body = RULE.emit_post(cfg)

    assert "/root/create-rootless-user.sh" in body
    # No per-user provisioning calls when users list is empty
    assert "-l -c" not in body


def test_container_host_emit_post_provisions_each_user(ubuntu_cfg_factory):
    cfg = ubuntu_cfg_factory().model_copy(
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


def test_container_host_emit_post_handles_multiple_keys(ubuntu_cfg_factory):
    cfg = ubuntu_cfg_factory().model_copy(
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


def test_container_host_emit_post_no_quadlet_scaffold(ubuntu_cfg_factory):
    # Kickstart-time provisioning never passes -q (Quadlet scaffold is
    # post-install only).
    cfg = ubuntu_cfg_factory().model_copy(
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


def test_container_host_emit_post_drops_restorecon_calls(ubuntu_cfg_factory):
    # Key Ubuntu port assertion. The alma9 rule writes
    # `restorecon -R /home/<user>/.ssh` after each authorized_keys
    # block; this port drops it (no SELinux on Ubuntu).
    cfg = ubuntu_cfg_factory().model_copy(
        update={
            "containers": Containers(
                enabled=True,
                users=[ContainerUser(name="webapp", authorized_keys=["ssh-ed25519 K w@h"])],
            )
        }
    )
    body = RULE.emit_post(cfg)
    assert "restorecon" not in body


def test_container_host_helper_script_drops_semanage_calls(ubuntu_cfg_factory):
    # Key Ubuntu port assertion on the embedded helper script:
    # `semanage` should not appear anywhere — the SELinux fcontext
    # equivalence + preflight check are removed in the Ubuntu helper.
    cfg = ubuntu_cfg_factory().model_copy(update={"containers": Containers(enabled=True)})
    body = RULE.emit_post(cfg)
    assert "semanage" not in body


def test_container_host_helper_script_drops_restorecon_calls(ubuntu_cfg_factory):
    # Catches the script's internal `restorecon` lines (Quadlet branch,
    # per-user storage, .ssh) that alma9 has and Ubuntu's helper drops.
    cfg = ubuntu_cfg_factory().model_copy(update={"containers": Containers(enabled=True)})
    body = RULE.emit_post(cfg)
    # The previous test already asserts no restorecon in body — this one
    # is the explicit helper-script callout for the audit trail.
    assert "restorecon" not in body


def test_container_host_helper_script_targets_ubuntu(ubuntu_cfg_factory):
    # The helper script docstring identifies its target distro. Pins
    # against an accidental swap back to the alma9 helper.
    cfg = ubuntu_cfg_factory().model_copy(update={"containers": Containers(enabled=True)})
    body = RULE.emit_post(cfg)
    assert "Ubuntu 24.04 LTS" in body
    assert "AlmaLinux 9" not in body


def test_container_host_rule_is_discoverable():
    from ks_gen.registry import load_rules

    rule_ids = {r.id for r in load_rules("ubuntu2404")}
    assert "container_host" in rule_ids
