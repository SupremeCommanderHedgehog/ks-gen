from ks_gen.skeleton import render_skeleton


def test_skeleton_has_required_kickstart_directives(minimal_cfg):
    out = render_skeleton(minimal_cfg, post_blocks=["# rule blocks go here"])
    assert "text\n" in out
    assert "lang en_US.UTF-8\n" in out
    assert "keyboard us\n" in out
    assert "timezone UTC --utc\n" in out
    assert "rootpw --lock" in out
    assert "%packages" in out
    assert "scap-security-guide" in out
    assert "%addon org_fedora_oscap" in out
    assert "tailoring-path = /tailoring.xml" in out
    assert "%post --erroronfail --log=/root/ks-post.log" in out
    assert "# rule blocks go here" in out
    assert out.rstrip().endswith("reboot --eject")


def test_skeleton_static_interface_emits_static_args(minimal_cfg):
    from ks_gen.config import Interface, Network

    cfg = minimal_cfg.model_copy(
        update={
            "network": Network(
                interfaces=[
                    Interface(
                        device="enp1s0",
                        bootproto="static",
                        ip="10.0.0.10",
                        netmask="255.255.255.0",
                        gateway="10.0.0.1",
                        nameservers=["1.1.1.1"],
                    )
                ]
            )
        }
    )
    out = render_skeleton(cfg, post_blocks=[])
    assert "--ip=10.0.0.10" in out
    assert "--nameserver=1.1.1.1" in out


def test_skeleton_partition_preset_stig_server(minimal_cfg):
    out = render_skeleton(minimal_cfg, post_blocks=[])
    assert "/var/log/audit" in out
    assert "noexec" in out
