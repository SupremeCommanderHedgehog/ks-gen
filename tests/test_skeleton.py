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

    fetch_idx = out.find("%post --nochroot --erroronfail")
    eval_idx = out.find("%post --erroronfail --log=/root/ks-post-oscap.log")
    overrides_idx = out.find("%post --erroronfail --log=/root/ks-post.log")
    packages_idx = out.find("%packages")

    assert fetch_idx != -1, "missing fetch %post --nochroot block"
    assert eval_idx != -1, "missing eval %post --erroronfail block"
    assert overrides_idx != -1, "missing rule-overrides %post block"
    assert packages_idx != -1, "missing %packages block"
    assert packages_idx < fetch_idx < eval_idx < overrides_idx, (
        "expected order: %packages < fetch %post < eval %post < overrides %post"
    )

    fetch_body = out[fetch_idx:eval_idx]
    eval_body = out[eval_idx:overrides_idx]
    oscap_body = out[fetch_idx:overrides_idx]

    # Fetch block checks: transport detection and tailoring staging
    assert "set -euo pipefail" in fetch_body, "missing strict shell flags in fetch block"
    assert "/proc/cmdline" in fetch_body, "must derive transport from cmdline in fetch block"
    assert "http://*|https://*" in fetch_body, "missing HTTP case branch in fetch block"
    assert "curl -fsSL --retry 5 --retry-delay 3" in fetch_body, (
        "missing curl with retry in fetch block"
    )
    assert "/mnt/sysimage/root/tailoring.xml" in fetch_body, (
        "tailoring must stage to /mnt/sysimage/root/ in fetch block"
    )
    assert "hd:LABEL=*)" in fetch_body, "missing hd:LABEL case branch in fetch block"
    assert "unsupported inst.ks transport" in fetch_body, (
        "missing fallback hard-fail for unknown transport in fetch block"
    )

    # Eval block checks: oscap remediation
    assert "set -euo pipefail" in eval_body, "missing strict shell flags in eval block"
    assert "head -c 5 /root/tailoring.xml | grep -q '<?xml'" in eval_body, (
        "missing xml sentinel check in eval block"
    )
    assert "oscap xccdf eval --remediate" in eval_body, "missing oscap remediation invocation"
    assert "--fetch-remote-resources" in eval_body, (
        "oscap eval must fetch remote OVAL resources at install time"
    )
    assert "--tailoring-file /root/tailoring.xml" in eval_body, (
        "oscap must consume the fetched tailoring"
    )
    assert "/usr/share/xml/scap/ssg/content/ssg-almalinux9-ds.xml" in eval_body, (
        "missing SSG datastream path"
    )
    assert oscap_body.count("%end") == 2, "exactly two %end markers (fetch and eval blocks)"
