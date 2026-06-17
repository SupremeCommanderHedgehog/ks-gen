from __future__ import annotations

import io
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ks_gen.lint import lint_kickstart
from ks_gen.wizard import (
    WizardError,
    _disk,
    _network,
    _overrides,
    _prompts,
    run_wizard,
    write_initial,
)
from ks_gen.wizard import _core as _wizard_core
from ks_gen.writer import build_bundle, write_bundle


def _stdin(text: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace sys.stdin with an in-memory buffer feeding the wizard."""
    import sys

    monkeypatch.setattr(sys, "stdin", io.StringIO(text))


def test_non_interactive_requires_hostname():
    with pytest.raises(WizardError, match="Hostname"):
        run_wizard(interactive=False)


def test_interactive_minimal_inputs(monkeypatch: pytest.MonkeyPatch):
    # hostname, timezone (default), locale (default), admin name (default),
    # sudo (default), first SSH key, blank to stop, ssh port (default),
    # crypto policy (default)
    _stdin(
        "host01\n"  # hostname
        "\n"  # timezone -> default UTC
        "\n"  # locale   -> default en_US.UTF-8
        "\n"  # admin    -> default opsadmin
        "\n"  # sudo     -> default nopasswd_yes
        "ssh-ed25519 AAA test@example\n"
        "\n"  # blank line to stop key entry
        "\n"  # ssh port -> default 22
        "\n",  # crypto   -> default MODERN
        monkeypatch,
    )
    monkeypatch.setattr(_prompts, "ask_checkbox", lambda *_a, **_kw: [])
    cfg, yaml_text = run_wizard(interactive=True)
    assert cfg.system.hostname == "host01"
    assert cfg.system.timezone == "UTC"
    assert cfg.user.admin.name == "opsadmin"
    assert cfg.user.admin.sudo == "nopasswd_yes"
    assert cfg.user.admin.authorized_keys == ["ssh-ed25519 AAA test@example"]
    assert cfg.ssh.port == 22
    assert cfg.crypto.policy.value == "MODERN"
    # YAML output is deterministic, hostname appears first
    assert "host01" in yaml_text


def test_interactive_eof_mid_prompt_raises(monkeypatch: pytest.MonkeyPatch):
    _stdin("", monkeypatch)
    with pytest.raises(WizardError, match="unexpected EOF"):
        run_wizard(interactive=True)


def test_interactive_no_ssh_keys_raises(monkeypatch: pytest.MonkeyPatch):
    _stdin(
        "host01\n\n\n\n\n"  # hostname through sudo
        "\n",  # blank SSH key with none entered
        monkeypatch,
    )
    with pytest.raises(WizardError, match="missing required value: SSH public key"):
        run_wizard(interactive=True)


def test_write_initial_creates_host_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _stdin(
        "host01\n\n\n\n\nssh-ed25519 AAA test@example\n\n\n\n",
        monkeypatch,
    )
    monkeypatch.setattr(_prompts, "ask_checkbox", lambda *_a, **_kw: [])
    cfg, yaml_text = run_wizard(interactive=True)
    host_dir = write_initial(tmp_path, cfg, yaml_text)
    assert host_dir == tmp_path / "host01"
    assert (host_dir / "host.yaml").read_text(encoding="utf-8") == yaml_text


# --- _prompts adapter tests -------------------------------------------------


def _stub_questionary(monkeypatch: pytest.MonkeyPatch, name: str, return_value: Any) -> None:
    """Replace `_prompts._questionary.<name>` with a stub returning .ask() = value."""

    class _Q:
        def ask(self) -> Any:
            return return_value

    def _factory(*_a: object, **_kw: object) -> _Q:
        return _Q()

    monkeypatch.setattr(_prompts._questionary, name, _factory)


def test_select_one_returns_choice(monkeypatch: pytest.MonkeyPatch):
    _stub_questionary(monkeypatch, "select", "stig_server")
    assert _prompts.select_one("Disk preset:", ["stig_server", "minimal"]) == "stig_server"


def test_ask_text_returns_stripped_value(monkeypatch: pytest.MonkeyPatch):
    _stub_questionary(monkeypatch, "text", "  host01  ")
    assert _prompts.ask_text("Hostname:") == "host01"


def test_ask_confirm_returns_bool(monkeypatch: pytest.MonkeyPatch):
    _stub_questionary(monkeypatch, "confirm", True)
    assert _prompts.ask_confirm("Wipe disk?", default=True) is True


def test_ask_password_returns_value(monkeypatch: pytest.MonkeyPatch):
    _stub_questionary(monkeypatch, "password", "hunter2")
    assert _prompts.ask_password("Passphrase:") == "hunter2"


def test_ask_checkbox_returns_selected_list(monkeypatch: pytest.MonkeyPatch):
    _stub_questionary(monkeypatch, "checkbox", ["faillock", "package_purge"])
    got = _prompts.ask_checkbox("Disable:", [("faillock", "lockout"), ("package_purge", "purge")])
    assert got == ["faillock", "package_purge"]


def test_select_one_keyboard_interrupt_propagates(monkeypatch: pytest.MonkeyPatch):
    class _Q:
        def ask(self) -> Any:
            raise KeyboardInterrupt

    monkeypatch.setattr(_prompts._questionary, "select", lambda *_a, **_kw: _Q())
    with pytest.raises(KeyboardInterrupt):
        _prompts.select_one("x", ["a", "b"])


def test_select_one_none_return_raises_keyboard_interrupt(monkeypatch: pytest.MonkeyPatch):
    # questionary returns None (not raises) when stdin is non-interactive.
    # The adapter must turn that into KeyboardInterrupt so the orchestrator
    # can map it to WizardError("aborted by user").
    _stub_questionary(monkeypatch, "select", None)
    with pytest.raises(KeyboardInterrupt):
        _prompts.select_one("x", ["a", "b"])


# --- group-selector + orchestration tests -----------------------------------


def test_core_prompts_non_interactive_requires_hostname():
    with pytest.raises(WizardError, match="Hostname"):
        _wizard_core.prompts(interactive=False)


def test_run_wizard_non_interactive_skips_group_selector(monkeypatch: pytest.MonkeyPatch):
    # No questionary stub is needed — non-interactive must never call it.
    def _explode(*_a: object, **_kw: object) -> object:
        raise AssertionError("questionary was called in non-interactive mode")

    monkeypatch.setattr(_prompts, "ask_checkbox", _explode)

    with pytest.raises(WizardError, match="Hostname"):
        run_wizard(interactive=False)


def test_run_wizard_empty_group_selector_matches_legacy(monkeypatch: pytest.MonkeyPatch):
    """With no optional groups selected, YAML must equal today's output."""
    _stdin(
        "host01\n\n\n\n\nssh-ed25519 AAA test@example\n\n\n\n",
        monkeypatch,
    )
    # Group selector returns empty list (no optional groups).
    monkeypatch.setattr(_prompts, "ask_checkbox", lambda *_a, **_kw: [])

    _cfg, yaml_text = run_wizard(interactive=True)
    # Build the legacy payload from the same inputs to compare.
    import yaml

    legacy = {
        "system": {"hostname": "host01", "timezone": "UTC", "locale": "en_US.UTF-8"},
        "user": {
            "admin": {
                "name": "opsadmin",
                "authorized_keys": ["ssh-ed25519 AAA test@example"],
                "sudo": "nopasswd_yes",
            }
        },
        "ssh": {"port": 22},
        "crypto": {"policy": "MODERN"},
    }
    from ks_gen.config import HostConfig

    legacy_cfg = HostConfig.model_validate(legacy)
    legacy_yaml = yaml.safe_dump(
        legacy_cfg.model_dump(mode="json"), sort_keys=False, default_flow_style=False
    )
    assert yaml_text == legacy_yaml


# --- _disk group tests -----------------------------------------------------


def _scripted(monkeypatch: pytest.MonkeyPatch, scripts: dict[str, list[Any]]) -> None:
    """Replace _prompts.* functions with scripted pop-front queues.

    Each key in `scripts` maps to a list of values popped per call.
    Raises IndexError if the wizard asks more times than scripted.
    """
    for name, values in scripts.items():
        queue = list(values)

        def _make(q: list[Any]) -> Callable[..., Any]:
            def _f(*_a: object, **_kw: object) -> Any:
                return q.pop(0)

            return _f

        monkeypatch.setattr(_prompts, name, _make(queue))


def test_disk_stig_server_no_luks(monkeypatch: pytest.MonkeyPatch):
    _scripted(
        monkeypatch,
        {
            "select_one": ["stig_server", "none"],
            "ask_confirm": [True, False],  # wipe = true, add data disk? no
        },
    )
    payload = _disk.prompts()
    assert payload == {
        "preset": "stig_server",
        "wipe": True,
        "luks": {"preset": "none"},
    }


def test_disk_stig_server_no_wipe(monkeypatch: pytest.MonkeyPatch):
    _scripted(
        monkeypatch,
        {
            "select_one": ["stig_server", "none"],
            "ask_confirm": [False, False],
        },
    )
    payload = _disk.prompts()
    assert payload["wipe"] is False


def test_disk_minimal_skips_luks_prompt(monkeypatch: pytest.MonkeyPatch):
    # Only one select_one call (preset). If LUKS were asked, the queue
    # would underflow and IndexError would be raised.
    _scripted(
        monkeypatch,
        {
            "select_one": ["minimal"],
            "ask_confirm": [True],
        },
    )
    payload = _disk.prompts()
    assert payload == {"preset": "minimal", "wipe": True}
    assert "luks" not in payload


def test_disk_luks_partial_inline_match(monkeypatch: pytest.MonkeyPatch):
    _scripted(
        monkeypatch,
        {
            "select_one": ["stig_server", "partial", "inline"],
            "ask_confirm": [True, False],
            "ask_password": ["hunter2", "hunter2"],
        },
    )
    payload = _disk.prompts()
    assert payload == {
        "preset": "stig_server",
        "wipe": True,
        "luks": {"preset": "partial", "passphrase": "hunter2"},
    }


def test_disk_luks_partial_inline_retry_then_match(monkeypatch: pytest.MonkeyPatch):
    _scripted(
        monkeypatch,
        {
            "select_one": ["stig_server", "partial", "inline"],
            "ask_confirm": [True, False],
            # first pair mismatches, second pair matches
            "ask_password": ["hunter2", "wrong", "hunter2", "hunter2"],
        },
    )
    payload = _disk.prompts()
    assert payload["luks"]["passphrase"] == "hunter2"


def test_disk_luks_partial_inline_three_mismatches_raises(monkeypatch: pytest.MonkeyPatch):
    _scripted(
        monkeypatch,
        {
            "select_one": ["stig_server", "partial", "inline"],
            "ask_confirm": [True],
            "ask_password": ["a", "b"] * 3,
        },
    )
    with pytest.raises(WizardError, match="confirmation mismatch"):
        _disk.prompts()


def test_disk_luks_partial_inline_empty_passphrase_raises(monkeypatch: pytest.MonkeyPatch):
    _scripted(
        monkeypatch,
        {
            "select_one": ["stig_server", "partial", "inline"],
            "ask_confirm": [True],
            "ask_password": ["   ", "   "],
        },
    )
    with pytest.raises(WizardError, match="empty"):
        _disk.prompts()


def test_disk_luks_partial_file(monkeypatch: pytest.MonkeyPatch):
    _scripted(
        monkeypatch,
        {
            "select_one": ["stig_server", "partial", "file"],
            "ask_confirm": [True, False],
            "ask_text": ["/etc/ks-gen/luks.key"],
        },
    )
    payload = _disk.prompts()
    assert payload == {
        "preset": "stig_server",
        "wipe": True,
        "luks": {"preset": "partial", "passphrase_file": "/etc/ks-gen/luks.key"},
    }


def test_disk_luks_partial_file_empty_path_raises(monkeypatch: pytest.MonkeyPatch):
    _scripted(
        monkeypatch,
        {
            "select_one": ["stig_server", "partial", "file"],
            "ask_confirm": [True],
            "ask_text": [""],
        },
    )
    with pytest.raises(WizardError, match="path is empty"):
        _disk.prompts()


# --- _network group tests --------------------------------------------------


def test_network_single_dhcp_default_device(monkeypatch: pytest.MonkeyPatch):
    _scripted(
        monkeypatch,
        {
            "ask_text": ["link"],  # device
            "select_one": ["dhcp"],
            "ask_confirm": [True, False],  # onboot=True, add another=False
        },
    )
    payload = _network.prompts()
    assert payload == {"interfaces": [{"device": "link", "bootproto": "dhcp", "onboot": True}]}


def test_network_single_dhcp_explicit_device(monkeypatch: pytest.MonkeyPatch):
    _scripted(
        monkeypatch,
        {
            "ask_text": ["eth0"],
            "select_one": ["dhcp"],
            "ask_confirm": [True, False],
        },
    )
    payload = _network.prompts()
    assert payload["interfaces"][0]["device"] == "eth0"


def test_network_static_with_nameservers(monkeypatch: pytest.MonkeyPatch):
    _scripted(
        monkeypatch,
        {
            "ask_text": [
                "ens3",  # device
                "10.0.0.10",  # ip
                "255.255.255.0",  # netmask
                "10.0.0.1",  # gateway
                "1.1.1.1",  # nameserver #1
                "8.8.8.8",  # nameserver #2
                "",  # blank to stop
            ],
            "select_one": ["static"],
            "ask_confirm": [True, False],
        },
    )
    payload = _network.prompts()
    assert payload == {
        "interfaces": [
            {
                "device": "ens3",
                "bootproto": "static",
                "onboot": True,
                "ip": "10.0.0.10",
                "netmask": "255.255.255.0",
                "gateway": "10.0.0.1",
                "nameservers": ["1.1.1.1", "8.8.8.8"],
            }
        ]
    }


def test_network_dotted_quad_validator_positive():
    assert _network._is_dotted_quad("10.0.0.1") is True
    assert _network._is_dotted_quad("255.255.255.255") is True


def test_network_dotted_quad_validator_negative():
    assert _network._is_dotted_quad("not-an-ip") is False
    assert _network._is_dotted_quad("10.0.0") is False
    assert _network._is_dotted_quad("10.0.0.0.0") is False
    assert _network._is_dotted_quad("") is False


def test_network_multi_interface(monkeypatch: pytest.MonkeyPatch):
    _scripted(
        monkeypatch,
        {
            "ask_text": [
                "eth0",
                "eth1",  # devices for iface #1 and #2
            ],
            "select_one": ["dhcp", "dhcp"],
            "ask_confirm": [
                True,
                True,  # onboot for #1, add-another=True
                True,
                False,  # onboot for #2, add-another=False
            ],
        },
    )
    payload = _network.prompts()
    assert len(payload["interfaces"]) == 2
    assert payload["interfaces"][0]["device"] == "eth0"
    assert payload["interfaces"][1]["device"] == "eth1"


# --- _overrides group tests ------------------------------------------------


def test_override_toggles_keys_are_overrides_fields():
    """If a cfg block is renamed or removed, this fails loudly."""
    from ks_gen.config import Overrides

    for key in _overrides._OVERRIDE_TOGGLES:
        assert key in Overrides.model_fields, (
            f"_OVERRIDE_TOGGLES has key {key!r} that no longer exists "
            f"on Overrides; mapping is out of sync with the schema."
        )


def test_override_toggles_attr_names_exist_on_cfg():
    """Each (toggle-attr) must be a real field on the corresponding Cfg block."""
    from ks_gen.config import Overrides

    for cfg_name, (attr, _default, _label) in _overrides._OVERRIDE_TOGGLES.items():
        cfg_field = Overrides.model_fields[cfg_name]
        cfg_cls = cfg_field.annotation
        assert attr in cfg_cls.model_fields, (  # type: ignore[union-attr]
            f"_OVERRIDE_TOGGLES[{cfg_name!r}] uses attr {attr!r} that doesn't "
            f"exist on {cfg_cls.__name__}"
        )


def test_overrides_empty_selection_returns_empty(monkeypatch: pytest.MonkeyPatch):
    _scripted(
        monkeypatch,
        {
            "ask_checkbox": [[], []],  # nothing disabled, nothing enabled
        },
    )
    assert _overrides.prompts() == {}


def test_overrides_disable_one_default_on(monkeypatch: pytest.MonkeyPatch):
    _scripted(
        monkeypatch,
        {
            "ask_checkbox": [["faillock"], []],
        },
    )
    assert _overrides.prompts() == {"faillock": {"enable": False}}


def test_overrides_enable_one_default_off(monkeypatch: pytest.MonkeyPatch):
    _scripted(
        monkeypatch,
        {
            "ask_checkbox": [[], ["dod_root_ca"]],
        },
    )
    # dod_root_ca uses "install" attr, default False -> set install=True
    assert _overrides.prompts() == {"dod_root_ca": {"install": True}}


def test_overrides_mixed(monkeypatch: pytest.MonkeyPatch):
    _scripted(
        monkeypatch,
        {
            "ask_checkbox": [["package_purge"], ["usbguard"]],
        },
    )
    assert _overrides.prompts() == {
        "package_purge": {"enable": False},
        "usbguard": {"enable": True},
    }


# --- end-to-end orchestration tests ----------------------------------------


def test_run_wizard_disk_group_selected(monkeypatch: pytest.MonkeyPatch):
    _stdin(
        "host01\n\n\n\n\nssh-ed25519 AAA test@example\n\n\n\n",
        monkeypatch,
    )
    monkeypatch.setattr(_prompts, "ask_checkbox", lambda *_a, **_kw: ["disk"])
    # Inject scripted disk-group answers
    _scripted(
        monkeypatch,
        {
            "select_one": ["stig_server", "none"],
            "ask_confirm": [True, False],  # wipe=True, add data disk? no
        },
    )
    cfg, _yaml_text = run_wizard(interactive=True)
    assert cfg.disk.preset is not None and cfg.disk.preset.value == "stig_server"
    assert cfg.disk.luks.preset.value == "none"
    assert cfg.disk.wipe is True


def test_run_wizard_all_groups_lints_clean(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _stdin(
        "host01\n\n\n\n\nssh-ed25519 AAA test@example\n\n\n\n",
        monkeypatch,
    )
    # script: group selector + every group's prompts, in call order.
    # The first ask_checkbox call is the group selector; the next two are
    # the override matrix's disable/enable lists.
    _scripted(
        monkeypatch,
        {
            "select_one": [
                "stig_server",
                "none",  # disk preset + LUKS
                "dhcp",  # bootproto
            ],
            "ask_confirm": [
                True,  # wipe system disk
                False,  # add data disk? no
                True,
                False,  # onboot, add-another (network)
            ],
            "ask_text": ["link"],  # device
            "ask_checkbox": [
                ["disk", "network", "overrides"],  # group selector
                [],  # disable nothing
                [],  # enable nothing
            ],
        },
    )

    cfg, yaml_text = run_wizard(interactive=True)
    write_initial(tmp_path, cfg, yaml_text)

    # Render the bundle and lint
    bundle = build_bundle(cfg)
    host_dir = tmp_path / "host01"
    write_bundle(bundle, host_dir)
    report = lint_kickstart(host_dir / "ks.cfg")
    assert report.ok, f"lint failed: {report}"


def test_run_wizard_keyboard_interrupt_becomes_wizard_error(
    monkeypatch: pytest.MonkeyPatch,
):
    _stdin(
        "host01\n\n\n\n\nssh-ed25519 AAA test@example\n\n\n\n",
        monkeypatch,
    )

    def _raise_kbd(*_a: object, **_kw: object) -> Any:
        raise KeyboardInterrupt

    monkeypatch.setattr(_prompts, "ask_checkbox", _raise_kbd)

    with pytest.raises(WizardError, match="aborted"):
        run_wizard(interactive=True)


# --- _disk data_disks loop tests -------------------------------------------


def test_disk_data_disks_skipped_when_user_declines(monkeypatch: pytest.MonkeyPatch):
    _scripted(
        monkeypatch,
        {
            "select_one": ["stig_server", "none"],
            "ask_confirm": [True, False],  # wipe=true, add data disk? no
        },
    )
    payload = _disk.prompts()
    assert "data_disks" not in payload


def test_disk_data_disks_one_wipe_true(monkeypatch: pytest.MonkeyPatch):
    _scripted(
        monkeypatch,
        {
            "select_one": ["stig_server", "none", "xfs"],
            # confirm flow: wipe?, add data disk?, wipe this disk?, add another?
            "ask_confirm": [True, True, True, False],
            "ask_text": [
                "disk/by-id/ata-WDC_X",
                "/data",
                "nodev,nosuid",
            ],
        },
    )
    payload = _disk.prompts()
    assert payload["data_disks"] == [
        {
            "target": "disk/by-id/ata-WDC_X",
            "mount": "/data",
            "fstype": "xfs",
            "fsoptions": "nodev,nosuid",
            "wipe": True,
        }
    ]


def test_disk_data_disks_one_preserve_partition_number(monkeypatch: pytest.MonkeyPatch):
    _scripted(
        monkeypatch,
        {
            "select_one": ["stig_server", "none", "xfs", "partition"],
            # wipe sys, add data, wipe data? no, add another? no
            "ask_confirm": [True, True, False, False],
            "ask_text": [
                "sdb",
                "/data",
                "nodev,nosuid",
                "1",
            ],
        },
    )
    payload = _disk.prompts()
    assert payload["data_disks"] == [
        {
            "target": "sdb",
            "mount": "/data",
            "fstype": "xfs",
            "fsoptions": "nodev,nosuid",
            "wipe": False,
            "partition": 1,
        }
    ]


def test_disk_data_disks_one_preserve_uuid(monkeypatch: pytest.MonkeyPatch):
    _scripted(
        monkeypatch,
        {
            "select_one": ["stig_server", "none", "xfs", "uuid"],
            "ask_confirm": [True, True, False, False],
            "ask_text": [
                "sdb",
                "/data",
                "nodev,nosuid",
                "0f2a-1c3b-4d5e-6f7a",
            ],
        },
    )
    payload = _disk.prompts()
    assert payload["data_disks"][0]["partition_uuid"] == "0f2a-1c3b-4d5e-6f7a"
    assert "partition" not in payload["data_disks"][0]


def test_disk_data_disks_one_preserve_label(monkeypatch: pytest.MonkeyPatch):
    _scripted(
        monkeypatch,
        {
            "select_one": ["stig_server", "none", "xfs", "label"],
            "ask_confirm": [True, True, False, False],
            "ask_text": [
                "sdb",
                "/data",
                "nodev,nosuid",
                "preserve_test",
            ],
        },
    )
    payload = _disk.prompts()
    assert payload["data_disks"][0]["partition_label"] == "preserve_test"


def test_disk_data_disks_two_disks_mixed(monkeypatch: pytest.MonkeyPatch):
    _scripted(
        monkeypatch,
        {
            "select_one": ["stig_server", "none", "xfs", "xfs", "label"],
            "ask_confirm": [
                True,  # wipe system disk
                True,  # add a data disk
                True,  # disk 1: wipe=true
                True,  # add another
                False,  # disk 2: wipe=false
                False,  # add another? no
            ],
            "ask_text": [
                "sdb",
                "/scratch",
                "nodev,nosuid",  # disk 1
                "sdc",
                "/data",
                "nodev,nosuid",
                "keep",  # disk 2 (label keep)
            ],
        },
    )
    payload = _disk.prompts()
    assert len(payload["data_disks"]) == 2
    assert payload["data_disks"][0]["mount"] == "/scratch"
    assert payload["data_disks"][0]["wipe"] is True
    assert payload["data_disks"][1]["mount"] == "/data"
    assert payload["data_disks"][1]["wipe"] is False
    assert payload["data_disks"][1]["partition_label"] == "keep"
