from __future__ import annotations

import io
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ks_gen.wizard import WizardError, _disk, _prompts, run_wizard, write_initial
from ks_gen.wizard import _core as _wizard_core


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
            "ask_confirm": [True],  # wipe = true
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
            "ask_confirm": [False],
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
