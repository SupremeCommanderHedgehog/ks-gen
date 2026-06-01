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
    assert "%addon org_fedora_oscap" not in out, (
        "v0.1.1: addon dropped in favor of %post-driven oscap"
    )
    assert "%post --erroronfail --log=/root/ks-post-oscap.log" in out
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


def test_skeleton_emits_oscap_post_block(minimal_cfg):
    out = render_skeleton(minimal_cfg, post_blocks=["# rule blocks go here"])

    oscap_idx = out.find("%post --erroronfail --log=/root/ks-post-oscap.log")
    overrides_idx = out.find("%post --erroronfail --log=/root/ks-post.log")
    packages_idx = out.find("%packages")

    assert oscap_idx != -1, "missing oscap %post block"
    assert overrides_idx != -1, "missing rule-overrides %post block"
    assert packages_idx != -1, "missing %packages block"
    assert packages_idx < oscap_idx < overrides_idx, (
        "expected order: %packages < oscap %post < overrides %post"
    )

    oscap_body = out[oscap_idx:overrides_idx]
    assert "set -euo pipefail" in oscap_body, "missing strict shell flags"
    assert "/proc/cmdline" in oscap_body, "must derive transport from cmdline"
    assert "http://*|https://*" in oscap_body, "missing HTTP case branch"
    assert "curl -fsSL --retry 5 --retry-delay 3" in oscap_body, "missing curl with retry"
    assert "/root/tailoring.xml" in oscap_body, (
        "tailoring must land in /root/ on the installed system"
    )
    assert "head -c 5 /root/tailoring.xml | grep -q '<?xml'" in oscap_body, (
        "missing xml sentinel check"
    )
    assert "oscap xccdf eval --remediate" in oscap_body, "missing oscap remediation invocation"
    assert "--tailoring-file /root/tailoring.xml" in oscap_body, (
        "oscap must consume the fetched tailoring"
    )
    assert "/usr/share/xml/scap/ssg/content/ssg-almalinux9-ds.xml" in oscap_body, (
        "missing SSG datastream path"
    )
    assert "unsupported inst.ks transport" in oscap_body, (
        "missing fallback hard-fail for unknown transport"
    )
    assert oscap_body.count("%end") >= 1, "oscap %post block not closed"
