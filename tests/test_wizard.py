from __future__ import annotations

import io
from pathlib import Path

import pytest

from ks_gen.wizard import WizardError, run_wizard, write_initial


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
    cfg, yaml_text = run_wizard(interactive=True)
    host_dir = write_initial(tmp_path, cfg, yaml_text)
    assert host_dir == tmp_path / "host01"
    assert (host_dir / "host.yaml").read_text(encoding="utf-8") == yaml_text
