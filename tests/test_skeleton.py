import os
import shutil
import subprocess

import pytest

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


def test_skeleton_jinja_env_exposes_disk_layout_helpers():
    from ks_gen.skeleton import _env

    env = _env()
    assert "effective_size_mb" in env.globals
    assert "effective_fsoptions" in env.globals
    assert "size_to_mb" in env.globals


def test_skeleton_renders_layout_partial_when_layout_set():
    from ks_gen.config import (
        AdminUser,
        Disk,
        DiskLayout,
        DiskLvDef,
        HostConfig,
        System,
        User,
    )
    from ks_gen.skeleton import render_skeleton

    admin = AdminUser(name="ops", authorized_keys=["ssh-ed25519 A a@b"], sudo="nopasswd_yes")
    cfg = HostConfig(
        system=System(hostname="x"),
        user=User(admin=admin),
        disk=Disk(
            layout=DiskLayout(
                lvs=[
                    DiskLvDef(name="root", mount="/"),
                    DiskLvDef(name="home", mount="/home"),
                    DiskLvDef(name="tmp", mount="/tmp"),
                    DiskLvDef(name="var", mount="/var"),
                    DiskLvDef(name="varlog", mount="/var/log"),
                    DiskLvDef(name="varlogaudit", mount="/var/log/audit"),
                    DiskLvDef(name="vartmp", mount="/var/tmp"),
                    DiskLvDef(name="swap", fstype="swap"),
                ]
            )
        ),
    )
    out = render_skeleton(cfg, post_blocks=[])
    assert "part /boot/efi --fstype=efi" in out
    assert "volgroup vg_root pv.01" in out
    assert "logvol / --vgname=vg_root --name=root --fstype=xfs --size=15360" in out
    assert "logvol swap --vgname=vg_root --name=swap --fstype=swap --recommended" in out
    # Load-bearing exact-substring assertion (>100 chars by design — verifies
    # the layout partial renders fsoptions for STIG-default mountpoints).
    expected_audit_lv = 'logvol /var/log/audit --vgname=vg_root --name=varlogaudit --fstype=xfs --size=3072 --fsoptions="nodev,nosuid,noexec"'  # noqa: E501
    assert expected_audit_lv in out


def test_skeleton_still_renders_preset_partial_when_preset_set():
    from ks_gen.config import AdminUser, HostConfig, System, User
    from ks_gen.skeleton import render_skeleton

    admin = AdminUser(name="ops", authorized_keys=["ssh-ed25519 A a@b"], sudo="nopasswd_yes")
    cfg = HostConfig(
        system=System(hostname="x"),
        user=User(admin=admin),
    )
    out = render_skeleton(cfg, post_blocks=[])
    # The existing stig_server partial has aligned-column whitespace:
    assert "logvol /var/log/audit --vgname=vg_root --name=varlogaudit" in out


def test_skeleton_jinja_env_exposes_disk_luks_helpers():
    from ks_gen.skeleton import _env

    env = _env()
    assert "resolve_passphrase" in env.globals
    assert "kickstart_passphrase_quoted" in env.globals


def test_skeleton_luks_macro_none_emits_empty():
    from ks_gen.config import AdminUser, HostConfig, System, User
    from ks_gen.skeleton import _env

    cfg = HostConfig(
        system=System(hostname="x"),
        user=User(
            admin=AdminUser(
                name="ops",
                authorized_keys=["ssh-ed25519 A a@b"],
                sudo="nopasswd_yes",
            )
        ),
    )
    env = _env()
    tmpl = env.from_string(
        "{% from 'partials/_luks_flags.j2' import luks_pv_flags %}"
        "BEFORE{{ luks_pv_flags(cfg) }}AFTER"
    )
    assert tmpl.render(cfg=cfg) == "BEFOREAFTER"


