# Wizard disk/network/overrides Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `ks-gen new` with three opt-in prompt groups — disk, network, override matrix — driven by a `questionary`-based interactive checkbox selector. Closes #9; ships the wizard described in spec `docs/superpowers/specs/2026-06-08-wizard-disk-network-overrides-design.md`.

**Architecture:** Promote `src/ks_gen/wizard.py` to a package; add a single-file `questionary` adapter (`_prompts.py`) that bounds all type-untyped library calls; keep one entry point per group (`_disk.prompts()`, `_network.prompts()`, `_overrides.prompts()`); `run_wizard()` orchestrates `_core` + group selector + each opted-in group; non-interactive mode bypasses questionary and all optional groups.

**Tech Stack:** Python 3.11+, pydantic 2.x, typer (existing), questionary (new dep), pytest + monkeypatch for mocking questionary in tests. CI parity: `ruff check && ruff format --check && mypy && pytest -q`.

**Branch:** `impl/v0.7.0-wizard-disk-network-overrides` (matches the `impl/v0.X.Y-<topic>` convention for v0.2.0/v0.2.1/v0.3.0 feature branches).

---

## Pre-flight

- [ ] Create a feature branch off `main`:

```bash
git checkout main && git pull --ff-only
git checkout -b impl/v0.7.0-wizard-disk-network-overrides
```

- [ ] Confirm working tree is clean: `git status --short` shows nothing.

---

### Task 1: Add `questionary` dependency

**Files:**
- Modify: `pyproject.toml:12-18` (the `dependencies` list)

- [ ] **Step 1: Edit `pyproject.toml`**

Add `questionary>=2.0` to the `dependencies` list. The list becomes:

```toml
dependencies = [
  "typer>=0.12",
  "pydantic>=2.6",
  "jinja2>=3.1",
  "pyyaml>=6.0",
  "pykickstart>=3.52",
  "questionary>=2.0",
]
```

- [ ] **Step 2: Install the dep in the current venv**

Run:
```bash
pip install -e .
```

Expected: questionary + prompt_toolkit + wcwidth resolve and install with no conflicts.

- [ ] **Step 3: Smoke-check the dep imports**

Run:
```bash
python -c "import questionary; print(questionary.__version__)"
```

Expected: prints a version string ≥ 2.0.

- [ ] **Step 4: Run the local CI parity chain**

Run:
```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green. (No code change yet; this confirms the dep didn't break the existing tree.)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "build(deps): add questionary for ks-gen new wizard prompts"
```

---

### Task 2: Add `tests/test_wizard.py` covering existing wizard behavior

This closes the v0.1 test gap before we touch the wizard module. Tests must pass against the current `wizard.py` before we refactor.

**Files:**
- Create: `tests/test_wizard.py`

- [ ] **Step 1: Write `tests/test_wizard.py`**

Full file content:

```python
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
        "host01\n"           # hostname
        "\n"                 # timezone -> default UTC
        "\n"                 # locale   -> default en_US.UTF-8
        "\n"                 # admin    -> default opsadmin
        "\n"                 # sudo     -> default nopasswd_yes
        "ssh-ed25519 AAA test@example\n"
        "\n"                 # blank line to stop key entry
        "\n"                 # ssh port -> default 22
        "\n",                # crypto   -> default MODERN
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
        "host01\n\n\n\n\n"   # hostname through sudo
        "\n",                # blank SSH key with none entered
        monkeypatch,
    )
    with pytest.raises(WizardError, match="at least one SSH key"):
        run_wizard(interactive=True)


def test_write_initial_creates_host_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _stdin(
        "host01\n\n\n\n\n"
        "ssh-ed25519 AAA test@example\n\n"
        "\n\n",
        monkeypatch,
    )
    cfg, yaml_text = run_wizard(interactive=True)
    host_dir = write_initial(tmp_path, cfg, yaml_text)
    assert host_dir == tmp_path / "host01"
    assert (host_dir / "host.yaml").read_text(encoding="utf-8") == yaml_text
```

- [ ] **Step 2: Run the tests**

Run:
```bash
pytest tests/test_wizard.py -v
```

Expected: all 5 pass against the current `src/ks_gen/wizard.py`.

- [ ] **Step 3: Run the local CI parity chain**

Run:
```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_wizard.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "test(wizard): cover existing run_wizard / write_initial paths"
```

---

### Task 3: Promote `wizard.py` to a `wizard/` package

Pure refactor — no behavior change. Tests from Task 2 are the safety net.

**Files:**
- Create: `src/ks_gen/wizard/__init__.py`
- Create: `src/ks_gen/wizard/_core.py`
- Delete: `src/ks_gen/wizard.py`

- [ ] **Step 1: Create `src/ks_gen/wizard/_core.py`**

Copy the current `src/ks_gen/wizard.py` contents verbatim into `src/ks_gen/wizard/_core.py`. No changes to function bodies.

- [ ] **Step 2: Create `src/ks_gen/wizard/__init__.py`**

```python
from __future__ import annotations

from ks_gen.wizard._core import (
    WizardError as WizardError,
    run_wizard as run_wizard,
    write_initial as write_initial,
)

__all__ = ["WizardError", "run_wizard", "write_initial"]
```

The explicit `X as X` aliases satisfy mypy --strict's `no-implicit-reexport`.

- [ ] **Step 3: Delete the old module**

```bash
git rm src/ks_gen/wizard.py
```

- [ ] **Step 4: Run the tests**

Run:
```bash
pytest tests/test_wizard.py -v
```

Expected: all 5 still pass (imports go through the package shim now).

- [ ] **Step 5: Run the local CI parity chain**

Run:
```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/wizard/
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "refactor(wizard): promote wizard.py to package (no behavior change)"
```

---

### Task 4: Build the `_prompts.py` questionary adapter

Single point of contact with questionary. Outward-facing functions are typed strictly; the questionary import carries `# type: ignore[import-untyped]`.

**Files:**
- Create: `src/ks_gen/wizard/_prompts.py`
- Modify: `tests/test_wizard.py` (add adapter tests at end)

- [ ] **Step 1: Write failing tests for `_prompts.py`**

Append to `tests/test_wizard.py`:

```python
# --- _prompts adapter tests -------------------------------------------------

from collections.abc import Callable
from typing import Any

from ks_gen.wizard import _prompts


def _stub_questionary(monkeypatch: pytest.MonkeyPatch, name: str, return_value: Any) -> None:
    """Replace `_prompts._questionary.<name>` with a stub returning .ask() = value."""

    class _Q:
        def ask(self) -> Any:  # noqa: ANN401
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
```

