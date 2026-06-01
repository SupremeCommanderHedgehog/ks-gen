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


def test_skeleton_emits_pre_tailoring_fetcher(minimal_cfg):
    out = render_skeleton(minimal_cfg, post_blocks=[])

    pre_idx = out.find("%pre --erroronfail --log=/tmp/ks-pre-tailoring.log")
    addon_idx = out.find("%addon org_fedora_oscap")
    packages_idx = out.find("%packages")

    assert pre_idx != -1, "missing %pre tailoring fetcher block"
    assert addon_idx != -1, "missing %addon block"
    assert packages_idx != -1, "missing %packages block"
    assert pre_idx < packages_idx < addon_idx, "expected order: %pre < %packages < %addon"

    pre_body = out[pre_idx:packages_idx]
    assert "set -euo pipefail" in pre_body, "missing strict shell flags"
    assert "[ -s /tailoring.xml ]" in pre_body, "missing idempotence guard"
    assert "/proc/cmdline" in pre_body, "must derive transport from cmdline"
    assert "http://*|https://*" in pre_body, "missing HTTP case branch"
    assert "hd:*" in pre_body, "missing hd: case branch"
    assert "curl -fsSL --retry 5 --retry-delay 3" in pre_body, "missing curl with retry"
    assert "/run/install/repo/tailoring.xml" in pre_body, "missing hd: source path"
    assert "head -c 5 /tailoring.xml | grep -q '<?xml'" in pre_body, "missing xml sentinel check"
    assert "exit 1" in pre_body, "missing fallback hard-fail for unknown transport"
    assert pre_body.count("%end") >= 1, "%pre block not closed"