def test_skeleton_luks_macro_partial_emits_flags():
    from ks_gen.config import AdminUser, Disk, DiskLuks, HostConfig, System, User
    from ks_gen.skeleton import _env

    cfg = HostConfig(
        system=System(hostname="x"),
        user=User(
            admin=AdminUser(
                name="ops",
                authorized_keys=["ssh-ed25519 A a@b"],
                sudo="nopasswd_yes",
            )
        ),
        disk=Disk(luks=DiskLuks.model_validate({"preset": "partial", "passphrase": "hunter2"})),
    )
    env = _env()
    tmpl = env.from_string(
        "{% from 'partials/_luks_flags.j2' import luks_pv_flags %}"
        "BEFORE{{ luks_pv_flags(cfg) }}AFTER"
    )
    assert (
        tmpl.render(cfg=cfg)
        == 'BEFORE --encrypted --luks-version=luks2 --passphrase="hunter2"AFTER'
    )


def test_skeleton_tang_block_emitted_when_preset_tang():
    from ks_gen.config import AdminUser, Disk, DiskLuks, HostConfig, System, User
    from ks_gen.skeleton import render_skeleton

    cfg = HostConfig(
        system=System(hostname="x"),
        user=User(
            admin=AdminUser(
                name="ops",
                authorized_keys=["ssh-ed25519 A a@b"],
                sudo="nopasswd_yes",
            )
        ),
        disk=Disk(
            luks=DiskLuks.model_validate(
                {
                    "preset": "tang",
                    "passphrase": "fallback",
                    "tang": {
                        "servers": [
                            {
                                "url": "https://tang1.example.com",
                                "thumbprint": "xK3HFGm-AVOaJVlA8oFAo7uMcrJBhFCdwq8WX8gqXJU",
                            },
                            {
                                "url": "https://tang2.example.com",
                                "thumbprint": "yL4IGHn-BWPbKWmA9pBp8vNdsKChiGDexr9XY9hrYKV",
                            },
                        ],
                        "threshold": 1,
                    },
                }
            )
        ),
    )
    out = render_skeleton(cfg, post_blocks=[])
    assert "dnf -y install clevis clevis-luks clevis-systemd" in out
    assert 'clevis luks bind -d "$luks_dev" -y sss' in out
    assert '"url": "https://tang1.example.com"' in out
    assert '"url": "https://tang2.example.com"' in out
    assert '"thp": "xK3HFGm-AVOaJVlA8oFAo7uMcrJBhFCdwq8WX8gqXJU"' in out
    assert '"t": 1' in out
    assert "systemctl enable clevis-luks-askpass.path" in out


def test_skeleton_tang_block_not_emitted_for_partial():
    from ks_gen.config import AdminUser, Disk, DiskLuks, HostConfig, System, User
    from ks_gen.skeleton import render_skeleton

    cfg = HostConfig(
        system=System(hostname="x"),
        user=User(
            admin=AdminUser(
                name="ops",
                authorized_keys=["ssh-ed25519 A a@b"],
                sudo="nopasswd_yes",
            )
        ),
        disk=Disk(luks=DiskLuks.model_validate({"preset": "partial", "passphrase": "x"})),
    )
    out = render_skeleton(cfg, post_blocks=[])
    assert "clevis luks bind" not in out
    assert "clevis-luks-askpass" not in out


def _disk(kind: str):
    from ks_gen.config import Disk, DiskLayout, DiskLvDef

    if kind == "layout":
        mounts = {
            "root": "/",
            "home": "/home",
            "tmp": "/tmp",
            "var": "/var",
            "varlog": "/var/log",
            "varlogaudit": "/var/log/audit",
            "vartmp": "/var/tmp",
        }
        lvs = [DiskLvDef(name=n, mount=m) for n, m in mounts.items()]
        return Disk(
            layout=DiskLayout(lvs=[*lvs, DiskLvDef(name="swap", fstype="swap")]), target="vda"
        )
    return Disk(preset=kind, target="vda")