- [ ] **Step 2: Run the tests — expect failure**

Run:
```bash
pytest tests/test_wizard.py -v -k "_prompts or select_one or ask_text or ask_confirm or ask_password or ask_checkbox"
```

Expected: ImportError / AttributeError on `from ks_gen.wizard import _prompts`.

- [ ] **Step 3: Write `src/ks_gen/wizard/_prompts.py`**

```python
"""Typed adapter over `questionary`.

This is the only file in the wizard package that imports questionary;
keeping the dependency surface here bounds the `type: ignore` to one
line. Outward-facing functions are typed strictly and used by the
group helpers.
"""
from __future__ import annotations

from collections.abc import Iterable

import questionary as _questionary  # type: ignore[import-untyped]


def select_one(message: str, choices: Iterable[str]) -> str:
    """Single-select menu; returns the chosen string."""
    answer = _questionary.select(message, choices=list(choices)).ask()
    if answer is None:
        raise KeyboardInterrupt
    return str(answer)


def ask_text(
    message: str,
    *,
    default: str = "",
    validate: object | None = None,
) -> str:
    """Free-form text input; returns stripped value.

    `validate` accepts questionary's validator protocol — a callable
    returning True for valid input or a str error message.
    """
    answer = _questionary.text(message, default=default, validate=validate).ask()
    if answer is None:
        raise KeyboardInterrupt
    return str(answer).strip()


def ask_confirm(message: str, *, default: bool) -> bool:
    """Yes/no confirm; returns bool."""
    answer = _questionary.confirm(message, default=default).ask()
    if answer is None:
        raise KeyboardInterrupt
    return bool(answer)


def ask_password(message: str) -> str:
    """Hidden-input prompt for secrets; returns string (not stripped)."""
    answer = _questionary.password(message).ask()
    if answer is None:
        raise KeyboardInterrupt
    return str(answer)


def ask_checkbox(
    message: str,
    choices: Iterable[tuple[str, str]],
) -> list[str]:
    """Multi-select; `choices` is iterable of (key, label) pairs.

    Returns the list of selected keys (empty list is valid).
    """
    pairs = list(choices)
    q_choices = [
        _questionary.Choice(title=f"{key:<25}{label}", value=key) for key, label in pairs
    ]
    answer = _questionary.checkbox(message, choices=q_choices).ask()
    if answer is None:
        raise KeyboardInterrupt
    return [str(x) for x in answer]


def loop_until_blank(message: str) -> list[str]:
    """Repeated text prompt; stops on blank input. Returns collected values."""
    collected: list[str] = []
    while True:
        value = ask_text(message, default="")
        if not value:
            return collected
        collected.append(value)
```

- [ ] **Step 4: Run the adapter tests**

Run:
```bash
pytest tests/test_wizard.py -v
```

Expected: all tests pass (Task 2 tests still green + new adapter tests pass).

- [ ] **Step 5: Run the local CI parity chain**

Run:
```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/wizard/_prompts.py tests/test_wizard.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(wizard): typed questionary adapter in wizard/_prompts.py"
```

---

### Task 5: Refactor `run_wizard` to call `_core.prompts()` + add group selector

This pulls the 4-prompt body out of `_core.run_wizard` into `_core.prompts()`, leaves the public `run_wizard` in `__init__.py` as the orchestrator with an empty group-selector loop. Behavior unchanged: optional groups are not yet wired (next phase).

**Files:**
- Modify: `src/ks_gen/wizard/_core.py`
- Modify: `src/ks_gen/wizard/__init__.py`
- Modify: `tests/test_wizard.py` (add tests for group selector and the orchestrator)

- [ ] **Step 1: Write the failing group-selector test**

Append to `tests/test_wizard.py`:

```python
# --- group-selector + orchestration tests -----------------------------------

from ks_gen.wizard import _core as _wizard_core


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
        "host01\n\n\n\n\n"
        "ssh-ed25519 AAA test@example\n\n"
        "\n\n",
        monkeypatch,
    )
    # Group selector returns empty list (no optional groups).
    monkeypatch.setattr(_prompts, "ask_checkbox", lambda *_a, **_kw: [])

    cfg, yaml_text = run_wizard(interactive=True)
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
```

- [ ] **Step 2: Run the failing tests**

Run:
```bash
pytest tests/test_wizard.py::test_core_prompts_non_interactive_requires_hostname tests/test_wizard.py::test_run_wizard_empty_group_selector_matches_legacy -v
```

Expected: failure — `_core.prompts` does not exist yet.

- [ ] **Step 3: Refactor `src/ks_gen/wizard/_core.py`**

Replace the file content with:

```python
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ks_gen.config import HostConfig


@dataclass
class WizardError(Exception):
    message: str


def _ask(prompt: str, default: str | None, *, interactive: bool) -> str:
    if not interactive:
        if default is None:
            raise WizardError(f"missing required value: {prompt}")
        return default
    suffix = f" [{default}]" if default is not None else ""
    sys.stdout.write(f"{prompt}{suffix}: ")
    sys.stdout.flush()
    line = sys.stdin.readline()
    if line == "":
        raise WizardError("unexpected EOF on stdin")
    answer = line.rstrip("\n")
    if not answer and default is not None:
        return default
    if not answer and default is None:
        raise WizardError(f"missing required value: {prompt}")
    return answer


def _ask_keys(interactive: bool) -> list[str]:
    keys: list[str] = []
    while True:
        line = _ask(
            "SSH public key (blank to stop)" if keys else "SSH public key",
            "" if keys else None,
            interactive=interactive,
        )
        if not line:
            if not keys:
                raise WizardError("at least one SSH key is required")
            return keys
        keys.append(line)


def prompts(interactive: bool) -> dict[str, Any]:
    """Run the always-required prompts. Returns a HostConfig payload fragment."""
    hostname = _ask("Hostname", None, interactive=interactive)
    timezone = _ask("Timezone", "UTC", interactive=interactive)
    locale = _ask("Locale", "en_US.UTF-8", interactive=interactive)
    admin_name = _ask("Admin username", "opsadmin", interactive=interactive)
    sudo = _ask(
        "Admin sudo mode (nopasswd_no/nopasswd_yes)", "nopasswd_yes", interactive=interactive
    )
    keys = _ask_keys(interactive)
    ssh_port_raw = _ask("SSH port", "22", interactive=interactive)
    crypto_policy = _ask("Crypto policy (STIG/MODERN/FUTURE)", "MODERN", interactive=interactive)

    return {
        "system": {"hostname": hostname, "timezone": timezone, "locale": locale},
        "user": {
            "admin": {
                "name": admin_name,
                "authorized_keys": keys,
                "sudo": sudo,
            }
        },
        "ssh": {"port": int(ssh_port_raw)},
        "crypto": {"policy": crypto_policy},
    }


def write_initial(out_root: Path, cfg: HostConfig, yaml_text: str) -> Path:
    host_dir = out_root / cfg.system.hostname
    host_dir.mkdir(parents=True, exist_ok=True)
    (host_dir / "host.yaml").write_text(yaml_text, encoding="utf-8", newline="\n")
    return host_dir
```

- [ ] **Step 4: Rewrite `src/ks_gen/wizard/__init__.py` as the orchestrator**

```python
from __future__ import annotations

import yaml

from ks_gen.config import HostConfig
from ks_gen.wizard import _core, _prompts
from ks_gen.wizard._core import WizardError as WizardError
from ks_gen.wizard._core import write_initial as write_initial

__all__ = ["WizardError", "run_wizard", "write_initial"]

_GROUP_CHOICES: list[tuple[str, str]] = [
    ("disk", "Disk layout (preset, LUKS)"),
    ("network", "Network (interfaces)"),
    ("overrides", "Override matrix (per-rule toggles)"),
]


def _ask_groups() -> set[str]:
    """Interactive checkbox: which optional groups to configure."""
    return set(_prompts.ask_checkbox("Configure which optional sections?", _GROUP_CHOICES))


def run_wizard(*, interactive: bool) -> tuple[HostConfig, str]:
    payload = _core.prompts(interactive)
    selected: set[str] = _ask_groups() if interactive else set()
    # Optional groups wired in later tasks; for now the selector is a no-op.
    # if "disk" in selected: payload["disk"] = _disk.prompts()
    # if "network" in selected: payload["network"] = _network.prompts()
    # if "overrides" in selected: payload["overrides"] = _overrides.prompts()
    cfg = HostConfig.model_validate(payload)
    yaml_text = yaml.safe_dump(
        cfg.model_dump(mode="json"), sort_keys=False, default_flow_style=False
    )
    return cfg, yaml_text
```

- [ ] **Step 5: Run all tests**

Run:
```bash
pytest tests/test_wizard.py -v
```

Expected: all pass (including the new group-selector tests).

- [ ] **Step 6: Run the local CI parity chain**

Run:
```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/ks_gen/wizard/ tests/test_wizard.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "refactor(wizard): _core.prompts() + group selector orchestration"
```

---

### Task 6: `_disk.py` — preset + wipe + LUKS none

First disk group implementation. Covers both presets, wipe confirm, and the LUKS-none path. Minimal-preset LUKS skip is also covered.

**Files:**
- Create: `src/ks_gen/wizard/_disk.py`
- Modify: `tests/test_wizard.py` (append disk tests)

- [ ] **Step 1: Write failing tests for `_disk.py`**

Append to `tests/test_wizard.py`:

```python
# --- _disk group tests -----------------------------------------------------

from ks_gen.wizard import _disk


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
    _scripted(monkeypatch, {
        "select_one": ["stig_server", "none"],
        "ask_confirm": [True],          # wipe = true
    })
    payload = _disk.prompts()
    assert payload == {
        "preset": "stig_server",
        "wipe": True,
        "luks": {"preset": "none"},
    }


def test_disk_stig_server_no_wipe(monkeypatch: pytest.MonkeyPatch):
    _scripted(monkeypatch, {
        "select_one": ["stig_server", "none"],
        "ask_confirm": [False],
    })
    payload = _disk.prompts()
    assert payload["wipe"] is False


def test_disk_minimal_skips_luks_prompt(monkeypatch: pytest.MonkeyPatch):
    # Only one select_one call (preset). If LUKS were asked, the queue
    # would underflow and IndexError would be raised.
    _scripted(monkeypatch, {
        "select_one": ["minimal"],
        "ask_confirm": [True],
    })
    payload = _disk.prompts()
    assert payload == {"preset": "minimal", "wipe": True}
    assert "luks" not in payload
```

- [ ] **Step 2: Run the failing tests**

Run:
```bash
pytest tests/test_wizard.py -v -k disk
```

Expected: ImportError on `from ks_gen.wizard import _disk`.

- [ ] **Step 3: Write `src/ks_gen/wizard/_disk.py`**

```python
"""Disk group prompts.

Covers preset choice (stig_server / minimal), wipe confirm, and LUKS
preset (none / partial). Tang and custom disk.layout are deferred to
hand-edit per the design spec.
"""
from __future__ import annotations

from typing import Any

from ks_gen.wizard import _prompts


def prompts() -> dict[str, Any]:
    """Run the disk-group prompts. Returns a HostConfig.disk fragment."""
    preset = _prompts.select_one(
        "Disk preset:", ["stig_server", "minimal"]
    )
    wipe = _prompts.ask_confirm("Wipe disk on install?", default=True)

    payload: dict[str, Any] = {"preset": preset, "wipe": wipe}

    if preset == "minimal":
        # _minimal_preset_rejects_luks would reject any LUKS != none.
        # Skip the prompt entirely.
        print("minimal preset has no LVM PV; skipping LUKS prompt.")
        return payload

    luks_preset = _prompts.select_one(
        "LUKS encryption:", ["none", "partial"]
    )
    print(
        "(LUKS tang preset is hand-edit only — needs URLs, thumbprints, "
        "and threshold. See MANUAL.md §5.1.)"
    )
    if luks_preset == "none":
        payload["luks"] = {"preset": "none"}
        return payload

    # luks_preset == "partial" — handled by the partial helpers added in
    # Task 7 / Task 8. Placeholder raises until those land.
    raise NotImplementedError("LUKS partial path not yet implemented")
```

- [ ] **Step 4: Run all wizard tests**

Run:
```bash
pytest tests/test_wizard.py -v
```

Expected: all pass.

- [ ] **Step 5: Run the local CI parity chain**

Run:
```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/wizard/_disk.py tests/test_wizard.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(wizard): disk group prompts (preset, wipe, LUKS none)"
```

---

### Task 7: `_disk.py` — LUKS partial inline passphrase

Adds the inline-passphrase branch with confirm + mismatch retry (max 3).