@pytest.mark.parametrize("kind", ["stig_server", "minimal", "layout"])
def test_skeleton_alma10_adds_biosboot_before_efi(minimal_cfg, kind):
    # AL10 labels every disk GPT, which BIOS firmware can't boot without a
    # biosboot partition; anaconda refuses the kickstart otherwise.
    cfg = minimal_cfg.model_copy(update={"distro": "alma10", "disk": _disk(kind)})
    parts = [
        line
        for line in render_skeleton(cfg, post_blocks=[]).splitlines()
        if line.startswith("part ")
    ]
    assert parts[0] == "part biosboot --fstype=biosboot --size=1 --ondisk=vda"
    assert parts[1].startswith("part /boot/efi ")


@pytest.mark.parametrize("kind", ["stig_server", "minimal", "layout"])
def test_skeleton_alma9_has_no_biosboot(minimal_cfg, kind):
    # AL8/9 give BIOS machines an msdos label, where biosboot doesn't belong.
    cfg = minimal_cfg.model_copy(update={"distro": "alma9", "disk": _disk(kind)})
    assert "biosboot" not in render_skeleton(cfg, post_blocks=[])


def test_skeleton_alma10_no_biosboot_without_wipe(minimal_cfg):
    # No clearpart, so the disk keeps its label; on msdos, biosboot can't exist.
    disk = _disk("stig_server").model_copy(update={"wipe": False})
    cfg = minimal_cfg.model_copy(update={"distro": "alma10", "disk": disk})
    assert "biosboot" not in render_skeleton(cfg, post_blocks=[])


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_skeleton_clears_aging_on_locked_regular_accounts_last(minimal_cfg, tmp_path):
    """#139: useradd after the STIG remediation gives accounts max 60 days and
    35 inactive, which a key-only account can never reset. The final pass must
    run after custom_post, in its own %post so an early `exit` there can't skip
    it, and clear aging only on regular accounts with no password to unlock."""
    cfg = minimal_cfg.model_copy(update={"custom_post": ["useradd -m opsadmin2\nexit 0"]})
    out = render_skeleton(cfg, post_blocks=[])
    marker = "# ===== key-only account aging (#139) ====="
    start = out.index(marker)
    assert out.index("%end", out.index("exit 0")) < start  # custom_post's %post closed first
    assert out.rindex("%post --erroronfail --log=/root/ks-post-aging.log", 0, start) > out.index(
        "exit 0"
    )
    block = out[start : out.index("%end", start)]

    etc = tmp_path / "etc"
    etc.mkdir()
    # A repeated key must not turn the bound into a string: the first wins.
    (etc / "login.defs").write_text(
        "PASS_MAX_DAYS 60\n#UID_MIN 5\nUID_MIN   1000\nUID_MAX 60000\nUID_MIN 1003\n"
    )
    accounts = {  # name: (uid, shadow password field)
        "root": (0, "!"),
        "sshd": (74, "!!"),
        "opsadmin": (1000, "!"),
        "webapp": (1001, "!!"),
        "legacy": (1002, "*"),
        "pwuser": (1003, "$6$salt$hash"),
        "staged": (1004, "!$6$salt$hash"),  # an unlock brings its password back
        "nobody": (65534, "!"),
    }
    (etc / "passwd").write_text(
        "".join(f"{n}:x:{uid}:{uid}::/home/{n}:/bin/bash\n" for n, (uid, _) in accounts.items())
    )
    (etc / "shadow").write_text(
        "".join(f"{n}:{pw}:20000:1:60:7:35::\n" for n, (_, pw) in accounts.items())
    )
    bindir = tmp_path / "bin"
    bindir.mkdir()
    calls = tmp_path / "chage.calls"
    (bindir / "chage").write_text(f'#!/usr/bin/env bash\necho "$*" >> {calls}\n')
    (bindir / "chage").chmod(0o755)

    script = "set -euo pipefail\n" + block.replace("/etc/", f"{etc}/")
    proc = subprocess.run(
        [shutil.which("bash") or "bash", "-c", script],
        capture_output=True,
        text=True,
        env={"PATH": f"{bindir}:{os.environ['PATH']}"},
    )
    assert proc.returncode == 0, proc.stderr
    assert calls.read_text().splitlines() == [
        f"-M 99999 -I -1 {n}" for n in ("opsadmin", "webapp", "legacy")
    ]