**Files:**
- Modify: `src/ks_gen/wizard/_disk.py`
- Modify: `tests/test_wizard.py` (append partial-inline tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_wizard.py`:

```python
def test_disk_luks_partial_inline_match(monkeypatch: pytest.MonkeyPatch):
    _scripted(monkeypatch, {
        "select_one": ["stig_server", "partial", "inline"],
        "ask_confirm": [True],
        "ask_password": ["hunter2", "hunter2"],
    })
    payload = _disk.prompts()
    assert payload == {
        "preset": "stig_server",
        "wipe": True,
        "luks": {"preset": "partial", "passphrase": "hunter2"},
    }


def test_disk_luks_partial_inline_retry_then_match(monkeypatch: pytest.MonkeyPatch):
    _scripted(monkeypatch, {
        "select_one": ["stig_server", "partial", "inline"],
        "ask_confirm": [True],
        # first pair mismatches, second pair matches
        "ask_password": ["hunter2", "wrong", "hunter2", "hunter2"],
    })
    payload = _disk.prompts()
    assert payload["luks"]["passphrase"] == "hunter2"


def test_disk_luks_partial_inline_three_mismatches_raises(monkeypatch: pytest.MonkeyPatch):
    _scripted(monkeypatch, {
        "select_one": ["stig_server", "partial", "inline"],
        "ask_confirm": [True],
        "ask_password": ["a", "b"] * 3,
    })
    with pytest.raises(WizardError, match="confirmation mismatch"):
        _disk.prompts()


def test_disk_luks_partial_inline_empty_passphrase_raises(monkeypatch: pytest.MonkeyPatch):
    _scripted(monkeypatch, {
        "select_one": ["stig_server", "partial", "inline"],
        "ask_confirm": [True],
        "ask_password": ["   ", "   "],
    })
    with pytest.raises(WizardError, match="empty"):
        _disk.prompts()
```

- [ ] **Step 2: Run failing tests**

Run:
```bash
pytest tests/test_wizard.py -v -k "disk_luks_partial_inline"
```

Expected: failures — `NotImplementedError` from the placeholder branch.

- [ ] **Step 3: Update `_disk.py` to implement inline passphrase**

Replace the trailing `raise NotImplementedError(...)` block at the bottom of `_disk.py` with:

```python
    # luks_preset == "partial"
    print(
        "NOTE: inline passphrase will be stored in plaintext in host.yaml; "
        "for production use the 'file' option."
    )
    source = _prompts.select_one(
        "Passphrase source:", ["inline", "file"]
    )
    if source == "inline":
        payload["luks"] = {
            "preset": "partial",
            "passphrase": _ask_inline_passphrase(),
        }
        return payload

    # source == "file" — handled in Task 8
    raise NotImplementedError("LUKS partial file path not yet implemented")
```

And add this helper near the top of the file (below the imports):

```python
from ks_gen.wizard._core import WizardError

_INLINE_RETRY_LIMIT = 3


def _ask_inline_passphrase() -> str:
    """Inline passphrase + confirm loop. Up to 3 mismatch retries."""
    for _ in range(_INLINE_RETRY_LIMIT):
        first = _prompts.ask_password("Passphrase:")
        second = _prompts.ask_password("Confirm passphrase:")
        if first.strip() == "" and second.strip() == "":
            raise WizardError("passphrase is empty")
        if first == second:
            return first
        print("passphrase mismatch; please try again")
    raise WizardError(
        f"passphrase confirmation mismatch after {_INLINE_RETRY_LIMIT} attempts"
    )
```

- [ ] **Step 4: Run all wizard tests**

Run:
```bash
pytest tests/test_wizard.py -v
```

Expected: all pass.

- [ ] **Step 5: Run the local CI parity chain**

Run:
```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/wizard/_disk.py tests/test_wizard.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(wizard): disk group LUKS partial inline passphrase + retry"
```

---

### Task 8: `_disk.py` — LUKS partial sidecar file

Adds the sidecar-file branch. No FS check at wizard time; `resolve_passphrase` validates at bundle build.

**Files:**
- Modify: `src/ks_gen/wizard/_disk.py`
- Modify: `tests/test_wizard.py` (append partial-file tests)

- [ ] **Step 1: Write failing test**

Append to `tests/test_wizard.py`:

```python
def test_disk_luks_partial_file(monkeypatch: pytest.MonkeyPatch):
    _scripted(monkeypatch, {
        "select_one": ["stig_server", "partial", "file"],
        "ask_confirm": [True],
        "ask_text": ["/etc/ks-gen/luks.key"],
    })
    payload = _disk.prompts()
    assert payload == {
        "preset": "stig_server",
        "wipe": True,
        "luks": {"preset": "partial", "passphrase_file": "/etc/ks-gen/luks.key"},
    }


def test_disk_luks_partial_file_empty_path_raises(monkeypatch: pytest.MonkeyPatch):
    _scripted(monkeypatch, {
        "select_one": ["stig_server", "partial", "file"],
        "ask_confirm": [True],
        "ask_text": [""],
    })
    with pytest.raises(WizardError, match="path is empty"):
        _disk.prompts()
```

- [ ] **Step 2: Run the failing test**

Run:
```bash
pytest tests/test_wizard.py -v -k "disk_luks_partial_file"
```

Expected: failure — `NotImplementedError` from the placeholder branch.

- [ ] **Step 3: Replace the trailing `raise NotImplementedError(...)` block**

Replace:
```python
    # source == "file" — handled in Task 8
    raise NotImplementedError("LUKS partial file path not yet implemented")
```

With:
```python
    # source == "file"
    path = _prompts.ask_text("Passphrase file path:")
    if not path:
        raise WizardError("passphrase_file path is empty")
    payload["luks"] = {"preset": "partial", "passphrase_file": path}
    return payload
```

- [ ] **Step 4: Run all wizard tests**

Run:
```bash
pytest tests/test_wizard.py -v
```

Expected: all pass.

- [ ] **Step 5: Run the local CI parity chain**

Run:
```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/wizard/_disk.py tests/test_wizard.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(wizard): disk group LUKS partial sidecar file"
```

---

### Task 9: `_network.py` — single DHCP interface

First network group implementation. Default-device + DHCP + onboot path only.

**Files:**
- Create: `src/ks_gen/wizard/_network.py`
- Modify: `tests/test_wizard.py` (append network tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_wizard.py`:

```python
# --- _network group tests --------------------------------------------------

from ks_gen.wizard import _network


def test_network_single_dhcp_default_device(monkeypatch: pytest.MonkeyPatch):
    _scripted(monkeypatch, {
        "ask_text": ["link"],                       # device
        "select_one": ["dhcp"],
        "ask_confirm": [True, False],               # onboot=True, add another=False
    })
    payload = _network.prompts()
    assert payload == {
        "interfaces": [
            {"device": "link", "bootproto": "dhcp", "onboot": True}
        ]
    }


def test_network_single_dhcp_explicit_device(monkeypatch: pytest.MonkeyPatch):
    _scripted(monkeypatch, {
        "ask_text": ["eth0"],
        "select_one": ["dhcp"],
        "ask_confirm": [True, False],
    })
    payload = _network.prompts()
    assert payload["interfaces"][0]["device"] == "eth0"
```

- [ ] **Step 2: Run the failing tests**

Run:
```bash
pytest tests/test_wizard.py -v -k "network_single_dhcp"
```

Expected: ImportError on `from ks_gen.wizard import _network`.

- [ ] **Step 3: Write `src/ks_gen/wizard/_network.py`**

```python
"""Network group prompts.

Single-interface loop with optional "add another" continuation.
Bond/bridge/VLAN deferred to hand-edit per the design spec.
"""
from __future__ import annotations

from typing import Any

from ks_gen.wizard import _prompts


def _ask_one_interface() -> dict[str, Any]:
    device = _prompts.ask_text("Interface device:", default="link")
    bootproto = _prompts.select_one("Bootproto:", ["dhcp", "static"])
    onboot = _prompts.ask_confirm("Bring up on boot?", default=True)

    iface: dict[str, Any] = {
        "device": device,
        "bootproto": bootproto,
        "onboot": onboot,
    }
    # static fields added in Task 10
    return iface


def prompts() -> dict[str, Any]:
    interfaces: list[dict[str, Any]] = []
    while True:
        interfaces.append(_ask_one_interface())
        if not _prompts.ask_confirm("Configure another interface?", default=False):
            break
    return {"interfaces": interfaces}
```

- [ ] **Step 4: Run all wizard tests**

Run:
```bash
pytest tests/test_wizard.py -v
```

Expected: all pass.

- [ ] **Step 5: Run the local CI parity chain**

Run:
```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/wizard/_network.py tests/test_wizard.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(wizard): network group single DHCP interface"
```

---

### Task 10: `_network.py` — static interface + dotted-quad validator

Adds the static branch with regex validation and the nameserver loop.

**Files:**
- Modify: `src/ks_gen/wizard/_network.py`
- Modify: `tests/test_wizard.py` (append static tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_wizard.py`:

```python
def test_network_static_with_nameservers(monkeypatch: pytest.MonkeyPatch):
    _scripted(monkeypatch, {
        "ask_text": [
            "ens3",          # device
            "10.0.0.10",     # ip
            "255.255.255.0", # netmask
            "10.0.0.1",      # gateway
            "1.1.1.1",       # nameserver #1
            "8.8.8.8",       # nameserver #2
            "",              # blank to stop
        ],
        "select_one": ["static"],
        "ask_confirm": [True, False],
    })
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
```

- [ ] **Step 2: Run the failing tests**

Run:
```bash
pytest tests/test_wizard.py -v -k "network_static or dotted_quad"
```

Expected: AttributeError on `_network._is_dotted_quad` / static branch doesn't add fields yet.

- [ ] **Step 3: Update `src/ks_gen/wizard/_network.py`**

Replace the file content with:

```python
"""Network group prompts.

Single-interface loop with optional "add another" continuation.
Bond/bridge/VLAN deferred to hand-edit per the design spec.
"""
from __future__ import annotations

import re
from typing import Any

from ks_gen.wizard import _prompts

_DOTTED_QUAD_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")


def _is_dotted_quad(s: str) -> bool:
    return bool(_DOTTED_QUAD_RE.match(s))


def _quad_validator(value: str) -> bool | str:
    """questionary validator: True if valid, else error string."""
    if _is_dotted_quad(value):
        return True
    return "expected dotted-quad (e.g., 10.0.0.1)"


def _ask_one_interface() -> dict[str, Any]:
    device = _prompts.ask_text("Interface device:", default="link")
    bootproto = _prompts.select_one("Bootproto:", ["dhcp", "static"])
    onboot = _prompts.ask_confirm("Bring up on boot?", default=True)

    iface: dict[str, Any] = {
        "device": device,
        "bootproto": bootproto,
        "onboot": onboot,
    }

    if bootproto == "static":
        iface["ip"] = _prompts.ask_text(
            "IPv4 address (e.g., 10.0.0.10):", validate=_quad_validator
        )
        iface["netmask"] = _prompts.ask_text(
            "Netmask (e.g., 255.255.255.0):", validate=_quad_validator
        )
        iface["gateway"] = _prompts.ask_text(
            "Gateway (e.g., 10.0.0.1):", validate=_quad_validator
        )
        iface["nameservers"] = _prompts.loop_until_blank("Nameserver (blank to stop):")

    return iface


def prompts() -> dict[str, Any]:
    interfaces: list[dict[str, Any]] = []
    while True:
        interfaces.append(_ask_one_interface())
        if not _prompts.ask_confirm("Configure another interface?", default=False):
            break
    return {"interfaces": interfaces}
```

- [ ] **Step 4: Run all wizard tests**

Run:
```bash
pytest tests/test_wizard.py -v
```

Expected: all pass.

- [ ] **Step 5: Run the local CI parity chain**

Run:
```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/wizard/_network.py tests/test_wizard.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(wizard): network group static interface + dotted-quad validator"
```

---

### Task 11: `_network.py` — add-another loop

Adds explicit test for the multi-interface loop (the loop already exists in `prompts()`; this task pins it with an end-to-end test).

**Files:**
- Modify: `tests/test_wizard.py` (append multi-interface test)

- [ ] **Step 1: Write failing test**

Append to `tests/test_wizard.py`:

```python
def test_network_multi_interface(monkeypatch: pytest.MonkeyPatch):
    _scripted(monkeypatch, {
        "ask_text": [
            "eth0", "eth1",   # devices for iface #1 and #2
        ],
        "select_one": ["dhcp", "dhcp"],
        "ask_confirm": [
            True, True,       # onboot for #1, add-another=True
            True, False,      # onboot for #2, add-another=False
        ],
    })
    payload = _network.prompts()
    assert len(payload["interfaces"]) == 2
    assert payload["interfaces"][0]["device"] == "eth0"
    assert payload["interfaces"][1]["device"] == "eth1"
```

- [ ] **Step 2: Run the test**

Run:
```bash
pytest tests/test_wizard.py::test_network_multi_interface -v
```

Expected: PASS (the loop already exists; this test pins the behavior).

- [ ] **Step 3: Run the local CI parity chain**

Run:
```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_wizard.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "test(wizard): pin network add-another multi-interface loop"
```

---

### Task 12: `_overrides.py` — `_OVERRIDE_TOGGLES` mapping + consistency test

Schema-asymmetry mapping plus the consistency test that fails if `Overrides` is changed.

**Files:**
- Create: `src/ks_gen/wizard/_overrides.py`
- Modify: `tests/test_wizard.py` (append mapping test)

- [ ] **Step 1: Write failing test**

Append to `tests/test_wizard.py`:

```python
# --- _overrides group tests ------------------------------------------------

from ks_gen.wizard import _overrides


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
```

- [ ] **Step 2: Run the failing test**

Run:
```bash
pytest tests/test_wizard.py -v -k override_toggles
```

Expected: ImportError on `from ks_gen.wizard import _overrides`.

- [ ] **Step 3: Write `src/ks_gen/wizard/_overrides.py`**

```python
"""Override matrix prompts.

Two checkbox prompts driven by a small static mapping. The mapping is
the cost of the schema asymmetry: not every Cfg block on Overrides has
a uniform `.enable: bool` field.
"""
from __future__ import annotations

from typing import Any

from ks_gen.wizard import _prompts

# cfg-field-name -> (toggle-attr, default-value, one-line operator label)
_OVERRIDE_TOGGLES: dict[str, tuple[str, bool, str]] = {
    "faillock":                ("enable",  True,  "account lockout policy"),
    "kernel_module_blacklist": ("enable",  True,  "blacklist USB-storage, cramfs, etc."),
    "package_purge":           ("enable",  True,  "remove telnet-server, rsh-server, etc."),
    "unattended_updates":      ("enable",  True,  "nightly + monthly + reboot timers"),
    "usbguard":                ("enable",  False, "USB device control daemon"),
    "dod_root_ca":             ("install", False, "install DoD root CA bundle"),
}


def prompts() -> dict[str, Any]:
    """Run the override-matrix prompts. Returns a HostConfig.overrides fragment.

    Empty selections on both checkboxes return {}, omitting the overrides
    key from the final payload so schema defaults stay in effect.
    """
    # Stub for Task 13.
    raise NotImplementedError("override matrix prompts not yet implemented")
```

- [ ] **Step 4: Run all wizard tests**

Run:
```bash
pytest tests/test_wizard.py -v -k override_toggles
```

Expected: PASS for the two consistency tests.

- [ ] **Step 5: Run the local CI parity chain**

Run:
```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/wizard/_overrides.py tests/test_wizard.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(wizard): _OVERRIDE_TOGGLES mapping + schema consistency tests"
```

---

### Task 13: `_overrides.py` — checkbox prompts + payload build

**Files:**
- Modify: `src/ks_gen/wizard/_overrides.py`
- Modify: `tests/test_wizard.py` (append checkbox + payload tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_wizard.py`:

```python
def test_overrides_empty_selection_returns_empty(monkeypatch: pytest.MonkeyPatch):
    _scripted(monkeypatch, {
        "ask_checkbox": [[], []],  # nothing disabled, nothing enabled
    })
    assert _overrides.prompts() == {}


def test_overrides_disable_one_default_on(monkeypatch: pytest.MonkeyPatch):
    _scripted(monkeypatch, {
        "ask_checkbox": [["faillock"], []],
    })
    assert _overrides.prompts() == {"faillock": {"enable": False}}


def test_overrides_enable_one_default_off(monkeypatch: pytest.MonkeyPatch):
    _scripted(monkeypatch, {
        "ask_checkbox": [[], ["dod_root_ca"]],
    })
    # dod_root_ca uses "install" attr, default False -> set install=True
    assert _overrides.prompts() == {"dod_root_ca": {"install": True}}


def test_overrides_mixed(monkeypatch: pytest.MonkeyPatch):
    _scripted(monkeypatch, {
        "ask_checkbox": [["package_purge"], ["usbguard"]],
    })
    assert _overrides.prompts() == {
        "package_purge": {"enable": False},
        "usbguard": {"enable": True},
    }
```

- [ ] **Step 2: Run failing tests**

Run:
```bash
pytest tests/test_wizard.py -v -k "overrides_empty or overrides_disable or overrides_enable or overrides_mixed"
```

Expected: `NotImplementedError` on each.

- [ ] **Step 3: Replace the stub `prompts()` in `_overrides.py`**

Replace the stub body with:

```python
def prompts() -> dict[str, Any]:
    on_choices = [
        (key, label)
        for key, (_attr, default, label) in _OVERRIDE_TOGGLES.items()
        if default is True
    ]
    off_choices = [
        (key, label)
        for key, (_attr, default, label) in _OVERRIDE_TOGGLES.items()
        if default is False
    ]

    to_disable: list[str] = _prompts.ask_checkbox(
        "Default-on rules to DISABLE:", on_choices
    )
    to_enable: list[str] = _prompts.ask_checkbox(
        "Default-off rules to ENABLE:", off_choices
    )

    payload: dict[str, Any] = {}
    for key in to_disable:
        attr, default, _label = _OVERRIDE_TOGGLES[key]
        # default=True -> set False to disable
        payload[key] = {attr: not default}
    for key in to_enable:
        attr, default, _label = _OVERRIDE_TOGGLES[key]
        # default=False -> set True to enable
        payload[key] = {attr: not default}
    return payload
```

- [ ] **Step 4: Run all wizard tests**

Run:
```bash
pytest tests/test_wizard.py -v
```

Expected: all pass.

- [ ] **Step 5: Run the local CI parity chain**

Run:
```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/wizard/_overrides.py tests/test_wizard.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(wizard): override matrix checkbox prompts + payload build"
```

---

### Task 14: Wire groups into `run_wizard()` orchestration

Replace the commented-out group orchestration in `__init__.py` with real calls.

**Files:**
- Modify: `src/ks_gen/wizard/__init__.py`
- Modify: `tests/test_wizard.py` (append integration tests)

- [ ] **Step 1: Write failing test**

Append to `tests/test_wizard.py`:

```python
# --- end-to-end orchestration tests ----------------------------------------


def test_run_wizard_disk_group_selected(monkeypatch: pytest.MonkeyPatch):
    _stdin(
        "host01\n\n\n\n\n"
        "ssh-ed25519 AAA test@example\n\n"
        "\n\n",
        monkeypatch,
    )
    monkeypatch.setattr(_prompts, "ask_checkbox", lambda *_a, **_kw: ["disk"])
    # Inject scripted disk-group answers
    _scripted(monkeypatch, {
        "select_one": ["stig_server", "none"],
        "ask_confirm": [True],
    })
    cfg, yaml_text = run_wizard(interactive=True)
    assert cfg.disk.preset is not None and cfg.disk.preset.value == "stig_server"
    assert cfg.disk.luks.preset.value == "none"
    assert cfg.disk.wipe is True
```

- [ ] **Step 2: Run the failing test**

Run:
```bash
pytest tests/test_wizard.py::test_run_wizard_disk_group_selected -v
```

Expected: failure — disk group is not yet wired.

- [ ] **Step 3: Update `src/ks_gen/wizard/__init__.py`**

Replace the file with:

```python
from __future__ import annotations

import yaml

from ks_gen.config import HostConfig
from ks_gen.wizard import _core, _disk, _network, _overrides, _prompts
from ks_gen.wizard._core import WizardError as WizardError
from ks_gen.wizard._core import write_initial as write_initial

__all__ = ["WizardError", "run_wizard", "write_initial"]

_GROUP_CHOICES: list[tuple[str, str]] = [
    ("disk", "Disk layout (preset, LUKS)"),
    ("network", "Network (interfaces)"),
    ("overrides", "Override matrix (per-rule toggles)"),
]


def _ask_groups() -> set[str]:
    return set(_prompts.ask_checkbox("Configure which optional sections?", _GROUP_CHOICES))


def run_wizard(*, interactive: bool) -> tuple[HostConfig, str]:
    payload = _core.prompts(interactive)
    selected: set[str] = _ask_groups() if interactive else set()
    if "disk" in selected:
        payload["disk"] = _disk.prompts()
    if "network" in selected:
        payload["network"] = _network.prompts()
    if "overrides" in selected:
        overrides_fragment = _overrides.prompts()
        if overrides_fragment:  # omit empty dict so schema defaults apply
            payload["overrides"] = overrides_fragment
    cfg = HostConfig.model_validate(payload)
    yaml_text = yaml.safe_dump(
        cfg.model_dump(mode="json"), sort_keys=False, default_flow_style=False
    )
    return cfg, yaml_text
```

- [ ] **Step 4: Run all wizard tests**

Run:
```bash
pytest tests/test_wizard.py -v
```

Expected: all pass.

- [ ] **Step 5: Run the local CI parity chain**

Run:
```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/wizard/__init__.py tests/test_wizard.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(wizard): wire disk/network/overrides groups into run_wizard"
```

---

### Task 15: End-to-end test — all groups selected produces a lint-clean kickstart

Confirms the full path: wizard → HostConfig → build_bundle → lint passes.

**Files:**
- Modify: `tests/test_wizard.py` (append e2e test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_wizard.py`:

```python
def test_run_wizard_all_groups_lints_clean(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    _stdin(
        "host01\n\n\n\n\n"
        "ssh-ed25519 AAA test@example\n\n"
        "\n\n",
        monkeypatch,
    )
    # script: group selector + every group's prompts, in call order.
    # The first ask_checkbox call is the group selector; the next two are
    # the override matrix's disable/enable lists.
    _scripted(monkeypatch, {
        "select_one": [
            "stig_server", "none",   # disk preset + LUKS
            "dhcp",                   # bootproto
        ],
        "ask_confirm": [
            True,                     # wipe
            True, False,              # onboot, add-another
        ],
        "ask_text": ["link"],         # device
        "ask_checkbox": [
            ["disk", "network", "overrides"],   # group selector
            [],                                  # disable nothing
            [],                                  # enable nothing
        ],
    })

    cfg, yaml_text = run_wizard(interactive=True)
    write_initial(tmp_path, cfg, yaml_text)

    # Render the bundle and lint
    from ks_gen.writer import build_bundle, write_bundle
    from ks_gen.lint import lint_kickstart

    bundle = build_bundle(cfg)
    host_dir = tmp_path / "host01"
    write_bundle(bundle, host_dir)
    report = lint_kickstart(host_dir / "ks.cfg")
    assert report.ok, f"lint failed: {report}"
```

- [ ] **Step 2: Run the test**

Run:
```bash
pytest tests/test_wizard.py::test_run_wizard_all_groups_lints_clean -v
```

Expected: PASS (the wizard already produces a valid HostConfig; build + lint pass).

- [ ] **Step 3: Run the local CI parity chain**

Run:
```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_wizard.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "test(wizard): end-to-end all-groups -> lint-clean ks.cfg"
```

---

### Task 16: KeyboardInterrupt + EOFError handling at `run_wizard()` boundary

Top-level catch in the orchestrator. EOFError is already handled inside `_core._ask` (raised when `sys.stdin.readline()` returns `""`); KeyboardInterrupt is what questionary raises (already propagated from the adapter on `None`).

**Files:**
- Modify: `src/ks_gen/wizard/__init__.py`
- Modify: `tests/test_wizard.py` (append error tests)

- [ ] **Step 1: Write failing test**

Append to `tests/test_wizard.py`:

```python
def test_run_wizard_keyboard_interrupt_becomes_wizard_error(
    monkeypatch: pytest.MonkeyPatch,
):
    _stdin(
        "host01\n\n\n\n\n"
        "ssh-ed25519 AAA test@example\n\n"
        "\n\n",
        monkeypatch,
    )
    def _raise_kbd(*_a: object, **_kw: object) -> Any:
        raise KeyboardInterrupt

    monkeypatch.setattr(_prompts, "ask_checkbox", _raise_kbd)

    with pytest.raises(WizardError, match="aborted"):
        run_wizard(interactive=True)
```

- [ ] **Step 2: Run the failing test**

Run:
```bash
pytest tests/test_wizard.py::test_run_wizard_keyboard_interrupt_becomes_wizard_error -v
```

Expected: failure — `KeyboardInterrupt` propagates uncaught.

- [ ] **Step 3: Update `run_wizard` to catch KeyboardInterrupt**

Replace the `run_wizard` function in `src/ks_gen/wizard/__init__.py` with:

```python
def run_wizard(*, interactive: bool) -> tuple[HostConfig, str]:
    try:
        payload = _core.prompts(interactive)
        selected: set[str] = _ask_groups() if interactive else set()
        if "disk" in selected:
            payload["disk"] = _disk.prompts()
        if "network" in selected:
            payload["network"] = _network.prompts()
        if "overrides" in selected:
            overrides_fragment = _overrides.prompts()
            if overrides_fragment:
                payload["overrides"] = overrides_fragment
        cfg = HostConfig.model_validate(payload)
        yaml_text = yaml.safe_dump(
            cfg.model_dump(mode="json"), sort_keys=False, default_flow_style=False
        )
        return cfg, yaml_text
    except KeyboardInterrupt as e:
        raise WizardError("aborted by user") from e
```

- [ ] **Step 4: Run all wizard tests**

Run:
```bash
pytest tests/test_wizard.py -v
```

Expected: all pass.

- [ ] **Step 5: Run the local CI parity chain**

Run:
```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/wizard/__init__.py tests/test_wizard.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "feat(wizard): map KeyboardInterrupt to WizardError(\"aborted by user\")"
```

---

### Task 17: Update `MANUAL.md` §5.1 — replace the v0.1 limitation

**Files:**
- Modify: `MANUAL.md:630-646`

- [ ] **Step 1: Replace the §5.1 block**

Replace lines 630-646 (the current §5.1 block) with:

```markdown
### 5.1 `ks-gen new`

Interactive wizard. Walks you through hostname, timezone, locale,
admin user, SSH keys, SSH port, and crypto policy, then offers an
opt-in checkbox for three optional sections: disk layout, network,
and the override matrix. Writes the full 4-file bundle.

```bash
ks-gen new --out ./build
# ./build/<hostname>/{host.yaml,ks.cfg,tailoring.xml,exceptions.md}

ks-gen new --out ./build --non-interactive
# Errors out unless every required field has a default;
# skips all optional sections (output matches the legacy 4-prompt run).
```

The optional sections cover:

- **Disk**: preset (`stig_server` / `minimal`), wipe confirmation,
  LUKS encryption (`none` / `partial` with inline or sidecar-file
  passphrase). Custom `disk.layout:`, `bootloader_password`, and
  `tang` LUKS are intentionally hand-edit only.
- **Network**: per-interface device, bootproto (dhcp / static), and
  for static interfaces IP / netmask / gateway / nameservers. Loops
  to "add another?" after each interface. Bond / bridge / VLAN are
  hand-edit only.
- **Override matrix**: two checkbox prompts — default-on rules to
  disable (`faillock`, `kernel_module_blacklist`, `package_purge`,
  `unattended_updates`), and default-off rules to enable (`usbguard`,
  `dod_root_ca`). Nested fields (e.g., `faillock.deny`,
  `unattended_updates.nightly_security.on_calendar`) remain
  hand-edit; same for `fips_mode`, `auditd_actions`, `ssh_keep_open`,
  and the `exceptions:` list.
```

- [ ] **Step 2: Spot-check the file renders**

Run:
```bash
pytest tests/test_smoke.py -v
```

Expected: all pass (the MANUAL update doesn't affect code tests).

- [ ] **Step 3: Run the local CI parity chain**

Run:
```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add MANUAL.md
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "docs(manual): wizard prompts disk/network/overrides — update §5.1"
```

---

### Task 18: Update `README.md` — remove the wizard limitation bullet

The quickstart's "v0.1 limitations" list at `README.md:58-63` has a bullet about the wizard covering only system/user/SSH/crypto. That's no longer true after this PR.

**Files:**
- Modify: `README.md:61-63`

- [ ] **Step 1: Remove the wizard limitation bullet**

In `README.md`, delete these three lines (lines 61-63 today):

```markdown
- **Wizard (`ks-gen new`) covers system / user / SSH / crypto only.**
  Disk, network, and override-matrix tuning go through hand-edited
  `host.yaml` + `ks-gen gen` for now.
```

Do NOT touch the surrounding bullets (the ISO and `disk.preset: custom` bullets are separate features and out of this PR's scope, even though they may also be stale — file follow-ups if you notice but don't bundle them here).

- [ ] **Step 2: Run the local CI parity chain**

Run:
```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green.

- [ ] **Step 3: Commit**

```bash
git add README.md
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
    commit -S -m "docs(readme): drop v0.1 wizard-limitation bullet (closes #9)"
```

---

### Task 19: Final CI parity + branch push + PR

- [ ] **Step 1: Run the full local CI parity chain a final time**

Run:
```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all green, all wizard tests included.

- [ ] **Step 2: Verify all commits on the branch are signed**

Run:
```bash
git log --format="%h %G? %s" main..HEAD
```

Expected: every line shows `G` (good signature). If any show `N`, stop and investigate before pushing.

- [ ] **Step 3: Push the branch**

Run:
```bash
git push -u origin impl/v0.7.0-wizard-disk-network-overrides
```

Expected: branch published.

- [ ] **Step 4: Open the pull request**

Run:
```bash
gh pr create --title "feat(wizard): disk / network / override matrix prompts (closes #9)" \
  --body "$(cat <<'EOF'
## Summary
- Closes #9. Extends `ks-gen new` with three opt-in prompt groups (disk, network, override matrix) gated by a questionary checkbox selector.
- Promotes `src/ks_gen/wizard.py` to a package; isolates `questionary` behind a single typed adapter (`wizard/_prompts.py`).
- Adds `tests/test_wizard.py` — covers both the new groups and the previously-untested 4-prompt path.
- Updates MANUAL.md §5.1 to remove the v0.1 wizard limitation note.

## Test plan
- [ ] CI green on 3.11 / 3.12 / 3.13
- [ ] `ks-gen new --out ./build` interactively — empty optional selection produces YAML byte-identical to pre-PR
- [ ] `ks-gen new --out ./build` with all optional groups selected — `ks-gen lint` exits 0 on the rendered ks.cfg

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed.

- [ ] **Step 5: Note follow-ups**

Filed as separate issues post-merge (already in the spec's non-goals):
- `ks-gen edit` command
- Bond / bridge / VLAN prompts
- Override matrix "customize" depth
- LUKS tang prompts

---

## Acceptance Verification (post-merge checklist)

These map directly to the spec's acceptance criteria:

1. **Byte-identical empty-selection** — covered by `test_run_wizard_empty_group_selector_matches_legacy` (Task 5).
2. **All groups → lint-clean ks.cfg** — covered by `test_run_wizard_all_groups_lints_clean` (Task 15).
3. **`--non-interactive` skips optionals** — covered by `test_run_wizard_non_interactive_skips_group_selector` (Task 5).
4. **`tests/test_wizard.py` coverage** — every public function in `wizard/` has a positive + a negative test.
5. **`MANUAL.md` §5.1 updated** — Task 17.
6. **`_OVERRIDE_TOGGLES` consistency** — Task 12.
7. **CI green on 3.11/3.12/3.13** — Task 19 Step 1 (local) and CI on the PR.
