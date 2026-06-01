# ks-gen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `ks-gen`, a Python 3.11+ CLI that generates remote-safe, DISA STIG-compliant AlmaLinux 9 kickstart configurations, per the design at `docs/superpowers/specs/2026-06-01-alma-stig-kickstart-design.md`.

**Architecture:** Hybrid STIG enforcement — most rules owned by `oscap` via the `%addon org_fedora_oscap` block with a per-host `tailoring.xml`; ~12 hand-rolled Rule objects own the named conflict points (admin user, SSH config, faillock, crypto-policy, banner, etc.). Inputs flow YAML → pydantic `HostConfig` → rule registry → tailoring XML + `%post` blocks → 4-file output bundle. Jinja2 renders the static kickstart skeleton; each rule emits its own `%post` shell.

**Tech Stack:** Python 3.11+, `typer` (CLI), `pydantic>=2` (config), `jinja2` (templating), `pyyaml`, `pykickstart` (lint), `pytest` + `syrupy` (tests), `ruff` + `mypy --strict` (lint/types), `xorriso` (ISO build, runtime).

---

## Working agreements (read before starting)

- **Signed commits:** Global git config on this machine is set with `user.email=github.v5f9w@bitbucket.onl`, `user.signingkey=BE707B220C995478`, `commit.gpgsign=true`. Plain `git commit -S -m "..."` will sign with the correct key. Never pass `--no-gpg-sign` or `--no-verify` without explicit user instruction. Never trigger the "GitHub Backup" scheduled task.
- **Source layout is `src/ks_gen/`** — keep imports `from ks_gen.xxx`, never `from xxx` (avoids editable-install surprises).
- **TDD:** Every task starts with a failing test. Run the test, see it fail, implement, see it pass, commit. No skipping.
- **Commit cadence:** One commit per completed task. Conventional-commits style (`feat:`, `test:`, `chore:`, `docs:`).
- **DRY/YAGNI:** No speculative abstraction. Each rule file is ~30–80 LOC; resist refactoring "common" rule code into a base class unless three rules genuinely share the same logic.

## File structure (informs decomposition)

```
src/ks_gen/
├── __init__.py              # __version__
├── __main__.py              # `python -m ks_gen`
├── cli.py                   # typer app: new, gen, iso, lint, rules, schema
├── wizard.py                # interactive flow for `new`
├── config.py                # pydantic models = host.yaml schema
├── loader.py                # YAML load + --set merge + cross-field validation
├── registry.py              # auto-discovers rules/*.py
├── topo.py                  # rule ordering + cycle detection
├── tailoring.py             # TailoringOp -> XCCDF XML
├── skeleton.py              # Jinja2 render of ks.cfg
├── writer.py                # 4-file output bundle
├── iso.py                   # xorriso wrapper
├── lint.py                  # ksvalidator + internal invariant re-check
├── exceptions_report.py     # exceptions.md generator
├── templates/
│   ├── ks.cfg.j2
│   └── partials/
│       ├── partitioning_stig_server.j2
│       ├── partitioning_minimal.j2
│       └── partitioning_custom.j2
└── rules/
    ├── __init__.py
    ├── _types.py            # TailoringOp, ExceptionEntry, Rule protocol
    ├── admin_user_and_keys.py
    ├── ssh_keep_open.py
    ├── ssh_config_apply.py
    ├── faillock_safety.py
    ├── crypto_policy.py
    ├── banner_text.py
    ├── time_servers.py
    ├── dod_root_ca.py
    ├── auditd_actions.py
    ├── usbguard.py
    ├── kernel_module_blacklist.py
    └── package_purge.py

tests/
├── conftest.py              # shared fixtures (minimal HostConfig builder)
├── test_loader.py
├── test_config_schema.py
├── test_registry.py
├── test_topo.py
├── test_tailoring.py
├── test_skeleton.py
├── test_writer.py
├── test_exceptions_report.py
├── test_invariants.py       # the three load-bearing safety properties
├── test_lint.py
├── test_iso.py
├── test_cli/
│   ├── test_gen.py
│   ├── test_new.py
│   ├── test_lint.py
│   ├── test_rules.py
│   └── test_schema.py
├── rules/
│   └── test_<each_rule>.py
└── golden/
    ├── minimal-dhcp.{host.yaml,ks.cfg,tailoring.xml,exceptions.md}
    ├── stig-strict.{host.yaml,ks.cfg,tailoring.xml,exceptions.md}
    ├── modern-crypto.{host.yaml,ks.cfg,tailoring.xml,exceptions.md}
    └── bare-metal-usbguard.{host.yaml,ks.cfg,tailoring.xml,exceptions.md}

pyproject.toml
.github/workflows/ci.yml
README.md
CHANGELOG.md
```

---

## Task 1: Bootstrap pyproject and src layout

**Files:**
- Create: `pyproject.toml`
- Create: `src/ks_gen/__init__.py`
- Create: `src/ks_gen/__main__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Write the failing smoke test**

`tests/test_smoke.py`:
```python
from ks_gen import __version__


def test_version_is_a_string():
    assert isinstance(__version__, str)
    assert __version__.count(".") >= 2
```

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "ks-gen"
version = "0.1.0"
requires-python = ">=3.11"
description = "Remote-safe DISA STIG kickstart generator for AlmaLinux 9."
authors = [{ name = "Patrick Connallon" }]
license = { file = "LICENSE" }
dependencies = [
  "typer>=0.12",
  "pydantic>=2.6",
  "jinja2>=3.1",
  "pyyaml>=6.0",
  "pykickstart>=3.52",
]

[project.optional-dependencies]
dev = [
  "pytest>=8",
  "syrupy>=4",
  "ruff>=0.5",
  "mypy>=1.10",
  "types-PyYAML",
]

[project.scripts]
ks-gen = "ks_gen.cli:app"

[tool.hatch.build.targets.wheel]
packages = ["src/ks_gen"]

[tool.hatch.build.targets.wheel.force-include]
"src/ks_gen/templates" = "ks_gen/templates"

[tool.ruff]
line-length = 100
target-version = "py311"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "RUF"]

[tool.mypy]
strict = true
files = ["src/ks_gen"]
mypy_path = "src"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = "-ra"
```

- [ ] **Step 3: Write `src/ks_gen/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Write `src/ks_gen/__main__.py`** (CLI entry indirection — `cli.py` will arrive in Task 30)

```python
from ks_gen.cli import app


if __name__ == "__main__":
    app()
```

Create empty `tests/__init__.py`.

- [ ] **Step 5: Install dev deps and run the smoke test**

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
.venv/Scripts/python.exe -m pytest tests/test_smoke.py -v
```

Expected: 1 passed.

(The `__main__.py` references `ks_gen.cli` which doesn't exist yet — that's fine because nothing imports it during the smoke test.)

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/ks_gen/__init__.py src/ks_gen/__main__.py tests/__init__.py tests/test_smoke.py
git commit -S -m "chore: bootstrap pyproject and src layout"
```

---

## Task 2: CI workflow (ruff → mypy → pytest)

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Write the workflow**

```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
          cache: pip
      - run: pip install -e ".[dev]"
      - run: ruff check src tests
      - run: ruff format --check src tests
      - run: mypy
      - run: pytest -q
```

- [ ] **Step 2: Run the same commands locally to confirm green**

```bash
.venv/Scripts/python.exe -m ruff check src tests
.venv/Scripts/python.exe -m ruff format --check src tests
.venv/Scripts/python.exe -m mypy
.venv/Scripts/python.exe -m pytest -q
```

Expected: all four exit 0.

If `ruff format --check` complains, run `ruff format src tests` once and commit the result with this task.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
# include any ruff format changes
git add src tests
git commit -S -m "ci: add ruff/mypy/pytest workflow"
```

---

## Task 3: Rule contract types

The Rule protocol and its supporting dataclasses. Every later task in Phase 6 depends on these.

**Files:**
- Create: `src/ks_gen/rules/__init__.py`
- Create: `src/ks_gen/rules/_types.py`
- Create: `tests/rules/__init__.py`
- Create: `tests/rules/test_types.py`

- [ ] **Step 1: Write the failing test**

`tests/rules/test_types.py`:
```python
from ks_gen.rules._types import ExceptionEntry, TailoringOp


def test_tailoring_op_disable():
    op = TailoringOp(rule_id="xccdf_org.ssgproject.content_rule_foo", action="disable")
    assert op.action == "disable"
    assert op.value is None


def test_tailoring_op_set_value():
    op = TailoringOp(
        rule_id="xccdf_org.ssgproject.content_value_bar",
        action="set_value",
        value="900",
    )
    assert op.value == "900"


def test_tailoring_op_set_value_requires_value():
    import pytest

    with pytest.raises(ValueError, match="set_value requires a value"):
        TailoringOp(rule_id="x", action="set_value")


def test_exception_entry_fields():
    entry = ExceptionEntry(
        rule_id="faillock_safety",
        summary="unlock_time=900 instead of STIG default 0",
        stig_rules_disabled=["xccdf_org.ssgproject.content_rule_pam_faillock_even_deny_root"],
        reason="Prevents permanent lockout of remote admin.",
    )
    assert entry.rule_id == "faillock_safety"
    assert len(entry.stig_rules_disabled) == 1
```

- [ ] **Step 2: Run it — expected fail**

```bash
.venv/Scripts/python.exe -m pytest tests/rules/test_types.py -v
```

Expected: `ModuleNotFoundError: No module named 'ks_gen.rules._types'`.

- [ ] **Step 3: Implement the types**

`src/ks_gen/rules/__init__.py`:
```python
```

(empty — discovery in Task 11 doesn't need anything here)

`src/ks_gen/rules/_types.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

TailoringAction = Literal["disable", "select", "set_value"]


@dataclass(frozen=True)
class TailoringOp:
    rule_id: str
    action: TailoringAction
    value: str | None = None

    def __post_init__(self) -> None:
        if self.action == "set_value" and self.value is None:
            raise ValueError("set_value requires a value")


@dataclass(frozen=True)
class ExceptionEntry:
    rule_id: str
    summary: str
    stig_rules_disabled: list[str] = field(default_factory=list)
    reason: str = ""


class Rule(Protocol):
    id: str
    summary: str
    depends_on: list[str]
    stig_rules_affected: list[str]

    def applies(self, cfg: "HostConfig") -> bool: ...
    def emit_tailoring(self, cfg: "HostConfig") -> list[TailoringOp]: ...
    def emit_post(self, cfg: "HostConfig") -> str: ...
    def exception_entry(self, cfg: "HostConfig") -> ExceptionEntry | None: ...
```

Create empty `tests/rules/__init__.py`.

- [ ] **Step 4: Run tests**

```bash
.venv/Scripts/python.exe -m pytest tests/rules/test_types.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/rules/__init__.py src/ks_gen/rules/_types.py tests/rules/__init__.py tests/rules/test_types.py
git commit -S -m "feat(rules): add Rule protocol, TailoringOp, ExceptionEntry"
```

---

## Task 4: HostConfig — `meta` and `system` sections

The first slice of the pydantic schema. Subsequent tasks extend it.

**Files:**
- Create: `src/ks_gen/config.py`
- Create: `tests/test_config_schema.py`

- [ ] **Step 1: Write the failing test**

`tests/test_config_schema.py`:
```python
import pytest
from pydantic import ValidationError

from ks_gen.config import HostConfig, Meta, System


def test_meta_defaults():
    m = Meta()
    assert m.release == "9"
    assert m.profile == "stig"
    assert m.scap_content == "ssg-almalinux9-ds.xml"


def test_system_requires_hostname():
    with pytest.raises(ValidationError):
        System()


def test_system_defaults():
    s = System(hostname="web01.example.com")
    assert s.timezone == "UTC"
    assert s.locale == "en_US.UTF-8"
    assert s.keyboard == "us"


def test_host_config_partial_ok():
    # Only meta + system are required at this stage.
    cfg = HostConfig.model_validate(
        {"meta": {}, "system": {"hostname": "web01.example.com"}}
    )
    assert cfg.system.hostname == "web01.example.com"


def test_unknown_top_level_key_rejected():
    with pytest.raises(ValidationError):
        HostConfig.model_validate(
            {"meta": {}, "system": {"hostname": "x"}, "garbage": True}
        )
```

- [ ] **Step 2: Run it — expected fail (ModuleNotFoundError)**

```bash
.venv/Scripts/python.exe -m pytest tests/test_config_schema.py -v
```

- [ ] **Step 3: Implement `config.py` (first slice)**

`src/ks_gen/config.py`:
```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Meta(StrictModel):
    release: str = "9"
    profile: str = "stig"
    scap_content: str = "ssg-almalinux9-ds.xml"


class System(StrictModel):
    hostname: str = Field(..., min_length=1)
    timezone: str = "UTC"
    locale: str = "en_US.UTF-8"
    keyboard: str = "us"


class HostConfig(StrictModel):
    meta: Meta = Field(default_factory=Meta)
    system: System
```

- [ ] **Step 4: Run tests**

```bash
.venv/Scripts/python.exe -m pytest tests/test_config_schema.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/config.py tests/test_config_schema.py
git commit -S -m "feat(config): meta and system models with strict validation"
```

---

## Task 5: HostConfig — `network` and `disk`

Extends the schema. New tests appended to `test_config_schema.py`.

**Files:**
- Modify: `src/ks_gen/config.py`
- Modify: `tests/test_config_schema.py`

- [ ] **Step 1: Write failing tests (append to `tests/test_config_schema.py`)**

```python
from ks_gen.config import Disk, DiskPreset, Interface, Network


def test_interface_dhcp_minimum():
    iface = Interface(device="link", bootproto="dhcp")
    assert iface.onboot is True
    assert iface.ip is None


def test_interface_static_requires_ip():
    with pytest.raises(ValidationError, match="ip is required"):
        Interface(device="enp1s0", bootproto="static")


def test_interface_static_complete():
    iface = Interface(
        device="enp1s0",
        bootproto="static",
        ip="10.0.0.10",
        netmask="255.255.255.0",
        gateway="10.0.0.1",
        nameservers=["1.1.1.1"],
    )
    assert iface.ip == "10.0.0.10"


def test_network_defaults():
    net = Network()
    assert net.interfaces[0].device == "link"
    assert net.interfaces[0].bootproto == "dhcp"
    assert net.hostname_from_dhcp is False


def test_disk_preset_default():
    d = Disk()
    assert d.preset == DiskPreset.STIG_SERVER
    assert d.wipe is True
    assert d.bootloader_password is None
```

- [ ] **Step 2: Run — expected fail**

```bash
.venv/Scripts/python.exe -m pytest tests/test_config_schema.py -v
```

- [ ] **Step 3: Extend `src/ks_gen/config.py`**

Add (at the top, with existing imports):
```python
from enum import Enum
from typing import Literal
from pydantic import field_validator, model_validator
```

Add (after `System`, before `HostConfig`):
```python
class Interface(StrictModel):
    device: str = "link"
    bootproto: Literal["dhcp", "static"] = "dhcp"
    onboot: bool = True
    ip: str | None = None
    netmask: str | None = None
    gateway: str | None = None
    nameservers: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _static_requires_fields(self) -> "Interface":
        if self.bootproto == "static":
            missing = [f for f in ("ip", "netmask", "gateway") if getattr(self, f) is None]
            if missing:
                raise ValueError(f"ip is required for static interfaces: missing {missing}")
        return self


class Network(StrictModel):
    interfaces: list[Interface] = Field(default_factory=lambda: [Interface()])
    dns_search: list[str] = Field(default_factory=list)
    hostname_from_dhcp: bool = False


class DiskPreset(str, Enum):
    STIG_SERVER = "stig_server"
    MINIMAL = "minimal"
    CUSTOM = "custom"


class Disk(StrictModel):
    preset: DiskPreset = DiskPreset.STIG_SERVER
    wipe: bool = True
    bootloader_password: str | None = None
```

Extend `HostConfig`:
```python
class HostConfig(StrictModel):
    meta: Meta = Field(default_factory=Meta)
    system: System
    network: Network = Field(default_factory=Network)
    disk: Disk = Field(default_factory=Disk)
```

- [ ] **Step 4: Run**

Expected: previous 5 + new 5 = 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/config.py tests/test_config_schema.py
git commit -S -m "feat(config): network and disk models with static-IP validation"
```

---

## Task 6: HostConfig — `user`, `ssh`, `banner`, `time`

**Files:**
- Modify: `src/ks_gen/config.py`
- Modify: `tests/test_config_schema.py`

- [ ] **Step 1: Failing tests (append)**

```python
from ks_gen.config import AdminUser, Banner, Ssh, Time, User


def test_admin_user_requires_keys_when_password_is_none():
    with pytest.raises(ValidationError, match="authorized_keys"):
        AdminUser(name="opsadmin", password=None, authorized_keys=[])


def test_admin_user_with_keys_ok():
    u = AdminUser(
        name="opsadmin",
        authorized_keys=["ssh-ed25519 AAAA... a@b"],
    )
    assert u.password is None
    assert u.groups == ["wheel"]


def test_admin_user_rejects_root():
    with pytest.raises(ValidationError, match="root"):
        AdminUser(name="root", authorized_keys=["ssh-ed25519 AAA a@b"])


def test_user_holds_admin():
    u = User(admin=AdminUser(name="opsadmin", authorized_keys=["ssh-ed25519 A a@b"]))
    assert u.admin.name == "opsadmin"


def test_ssh_defaults():
    s = Ssh()
    assert s.port == 22
    assert s.permit_root_login == "no"
    assert s.password_authentication is False
    assert s.client_alive_interval == 600


def test_banner_default_is_civilian():
    b = Banner()
    assert "U.S. Government" not in b.text
    assert "private" in b.text.lower()
    assert "issue" in b.apply_to


def test_time_defaults_are_not_dod():
    t = Time()
    assert t.servers == ["pool.ntp.org"]
    assert "usno" not in str(t.servers).lower()
```

- [ ] **Step 2: Run — expected fail**

- [ ] **Step 3: Extend `config.py`**

```python
DEFAULT_BANNER = (
    "WARNING: This is a private computer system. Unauthorized access is\n"
    "prohibited. All activity on this system may be monitored and logged.\n"
    "Use of this system constitutes consent to such monitoring.\n"
)


class AdminUser(StrictModel):
    name: str
    gecos: str = ""
    groups: list[str] = Field(default_factory=lambda: ["wheel"])
    shell: str = "/bin/bash"
    password: str | None = None
    sudo: Literal["nopasswd_no", "nopasswd_yes"] = "nopasswd_no"
    authorized_keys: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _not_root(cls, v: str) -> str:
        if v == "root":
            raise ValueError("admin name cannot be 'root'")
        return v

    @model_validator(mode="after")
    def _keys_or_password(self) -> "AdminUser":
        if self.password is None and not self.authorized_keys:
            raise ValueError(
                "user.admin.authorized_keys: at least one key required when password is null"
            )
        return self


class User(StrictModel):
    admin: AdminUser


class Ssh(StrictModel):
    port: int = Field(22, ge=1, le=65535)
    permit_root_login: Literal["no", "prohibit-password"] = "no"
    password_authentication: bool = False
    client_alive_interval: int = Field(600, ge=0)
    client_alive_count_max: int = Field(1, ge=0)
    max_auth_tries: int = Field(4, ge=1)
    use_pam: bool = True


class Banner(StrictModel):
    text: str = DEFAULT_BANNER
    apply_to: list[Literal["issue", "issue_net", "motd", "gdm"]] = Field(
        default_factory=lambda: ["issue", "issue_net", "motd", "gdm"]
    )


class Time(StrictModel):
    servers: list[str] = Field(default_factory=lambda: ["pool.ntp.org"])
    chrony_makestep_threshold: float = 1.0
```

Extend `HostConfig`:
```python
class HostConfig(StrictModel):
    meta: Meta = Field(default_factory=Meta)
    system: System
    network: Network = Field(default_factory=Network)
    disk: Disk = Field(default_factory=Disk)
    user: User
    ssh: Ssh = Field(default_factory=Ssh)
    banner: Banner = Field(default_factory=Banner)
    time: Time = Field(default_factory=Time)
```

- [ ] **Step 4: Run** — 17 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/config.py tests/test_config_schema.py
git commit -S -m "feat(config): user/ssh/banner/time with key-or-password and no-root invariants"
```

---

## Task 7: HostConfig — `crypto`, `packages`

**Files:**
- Modify: `src/ks_gen/config.py`
- Modify: `tests/test_config_schema.py`

- [ ] **Step 1: Failing tests**

```python
from ks_gen.config import CryptoPolicy, Crypto, Packages


def test_crypto_default_is_modern():
    assert Crypto().policy == CryptoPolicy.MODERN


def test_crypto_accepts_stig_and_future():
    assert Crypto(policy=CryptoPolicy.STIG).policy == CryptoPolicy.STIG
    assert Crypto(policy=CryptoPolicy.FUTURE).policy == CryptoPolicy.FUTURE


def test_packages_include_security_baseline():
    p = Packages()
    for required in (
        "scap-security-guide",
        "oscap-anaconda-addon",
        "aide",
        "firewalld",
        "chrony",
    ):
        assert required in p.required


def test_packages_exclude_known_legacy():
    p = Packages()
    for legacy in ("telnet-server", "rsh-server", "ypserv"):
        assert legacy in p.excluded
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

```python
class CryptoPolicy(str, Enum):
    STIG = "STIG"
    MODERN = "MODERN"
    FUTURE = "FUTURE"


class Crypto(StrictModel):
    policy: CryptoPolicy = CryptoPolicy.MODERN


class Packages(StrictModel):
    base_groups: list[str] = Field(
        default_factory=lambda: ["@^minimal-environment", "@standard"]
    )
    required: list[str] = Field(
        default_factory=lambda: [
            "scap-security-guide",
            "openscap-scanner",
            "oscap-anaconda-addon",
            "aide",
            "audit",
            "rsyslog",
            "chrony",
            "firewalld",
            "sudo",
            "policycoreutils-python-utils",
        ]
    )
    extra: list[str] = Field(default_factory=list)
    excluded: list[str] = Field(
        default_factory=lambda: [
            "telnet-server",
            "rsh-server",
            "tftp-server",
            "vsftpd",
            "ypserv",
        ]
    )
```

Extend `HostConfig` with `crypto: Crypto = Field(default_factory=Crypto)` and `packages: Packages = Field(default_factory=Packages)`.

- [ ] **Step 4: Run** — 21 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/config.py tests/test_config_schema.py
git commit -S -m "feat(config): crypto policy enum and package baseline"
```

---

## Task 8: HostConfig — `overrides`

The big one — all 12 override knobs.

**Files:**
- Modify: `src/ks_gen/config.py`
- Modify: `tests/test_config_schema.py`

- [ ] **Step 1: Failing tests**

```python
from ks_gen.config import (
    AuditdActionsCfg,
    AuditdMaxFileAction,
    AuditdSystemAction,
    DodRootCaCfg,
    FaillockCfg,
    KernelModuleBlacklistCfg,
    Overrides,
    PackagePurgeCfg,
    SshKeepOpenCfg,
    UsbguardCfg,
)


def test_overrides_safe_defaults():
    o = Overrides()
    assert o.fips_mode is False
    assert o.faillock.unlock_time == 900
    assert o.faillock.even_deny_root is False
    assert o.auditd.disk_full_action == AuditdSystemAction.SUSPEND
    assert o.auditd.max_log_file_action == AuditdMaxFileAction.ROTATE
    assert o.ssh_keep_open.ensure_firewalld_port is True
    assert o.usbguard.enable is False
    assert o.dod_root_ca.install is False
    assert "usb-storage" in o.kernel_module_blacklist.modules


def test_auditd_actions_reject_bogus():
    with pytest.raises(ValidationError):
        AuditdActionsCfg(disk_full_action="BURN")  # type: ignore[arg-type]
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

```python
class FaillockCfg(StrictModel):
    enable: bool = True
    deny: int = Field(3, ge=1)
    unlock_time: int = Field(900, ge=0)
    even_deny_root: bool = False


class AuditdSystemAction(str, Enum):
    SUSPEND = "SUSPEND"
    SYSLOG = "SYSLOG"
    HALT = "HALT"
    SINGLE = "SINGLE"


class AuditdMaxFileAction(str, Enum):
    ROTATE = "ROTATE"
    KEEP_LOGS = "keep_logs"
    SYSLOG = "SYSLOG"
    IGNORE = "IGNORE"


class AuditdActionsCfg(StrictModel):
    disk_full_action: AuditdSystemAction = AuditdSystemAction.SUSPEND
    disk_error_action: AuditdSystemAction = AuditdSystemAction.SUSPEND
    max_log_file_action: AuditdMaxFileAction = AuditdMaxFileAction.ROTATE


class SshKeepOpenCfg(StrictModel):
    ensure_firewalld_port: bool = True
    ensure_selinux_port: bool = True


class UsbguardCfg(StrictModel):
    enable: bool = False


class KernelModuleBlacklistCfg(StrictModel):
    enable: bool = True
    modules: list[str] = Field(
        default_factory=lambda: [
            "usb-storage",
            "cramfs",
            "freevxfs",
            "jffs2",
            "hfs",
            "hfsplus",
            "squashfs",
            "udf",
        ]
    )


class PackagePurgeCfg(StrictModel):
    enable: bool = True


class DodRootCaCfg(StrictModel):
    install: bool = False


class Overrides(StrictModel):
    fips_mode: bool = False
    faillock: FaillockCfg = Field(default_factory=FaillockCfg)
    auditd: AuditdActionsCfg = Field(default_factory=AuditdActionsCfg)
    ssh_keep_open: SshKeepOpenCfg = Field(default_factory=SshKeepOpenCfg)
    usbguard: UsbguardCfg = Field(default_factory=UsbguardCfg)
    kernel_module_blacklist: KernelModuleBlacklistCfg = Field(
        default_factory=KernelModuleBlacklistCfg
    )
    package_purge: PackagePurgeCfg = Field(default_factory=PackagePurgeCfg)
    dod_root_ca: DodRootCaCfg = Field(default_factory=DodRootCaCfg)
```

Extend `HostConfig` with `overrides: Overrides = Field(default_factory=Overrides)`.

- [ ] **Step 4: Run** — 23 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/config.py tests/test_config_schema.py
git commit -S -m "feat(config): overrides matrix with remote-safe defaults"
```

---

## Task 9: HostConfig — `custom_post`, `exceptions`, cross-field validation

**Files:**
- Modify: `src/ks_gen/config.py`
- Modify: `tests/test_config_schema.py`

- [ ] **Step 1: Failing tests**

```python
from ks_gen.config import ExceptionDecl


def test_custom_post_passes_through():
    cfg = HostConfig.model_validate(
        {
            "system": {"hostname": "x"},
            "user": {"admin": {"name": "ops", "authorized_keys": ["ssh-ed25519 A a@b"]}},
            "custom_post": ["echo hello"],
        }
    )
    assert cfg.custom_post == ["echo hello"]


def test_exception_decl_requires_rule_ids():
    with pytest.raises(ValidationError):
        ExceptionDecl(id="no-luks", reason="x", stig_rules_disabled=[])


def test_modern_crypto_and_fips_mode_rejected():
    payload = {
        "system": {"hostname": "x"},
        "user": {"admin": {"name": "ops", "authorized_keys": ["ssh-ed25519 A a@b"]}},
        "crypto": {"policy": "MODERN"},
        "overrides": {"fips_mode": True},
    }
    with pytest.raises(ValidationError, match="MODERN.*fips_mode"):
        HostConfig.model_validate(payload)


def test_stig_crypto_without_fips_allowed():
    cfg = HostConfig.model_validate(
        {
            "system": {"hostname": "x"},
            "user": {"admin": {"name": "ops", "authorized_keys": ["ssh-ed25519 A a@b"]}},
            "crypto": {"policy": "STIG"},
            "overrides": {"fips_mode": False},
        }
    )
    assert cfg.crypto.policy == CryptoPolicy.STIG
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

```python
class ExceptionDecl(StrictModel):
    id: str
    reason: str
    stig_rules_disabled: list[str] = Field(..., min_length=1)
```

Extend `HostConfig` to add `custom_post`, `exceptions`, and the mutex:
```python
class HostConfig(StrictModel):
    meta: Meta = Field(default_factory=Meta)
    system: System
    network: Network = Field(default_factory=Network)
    disk: Disk = Field(default_factory=Disk)
    user: User
    ssh: Ssh = Field(default_factory=Ssh)
    banner: Banner = Field(default_factory=Banner)
    time: Time = Field(default_factory=Time)
    crypto: Crypto = Field(default_factory=Crypto)
    packages: Packages = Field(default_factory=Packages)
    overrides: Overrides = Field(default_factory=Overrides)
    custom_post: list[str] = Field(default_factory=list)
    exceptions: list[ExceptionDecl] = Field(default_factory=list)

    @model_validator(mode="after")
    def _crypto_fips_mutex(self) -> "HostConfig":
        if self.crypto.policy in (CryptoPolicy.MODERN, CryptoPolicy.FUTURE):
            if self.overrides.fips_mode:
                raise ValueError(
                    "crypto.policy=MODERN/FUTURE conflicts with overrides.fips_mode=true: "
                    "FIPS kernel mode blocks Curve25519/Ed25519 at the kernel layer."
                )
        return self
```

- [ ] **Step 4: Run** — 27 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/config.py tests/test_config_schema.py
git commit -S -m "feat(config): custom_post, exception declarations, crypto/fips mutex"
```

---

## Task 10: YAML loader with `--set` overrides

**Files:**
- Create: `src/ks_gen/loader.py`
- Create: `tests/test_loader.py`

- [ ] **Step 1: Failing test**

`tests/test_loader.py`:
```python
import textwrap

import pytest

from ks_gen.config import CryptoPolicy
from ks_gen.loader import ConfigError, ExitCode, load_host_config


MIN_YAML = textwrap.dedent(
    """\
    system:
      hostname: web01.example.com
    user:
      admin:
        name: opsadmin
        authorized_keys:
          - "ssh-ed25519 AAAA a@b"
    """
)


def test_load_minimal_yaml(tmp_path):
    f = tmp_path / "host.yaml"
    f.write_text(MIN_YAML, encoding="utf-8")
    cfg = load_host_config(f, sets=[])
    assert cfg.system.hostname == "web01.example.com"
    assert cfg.crypto.policy == CryptoPolicy.MODERN


def test_set_overrides_string(tmp_path):
    f = tmp_path / "host.yaml"
    f.write_text(MIN_YAML, encoding="utf-8")
    cfg = load_host_config(f, sets=["ssh.port=2222"])
    assert cfg.ssh.port == 2222


def test_set_overrides_bool_and_nested(tmp_path):
    f = tmp_path / "host.yaml"
    f.write_text(MIN_YAML, encoding="utf-8")
    cfg = load_host_config(
        f, sets=["overrides.fips_mode=true", "crypto.policy=STIG"]
    )
    assert cfg.crypto.policy == CryptoPolicy.STIG
    assert cfg.overrides.fips_mode is True


def test_set_invalid_syntax_raises(tmp_path):
    f = tmp_path / "host.yaml"
    f.write_text(MIN_YAML, encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_host_config(f, sets=["ssh.port"])
    assert exc.value.exit_code == ExitCode.USAGE


def test_crypto_fips_conflict_returns_exit_3(tmp_path):
    f = tmp_path / "host.yaml"
    f.write_text(MIN_YAML, encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_host_config(f, sets=["overrides.fips_mode=true"])
    assert exc.value.exit_code == ExitCode.RULE_CONFLICT
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

`src/ks_gen/loader.py`:
```python
from __future__ import annotations

from enum import IntEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ks_gen.config import HostConfig


class ExitCode(IntEnum):
    OK = 0
    USAGE = 1
    CONFIG_INVALID = 2
    RULE_CONFLICT = 3
    LINT_FAIL = 4
    TOOL_MISSING = 5


class ConfigError(Exception):
    def __init__(self, message: str, exit_code: ExitCode):
        super().__init__(message)
        self.exit_code = exit_code


def _parse_scalar(raw: str) -> Any:
    """Best-effort YAML-style scalar coercion for --set RHS."""
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    if raw.lower() in ("null", "none", "~"):
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        return raw[1:-1]
    return raw


def _apply_set(data: dict[str, Any], expr: str) -> None:
    if "=" not in expr:
        raise ConfigError(
            f"--set expression must be KEY=VALUE: got {expr!r}", ExitCode.USAGE
        )
    key, _, raw = expr.partition("=")
    path = [p for p in key.split(".") if p]
    if not path:
        raise ConfigError(f"--set key is empty: {expr!r}", ExitCode.USAGE)
    cursor = data
    for segment in path[:-1]:
        if segment not in cursor or not isinstance(cursor[segment], dict):
            cursor[segment] = {}
        cursor = cursor[segment]
    cursor[path[-1]] = _parse_scalar(raw)


def load_host_config(path: Path, sets: list[str]) -> HostConfig:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"cannot read {path}: {e}", ExitCode.USAGE) from e
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"YAML parse error: {e}", ExitCode.CONFIG_INVALID) from e
    if not isinstance(data, dict):
        raise ConfigError("host.yaml top level must be a mapping", ExitCode.CONFIG_INVALID)
    for s in sets:
        _apply_set(data, s)
    try:
        return HostConfig.model_validate(data)
    except ValidationError as e:
        msg = str(e)
        code = (
            ExitCode.RULE_CONFLICT
            if ("MODERN" in msg and "fips_mode" in msg)
            else ExitCode.CONFIG_INVALID
        )
        raise ConfigError(msg, code) from e
```

- [ ] **Step 4: Run** — 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/loader.py tests/test_loader.py
git commit -S -m "feat(loader): YAML load with --set overrides and exit-code typing"
```

---

## Task 11: Rule registry — filesystem discovery

**Files:**
- Create: `src/ks_gen/registry.py`
- Create: `tests/test_registry.py`
- Create: `src/ks_gen/rules/_stub_noop.py` *(test-only stub; gets removed in Task 15)*
- Modify: `src/ks_gen/rules/__init__.py` (keep empty)

- [ ] **Step 1: Failing test**

`tests/test_registry.py`:
```python
from ks_gen.registry import load_rules


def test_registry_discovers_modules():
    rules = load_rules()
    ids = {r.id for r in rules}
    # Stub rule from Task 11; will be removed in Task 15.
    assert "stub_noop" in ids


def test_registry_skips_underscore_modules():
    rules = load_rules()
    ids = {r.id for r in rules}
    assert "_types" not in ids  # ensure private modules ignored


def test_registry_returns_rule_instances():
    rules = load_rules()
    for r in rules:
        assert hasattr(r, "id")
        assert hasattr(r, "applies")
        assert hasattr(r, "emit_post")
```

- [ ] **Step 2: Run — fail (registry missing)**

- [ ] **Step 3: Implement registry**

`src/ks_gen/registry.py`:
```python
from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Iterable

from ks_gen.rules._types import Rule


def load_rules() -> list[Rule]:
    import ks_gen.rules as pkg

    discovered: list[Rule] = []
    for info in pkgutil.iter_modules(pkg.__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"ks_gen.rules.{info.name}")
        rule = getattr(module, "RULE", None)
        if rule is None:
            raise RuntimeError(
                f"ks_gen.rules.{info.name} does not export a module-level RULE binding"
            )
        discovered.append(rule)
    return discovered


def rule_ids(rules: Iterable[Rule]) -> list[str]:
    return [r.id for r in rules]
```

- [ ] **Step 4: Implement the stub rule (will be deleted in Task 15)**

`src/ks_gen/rules/_stub_noop.py`:

```python
# Removed in Task 15 once a real rule is in place. The leading underscore
# would normally hide it; this file is named without one intentionally for
# the duration of Tasks 11–14 so the registry discovers something.
```

Rename it back to `src/ks_gen/rules/stub_noop.py` (no leading underscore) with this content:
```python
from __future__ import annotations

from dataclasses import dataclass, field

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if False:  # TYPE_CHECKING-only
    from ks_gen.config import HostConfig


@dataclass(frozen=True)
class _StubNoOp:
    id: str = "stub_noop"
    summary: str = "Test stub; removed in Task 15."
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: "HostConfig") -> bool:
        return False

    def emit_tailoring(self, cfg: "HostConfig") -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: "HostConfig") -> str:
        return ""

    def exception_entry(self, cfg: "HostConfig") -> ExceptionEntry | None:
        return None


RULE: Rule = _StubNoOp()
```

(Delete the placeholder `_stub_noop.py` if you created it; the actual file is `stub_noop.py` without a leading underscore.)

- [ ] **Step 5: Run tests**

```bash
.venv/Scripts/python.exe -m pytest tests/test_registry.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/registry.py src/ks_gen/rules/stub_noop.py tests/test_registry.py
git commit -S -m "feat(registry): filesystem discovery of rules/*.py with RULE binding"
```

---

## Task 12: Topological sort with cycle detection

**Files:**
- Create: `src/ks_gen/topo.py`
- Create: `tests/test_topo.py`

- [ ] **Step 1: Failing test**

`tests/test_topo.py`:
```python
from dataclasses import dataclass, field

import pytest

from ks_gen.topo import CycleError, topo_sort


@dataclass(frozen=True)
class _R:
    id: str
    depends_on: list[str] = field(default_factory=list)


def test_topo_preserves_order_when_independent():
    rules = [_R("a"), _R("b"), _R("c")]
    assert [r.id for r in topo_sort(rules)] == ["a", "b", "c"]


def test_topo_orders_dependencies():
    rules = [
        _R("c", ["a", "b"]),
        _R("b", ["a"]),
        _R("a"),
    ]
    out = [r.id for r in topo_sort(rules)]
    assert out.index("a") < out.index("b") < out.index("c")


def test_topo_detects_cycles():
    rules = [_R("a", ["b"]), _R("b", ["a"])]
    with pytest.raises(CycleError, match="cycle"):
        topo_sort(rules)


def test_topo_detects_missing_dep():
    rules = [_R("a", ["ghost"])]
    with pytest.raises(KeyError, match="ghost"):
        topo_sort(rules)
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

`src/ks_gen/topo.py`:
```python
from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, TypeVar


class _HasIdAndDeps(Protocol):
    id: str
    depends_on: list[str]


T = TypeVar("T", bound=_HasIdAndDeps)


class CycleError(Exception):
    pass


def topo_sort(rules: Iterable[T]) -> list[T]:
    by_id: dict[str, T] = {r.id: r for r in rules}
    visited: dict[str, str] = {}  # id -> "in" | "done"
    order: list[T] = []

    def visit(node_id: str) -> None:
        state = visited.get(node_id)
        if state == "done":
            return
        if state == "in":
            raise CycleError(f"cycle detected at rule {node_id!r}")
        if node_id not in by_id:
            raise KeyError(f"unknown dependency rule id: {node_id!r}")
        visited[node_id] = "in"
        for dep in by_id[node_id].depends_on:
            visit(dep)
        visited[node_id] = "done"
        order.append(by_id[node_id])

    for r in by_id.values():
        visit(r.id)
    return order
```

- [ ] **Step 4: Run** — 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/topo.py tests/test_topo.py
git commit -S -m "feat(topo): topological sort with cycle and missing-dep detection"
```

---

## Task 13: Tailoring XML builder

**Files:**
- Create: `src/ks_gen/tailoring.py`
- Create: `tests/test_tailoring.py`

- [ ] **Step 1: Failing test**

`tests/test_tailoring.py`:
```python
from ks_gen.rules._types import TailoringOp
from ks_gen.tailoring import build_tailoring_xml


def test_empty_ops_produces_skeleton():
    xml = build_tailoring_xml([], profile_id="xccdf_org.ssgproject.content_profile_stig")
    assert "<xccdf:Tailoring" in xml
    assert "extends=\"xccdf_org.ssgproject.content_profile_stig\"" in xml


def test_disable_rule_select_false():
    ops = [TailoringOp(rule_id="xccdf_org.ssgproject.content_rule_foo", action="disable")]
    xml = build_tailoring_xml(ops, profile_id="xccdf_org.ssgproject.content_profile_stig")
    assert (
        '<xccdf:select idref="xccdf_org.ssgproject.content_rule_foo" selected="false"/>'
        in xml
    )


def test_set_value_emits_set_value_element():
    ops = [
        TailoringOp(
            rule_id="xccdf_org.ssgproject.content_value_var_auditd_disk_full_action",
            action="set_value",
            value="SUSPEND",
        )
    ]
    xml = build_tailoring_xml(ops, profile_id="xccdf_org.ssgproject.content_profile_stig")
    assert (
        '<xccdf:set-value idref="xccdf_org.ssgproject.content_value_var_auditd_disk_full_action">'
        "SUSPEND</xccdf:set-value>" in xml
    )


def test_select_action_select_true():
    ops = [TailoringOp(rule_id="xccdf_org.ssgproject.content_rule_bar", action="select")]
    xml = build_tailoring_xml(ops, profile_id="xccdf_org.ssgproject.content_profile_stig")
    assert (
        '<xccdf:select idref="xccdf_org.ssgproject.content_rule_bar" selected="true"/>'
        in xml
    )
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

`src/ks_gen/tailoring.py`:
```python
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterable
from datetime import datetime, timezone

from ks_gen.rules._types import TailoringOp

XCCDF_NS = "http://checklists.nist.gov/xccdf/1.2"

_HEADER = (
    "<?xml version='1.0' encoding='UTF-8'?>\n"
    '<xccdf:Tailoring xmlns:xccdf="http://checklists.nist.gov/xccdf/1.2" '
    'id="xccdf_ks-gen_tailoring_default">\n'
    '  <xccdf:benchmark href="/usr/share/xml/scap/ssg/content/ssg-almalinux9-ds.xml"/>\n'
    '  <xccdf:version time="{timestamp}">1</xccdf:version>\n'
    '  <xccdf:Profile id="xccdf_ks-gen_profile_tailored" extends="{profile_id}">\n'
    '    <xccdf:title xml:lang="en-US">ks-gen tailored {profile_id}</xccdf:title>\n'
    '    <xccdf:description xml:lang="en-US">Tailoring generated by ks-gen.</xccdf:description>\n'
)

_FOOTER = "  </xccdf:Profile>\n</xccdf:Tailoring>\n"


def build_tailoring_xml(ops: Iterable[TailoringOp], *, profile_id: str) -> str:
    body: list[str] = []
    for op in ops:
        if op.action == "disable":
            body.append(f'    <xccdf:select idref="{op.rule_id}" selected="false"/>')
        elif op.action == "select":
            body.append(f'    <xccdf:select idref="{op.rule_id}" selected="true"/>')
        elif op.action == "set_value":
            value = "" if op.value is None else _escape(op.value)
            body.append(
                f'    <xccdf:set-value idref="{op.rule_id}">{value}</xccdf:set-value>'
            )
    head = _HEADER.format(
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        profile_id=profile_id,
    )
    return head + ("\n".join(body) + "\n" if body else "") + _FOOTER


def _escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
```

- [ ] **Step 4: Run** — 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/tailoring.py tests/test_tailoring.py
git commit -S -m "feat(tailoring): TailoringOp -> XCCDF 1.2 tailoring XML"
```

---

## Task 14: Jinja2 skeleton renderer

**Files:**
- Create: `src/ks_gen/templates/ks.cfg.j2`
- Create: `src/ks_gen/templates/partials/partitioning_stig_server.j2`
- Create: `src/ks_gen/templates/partials/partitioning_minimal.j2`
- Create: `src/ks_gen/skeleton.py`
- Create: `tests/test_skeleton.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Shared fixture for a minimal HostConfig**

`tests/conftest.py`:
```python
from __future__ import annotations

import pytest

from ks_gen.config import AdminUser, HostConfig, System, User


@pytest.fixture()
def minimal_cfg() -> HostConfig:
    return HostConfig(
        system=System(hostname="web01.example.com"),
        user=User(admin=AdminUser(name="opsadmin", authorized_keys=["ssh-ed25519 AAAA a@b"])),
    )
```

- [ ] **Step 2: Failing test**

`tests/test_skeleton.py`:
```python
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
```

- [ ] **Step 3: Run — fail**

- [ ] **Step 4: Write the Jinja2 template**

`src/ks_gen/templates/ks.cfg.j2`:
```jinja
# Generated by ks-gen v{{ version }} on {{ generated_at }}
# Source profile: xccdf_org.ssgproject.content_profile_{{ cfg.meta.profile }}
# DO NOT EDIT by hand — regenerate with `ks-gen gen --config <yaml>`

text
lang {{ cfg.system.locale }}
keyboard {{ cfg.system.keyboard }}
timezone {{ cfg.system.timezone }} --utc

{% for iface in cfg.network.interfaces -%}
network --device={{ iface.device }} --bootproto={{ iface.bootproto }}{% if iface.bootproto == 'static' %} --ip={{ iface.ip }} --netmask={{ iface.netmask }} --gateway={{ iface.gateway }}{% if iface.nameservers %} --nameserver={{ iface.nameservers | join(',') }}{% endif %}{% endif %} --hostname={{ cfg.system.hostname }} --onboot={{ 'yes' if iface.onboot else 'no' }}
{% endfor %}

rootpw --lock
{% if cfg.disk.bootloader_password -%}
bootloader --location=mbr --append="audit=1 audit_backlog_limit=8192{% if cfg.overrides.fips_mode %} fips=1{% endif %}" --password="{{ cfg.disk.bootloader_password }}"
{% else -%}
bootloader --location=mbr --append="audit=1 audit_backlog_limit=8192{% if cfg.overrides.fips_mode %} fips=1{% endif %}"
{% endif %}

{% if cfg.disk.wipe -%}
zerombr
clearpart --all --initlabel
{% endif -%}

{% include 'partials/partitioning_' ~ cfg.disk.preset.value ~ '.j2' %}

services --enabled=chronyd,firewalld,auditd,rsyslog,sshd
authselect select sssd --force

%packages
{% for grp in cfg.packages.base_groups %}{{ grp }}
{% endfor -%}
{% for pkg in cfg.packages.required %}{{ pkg }}
{% endfor -%}
{% for pkg in cfg.packages.extra %}{{ pkg }}
{% endfor -%}
{% for pkg in cfg.packages.excluded %}-{{ pkg }}
{% endfor -%}
%end

%addon org_fedora_oscap
  content-type = scap-security-guide
  profile = xccdf_org.ssgproject.content_profile_{{ cfg.meta.profile }}
  tailoring-path = /tailoring.xml
%end

%post --erroronfail --log=/root/ks-post.log
set -euxo pipefail

{% for block in post_blocks %}
# ===== {{ block.rule_id if block.rule_id is defined else 'block' }} =====
{{ block.body if block.body is defined else block }}

{% endfor -%}

{% for block in cfg.custom_post -%}
# ===== custom_post =====
{{ block }}

{% endfor -%}

%end

reboot --eject
```

`src/ks_gen/templates/partials/partitioning_stig_server.j2`:
```jinja
part /boot/efi --fstype=efi --size=1024 --asprimary
part /boot --fstype=xfs --size=1024 --fsoptions="nodev,nosuid" --asprimary
part pv.01 --grow --size=1
volgroup vg_root pv.01
logvol /             --vgname=vg_root --name=root     --fstype=xfs --size=15360
logvol /home         --vgname=vg_root --name=home     --fstype=xfs --size=5120  --fsoptions="nodev,nosuid"
logvol /tmp          --vgname=vg_root --name=tmp      --fstype=xfs --size=3072  --fsoptions="nodev,nosuid,noexec"
logvol /var          --vgname=vg_root --name=var      --fstype=xfs --size=10240 --fsoptions="nodev"
logvol /var/log      --vgname=vg_root --name=varlog   --fstype=xfs --size=5120  --fsoptions="nodev,nosuid,noexec"
logvol /var/log/audit --vgname=vg_root --name=varlogaudit --fstype=xfs --size=3072 --fsoptions="nodev,nosuid,noexec"
logvol /var/tmp      --vgname=vg_root --name=vartmp   --fstype=xfs --size=2048  --fsoptions="nodev,nosuid,noexec"
logvol swap          --vgname=vg_root --name=swap     --fstype=swap --recommended
```

`src/ks_gen/templates/partials/partitioning_minimal.j2`:
```jinja
part /boot/efi --fstype=efi --size=1024 --asprimary
part /boot --fstype=xfs --size=1024 --fsoptions="nodev,nosuid" --asprimary
part / --fstype=xfs --grow --size=8192
part swap --recommended
```

- [ ] **Step 5: Implement the renderer**

`src/ks_gen/skeleton.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.resources import files

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from ks_gen import __version__
from ks_gen.config import HostConfig


@dataclass(frozen=True)
class PostBlock:
    rule_id: str
    body: str


def _env() -> Environment:
    templates_path = files("ks_gen") / "templates"
    return Environment(
        loader=FileSystemLoader(str(templates_path)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render_skeleton(cfg: HostConfig, post_blocks: list[PostBlock | str]) -> str:
    env = _env()
    template = env.get_template("ks.cfg.j2")
    return template.render(
        cfg=cfg,
        post_blocks=post_blocks,
        version=__version__,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
```

- [ ] **Step 6: Run tests**

```bash
.venv/Scripts/python.exe -m pytest tests/test_skeleton.py -v
```

Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add src/ks_gen/templates src/ks_gen/skeleton.py tests/test_skeleton.py tests/conftest.py
git commit -S -m "feat(skeleton): Jinja2 ks.cfg template with stig_server/minimal partitioning"
```

---

## Continued in the next chunk

Tasks 15–41 follow in the same TDD format. Each rule task is one file in `src/ks_gen/rules/`, one file in `tests/rules/`, one commit. The remaining tasks are:

- **15–26:** Rule implementations (one task per rule)
- **27:** Output writer (4-file bundle)
- **28:** `exceptions_report.py`
- **29:** Invariant tests (the three load-bearing properties)
- **30:** `gen` CLI subcommand
- **31:** `lint.py` (ksvalidator + internal re-parse)
- **32:** `lint` CLI subcommand
- **33:** `rules` CLI subcommand
- **34:** `schema` CLI subcommand
- **35:** `wizard.py` and `new` CLI subcommand
- **36:** `iso.py` and `iso` CLI subcommand
- **37–40:** Golden snapshots (one per scenario)
- **41:** README + CHANGELOG

These get filled in immediately below.

---

## Task 15: Rule `admin_user_and_keys`

This rule runs first in every `%post`. Also: **delete `src/ks_gen/rules/stub_noop.py`** as part of this task (no longer needed once a real rule exists).

**Files:**
- Create: `src/ks_gen/rules/admin_user_and_keys.py`
- Create: `tests/rules/test_admin_user_and_keys.py`
- Delete: `src/ks_gen/rules/stub_noop.py`
- Modify: `tests/test_registry.py` (drop the `stub_noop` assertion; assert `admin_user_and_keys` instead)

- [ ] **Step 1: Failing test**

`tests/rules/test_admin_user_and_keys.py`:
```python
from ks_gen.rules.admin_user_and_keys import RULE


def test_applies_always(minimal_cfg):
    assert RULE.applies(minimal_cfg)


def test_emits_no_tailoring(minimal_cfg):
    assert RULE.emit_tailoring(minimal_cfg) == []


def test_post_creates_user_with_authorized_keys(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "useradd" in out
    assert "opsadmin" in out
    assert "wheel" in out
    assert ".ssh/authorized_keys" in out
    assert "ssh-ed25519 AAAA a@b" in out
    assert "chmod 600" in out
    assert "restorecon" in out


def test_post_writes_sudoers_fragment(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "/etc/sudoers.d/00-ks-gen-admin" in out


def test_no_exception_entry_unless_overridden(minimal_cfg):
    assert RULE.exception_entry(minimal_cfg) is None


def test_post_is_idempotent_via_guards(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    # We don't actually re-run; we just confirm guards exist that would
    # let the script be re-run without failure.
    assert "id -u" in out or "getent passwd" in out
```

Update `tests/test_registry.py`: replace the body of `test_registry_discovers_modules` with:
```python
def test_registry_discovers_modules():
    rules = load_rules()
    ids = {r.id for r in rules}
    assert "admin_user_and_keys" in ids
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

`src/ks_gen/rules/admin_user_and_keys.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


def _emit(cfg: "HostConfig") -> str:
    admin = cfg.user.admin
    name = admin.name
    groups = ",".join(admin.groups)
    home = f"/home/{name}"
    keys = "\n".join(admin.authorized_keys)
    pw_block = (
        f'echo "{name}:{admin.password}" | chpasswd -e\n'
        if admin.password
        else f"passwd -l {name}\n"
    )
    sudo_line = (
        f"{name} ALL=(ALL) NOPASSWD: ALL"
        if admin.sudo == "nopasswd_yes"
        else f"{name} ALL=(ALL) ALL"
    )
    return f"""\
# Create admin user (idempotent)
if ! getent passwd {name} >/dev/null 2>&1; then
  useradd --create-home --shell {admin.shell} --groups {groups} --comment "{admin.gecos}" {name}
fi
{pw_block}
install -d -m 700 -o {name} -g {name} {home}/.ssh
cat > {home}/.ssh/authorized_keys <<'__KS_GEN_EOF__'
{keys}
__KS_GEN_EOF__
chmod 600 {home}/.ssh/authorized_keys
chown {name}:{name} {home}/.ssh/authorized_keys
restorecon -R {home}/.ssh

# Sudoers
cat > /etc/sudoers.d/00-ks-gen-admin <<'__KS_GEN_EOF__'
{sudo_line}
__KS_GEN_EOF__
chmod 440 /etc/sudoers.d/00-ks-gen-admin
visudo -cf /etc/sudoers.d/00-ks-gen-admin
"""


@dataclass(frozen=True)
class _Rule:
    id: str = "admin_user_and_keys"
    summary: str = "Create wheel admin, drop authorized_keys, sudoers fragment."
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: "HostConfig") -> bool:
        return True

    def emit_tailoring(self, cfg: "HostConfig") -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: "HostConfig") -> str:
        return _emit(cfg)

    def exception_entry(self, cfg: "HostConfig") -> ExceptionEntry | None:
        return None


RULE: Rule = _Rule()
```

Delete `src/ks_gen/rules/stub_noop.py`:
```bash
git rm src/ks_gen/rules/stub_noop.py
```

- [ ] **Step 4: Run**

```bash
.venv/Scripts/python.exe -m pytest tests/rules/test_admin_user_and_keys.py tests/test_registry.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/rules/admin_user_and_keys.py tests/rules/test_admin_user_and_keys.py tests/test_registry.py
git commit -S -m "feat(rules): admin_user_and_keys creates wheel admin with authorized_keys"
```

---

## Task 16: Rule `ssh_keep_open`

**Files:**
- Create: `src/ks_gen/rules/ssh_keep_open.py`
- Create: `tests/rules/test_ssh_keep_open.py`

- [ ] **Step 1: Failing test**

```python
from ks_gen.rules.ssh_keep_open import RULE


def test_applies_when_either_flag_set(minimal_cfg):
    assert RULE.applies(minimal_cfg)


def test_port_22_skips_semanage(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "semanage" not in out
    assert "firewall-offline-cmd --add-port=22/tcp" in out


def test_custom_port_runs_semanage(minimal_cfg):
    from ks_gen.config import Ssh
    cfg = minimal_cfg.model_copy(update={"ssh": Ssh(port=2222)})
    out = RULE.emit_post(cfg)
    assert "semanage port -a -t ssh_port_t -p tcp 2222" in out or "semanage port -m" in out
    assert "firewall-offline-cmd --add-port=2222/tcp" in out


def test_no_tailoring(minimal_cfg):
    assert RULE.emit_tailoring(minimal_cfg) == []
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

`src/ks_gen/rules/ssh_keep_open.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


def _emit(cfg: "HostConfig") -> str:
    port = cfg.ssh.port
    parts: list[str] = []
    if cfg.overrides.ssh_keep_open.ensure_selinux_port and port != 22:
        parts.append(
            f"semanage port -a -t ssh_port_t -p tcp {port} 2>/dev/null || "
            f"semanage port -m -t ssh_port_t -p tcp {port}"
        )
    if cfg.overrides.ssh_keep_open.ensure_firewalld_port:
        parts.append(f"firewall-offline-cmd --add-port={port}/tcp")
    if not parts:
        return "# ssh_keep_open: nothing to do\n"
    return "# Pre-open SSH port in firewalld + SELinux (before sshd starts on first boot)\n" + "\n".join(parts) + "\n"


@dataclass(frozen=True)
class _Rule:
    id: str = "ssh_keep_open"
    summary: str = "Ensure ssh.port reachable in firewalld + SELinux before sshd starts."
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: "HostConfig") -> bool:
        o = cfg.overrides.ssh_keep_open
        return o.ensure_firewalld_port or o.ensure_selinux_port

    def emit_tailoring(self, cfg: "HostConfig") -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: "HostConfig") -> str:
        return _emit(cfg)

    def exception_entry(self, cfg: "HostConfig") -> ExceptionEntry | None:
        return None


RULE: Rule = _Rule()
```

- [ ] **Step 4: Run** — 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/rules/ssh_keep_open.py tests/rules/test_ssh_keep_open.py
git commit -S -m "feat(rules): ssh_keep_open pre-opens firewalld and SELinux for ssh.port"
```

---

## Task 17: Rule `ssh_config_apply`

**Files:**
- Create: `src/ks_gen/rules/ssh_config_apply.py`
- Create: `tests/rules/test_ssh_config_apply.py`

- [ ] **Step 1: Failing test**

```python
from ks_gen.rules.ssh_config_apply import RULE


def test_depends_on_admin_and_keep_open(minimal_cfg):
    assert "admin_user_and_keys" in RULE.depends_on
    assert "ssh_keep_open" in RULE.depends_on


def test_post_writes_drop_in_config(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "/etc/ssh/sshd_config.d/00-ks-gen.conf" in out
    assert "Port 22" in out
    assert "PermitRootLogin no" in out
    assert "PasswordAuthentication no" in out
    assert "ClientAliveInterval 600" in out
    assert "MaxAuthTries 4" in out
    assert "UsePAM yes" in out


def test_post_validates_with_sshd_t(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "sshd -t" in out


def test_post_does_not_restart_sshd_during_install(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "systemctl restart sshd" not in out
    assert "systemctl reload sshd" not in out
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

`src/ks_gen/rules/ssh_config_apply.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


def _emit(cfg: "HostConfig") -> str:
    s = cfg.ssh
    pwd = "yes" if s.password_authentication else "no"
    pam = "yes" if s.use_pam else "no"
    return f"""\
# Drop-in SSH server config (active on first boot)
install -d -m 755 /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/00-ks-gen.conf <<'__KS_GEN_EOF__'
Port {s.port}
PermitRootLogin {s.permit_root_login}
PasswordAuthentication {pwd}
ClientAliveInterval {s.client_alive_interval}
ClientAliveCountMax {s.client_alive_count_max}
MaxAuthTries {s.max_auth_tries}
UsePAM {pam}
__KS_GEN_EOF__
chmod 600 /etc/ssh/sshd_config.d/00-ks-gen.conf
sshd -t
"""


@dataclass(frozen=True)
class _Rule:
    id: str = "ssh_config_apply"
    summary: str = "Write sshd drop-in config for Port/PermitRootLogin/PasswordAuthentication."
    depends_on: list[str] = field(
        default_factory=lambda: ["admin_user_and_keys", "ssh_keep_open"]
    )
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: "HostConfig") -> bool:
        return True

    def emit_tailoring(self, cfg: "HostConfig") -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: "HostConfig") -> str:
        return _emit(cfg)

    def exception_entry(self, cfg: "HostConfig") -> ExceptionEntry | None:
        return None


RULE: Rule = _Rule()
```

- [ ] **Step 4: Run** — 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/rules/ssh_config_apply.py tests/rules/test_ssh_config_apply.py
git commit -S -m "feat(rules): ssh_config_apply writes drop-in sshd_config.d/00-ks-gen.conf"
```

---

## Task 18: Rule `faillock_safety`

**Files:**
- Create: `src/ks_gen/rules/faillock_safety.py`
- Create: `tests/rules/test_faillock_safety.py`

- [ ] **Step 1: Failing test**

```python
from ks_gen.rules._types import TailoringOp
from ks_gen.rules.faillock_safety import RULE


def test_applies_when_enabled(minimal_cfg):
    assert RULE.applies(minimal_cfg)


def test_disabled_short_circuits(minimal_cfg):
    from ks_gen.config import FaillockCfg, Overrides
    cfg = minimal_cfg.model_copy(
        update={"overrides": Overrides(faillock=FaillockCfg(enable=False))}
    )
    assert not RULE.applies(cfg)


def test_tailoring_sets_unlock_time(minimal_cfg):
    ops = RULE.emit_tailoring(minimal_cfg)
    assert any(
        o.action == "set_value"
        and o.rule_id.endswith("var_accounts_passwords_pam_faillock_unlock_time")
        and o.value == "900"
        for o in ops
    )


def test_tailoring_disables_even_deny_root_when_false(minimal_cfg):
    ops = RULE.emit_tailoring(minimal_cfg)
    disabled = {o.rule_id for o in ops if o.action == "disable"}
    assert any("even_deny_root" in r for r in disabled)


def test_post_reasserts_unlock_time(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "unlock_time = 900" in out
    assert "/etc/security/faillock.conf" in out


def test_exception_entry_named_when_disabling_even_deny_root(minimal_cfg):
    entry = RULE.exception_entry(minimal_cfg)
    assert entry is not None
    assert "even_deny_root" in " ".join(entry.stig_rules_disabled)


def test_no_exception_when_strict(minimal_cfg):
    from ks_gen.config import FaillockCfg, Overrides
    cfg = minimal_cfg.model_copy(
        update={
            "overrides": Overrides(
                faillock=FaillockCfg(enable=True, unlock_time=0, even_deny_root=True)
            )
        }
    )
    assert RULE.exception_entry(cfg) is None
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

`src/ks_gen/rules/faillock_safety.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_PREFIX = "xccdf_org.ssgproject.content_"
_VAR_UNLOCK = f"{_PREFIX}value_var_accounts_passwords_pam_faillock_unlock_time"
_VAR_DENY = f"{_PREFIX}value_var_accounts_passwords_pam_faillock_deny"
_RULE_EVEN_DENY_ROOT = f"{_PREFIX}rule_accounts_passwords_pam_faillock_even_deny_root"


@dataclass(frozen=True)
class _Rule:
    id: str = "faillock_safety"
    summary: str = "Set faillock unlock_time and disable even_deny_root for remote safety."
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(
        default_factory=lambda: [_RULE_EVEN_DENY_ROOT]
    )

    def applies(self, cfg: "HostConfig") -> bool:
        return cfg.overrides.faillock.enable

    def emit_tailoring(self, cfg: "HostConfig") -> list[TailoringOp]:
        f = cfg.overrides.faillock
        ops: list[TailoringOp] = [
            TailoringOp(rule_id=_VAR_UNLOCK, action="set_value", value=str(f.unlock_time)),
            TailoringOp(rule_id=_VAR_DENY, action="set_value", value=str(f.deny)),
        ]
        if not f.even_deny_root:
            ops.append(TailoringOp(rule_id=_RULE_EVEN_DENY_ROOT, action="disable"))
        return ops

    def emit_post(self, cfg: "HostConfig") -> str:
        f = cfg.overrides.faillock
        even = "yes" if f.even_deny_root else "no"
        return f"""\
# Re-assert faillock.conf in case oscap over-tightened
sed -i -E 's/^[# ]*unlock_time *=.*/unlock_time = {f.unlock_time}/' /etc/security/faillock.conf
grep -q '^unlock_time' /etc/security/faillock.conf || echo 'unlock_time = {f.unlock_time}' >> /etc/security/faillock.conf
sed -i -E 's/^[# ]*deny *=.*/deny = {f.deny}/' /etc/security/faillock.conf
grep -q '^deny' /etc/security/faillock.conf || echo 'deny = {f.deny}' >> /etc/security/faillock.conf
sed -i -E 's/^[# ]*even_deny_root.*/# even_deny_root removed by ks-gen: {even}/' /etc/security/faillock.conf
"""

    def exception_entry(self, cfg: "HostConfig") -> ExceptionEntry | None:
        f = cfg.overrides.faillock
        if f.even_deny_root and f.unlock_time == 0:
            return None
        disabled = [_RULE_EVEN_DENY_ROOT] if not f.even_deny_root else []
        return ExceptionEntry(
            rule_id="faillock_safety",
            summary=f"unlock_time={f.unlock_time}, even_deny_root={f.even_deny_root}",
            stig_rules_disabled=disabled,
            reason="Prevents permanent lockout of the sole remote admin on a missed-key event.",
        )


RULE: Rule = _Rule()
```

- [ ] **Step 4: Run** — 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/rules/faillock_safety.py tests/rules/test_faillock_safety.py
git commit -S -m "feat(rules): faillock_safety with unlock_time=900 and even_deny_root override"
```

---

## Task 19: Rule `crypto_policy`

**Files:**
- Create: `src/ks_gen/rules/crypto_policy.py`
- Create: `tests/rules/test_crypto_policy.py`

- [ ] **Step 1: Failing test**

```python
from ks_gen.config import Crypto, CryptoPolicy
from ks_gen.rules.crypto_policy import RULE


def test_stig_emits_fips(minimal_cfg):
    cfg = minimal_cfg.model_copy(update={"crypto": Crypto(policy=CryptoPolicy.STIG)})
    out = RULE.emit_post(cfg)
    assert "update-crypto-policies --set FIPS" in out


def test_modern_emits_default_and_ed25519(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)  # default MODERN
    assert "update-crypto-policies --set DEFAULT" in out
    assert "ssh-keygen -A" in out


def test_modern_tailoring_disables_fips_and_approved_lists(minimal_cfg):
    ops = RULE.emit_tailoring(minimal_cfg)
    disabled = {o.rule_id for o in ops if o.action == "disable"}
    assert any("enable_fips_mode" in r for r in disabled)
    assert any("sshd_use_approved_ciphers" in r for r in disabled)
    assert any("sshd_use_approved_kex" in r for r in disabled)
    assert any("sshd_use_approved_macs" in r for r in disabled)


def test_stig_emits_no_tailoring(minimal_cfg):
    cfg = minimal_cfg.model_copy(update={"crypto": Crypto(policy=CryptoPolicy.STIG)})
    assert RULE.emit_tailoring(cfg) == []


def test_exception_entry_named_for_non_stig(minimal_cfg):
    entry = RULE.exception_entry(minimal_cfg)
    assert entry is not None
    assert "MODERN" in entry.summary


def test_no_exception_for_stig(minimal_cfg):
    cfg = minimal_cfg.model_copy(update={"crypto": Crypto(policy=CryptoPolicy.STIG)})
    assert RULE.exception_entry(cfg) is None
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

`src/ks_gen/rules/crypto_policy.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_PREFIX = "xccdf_org.ssgproject.content_rule_"
_TAILORED_WHEN_NOT_STIG = [
    f"{_PREFIX}enable_fips_mode",
    f"{_PREFIX}sshd_use_approved_ciphers",
    f"{_PREFIX}sshd_use_approved_kex",
    f"{_PREFIX}sshd_use_approved_macs",
    f"{_PREFIX}sshd_use_approved_mac_ordered",
]

_POLICY_NAME = {"STIG": "FIPS", "MODERN": "DEFAULT", "FUTURE": "FUTURE"}


@dataclass(frozen=True)
class _Rule:
    id: str = "crypto_policy"
    summary: str = "Apply system crypto-policy; optionally generate Ed25519 host keys."
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=lambda: list(_TAILORED_WHEN_NOT_STIG))

    def applies(self, cfg: "HostConfig") -> bool:
        return True

    def emit_tailoring(self, cfg: "HostConfig") -> list[TailoringOp]:
        if cfg.crypto.policy.value == "STIG":
            return []
        return [TailoringOp(rule_id=r, action="disable") for r in _TAILORED_WHEN_NOT_STIG]

    def emit_post(self, cfg: "HostConfig") -> str:
        policy = cfg.crypto.policy.value
        target = _POLICY_NAME[policy]
        lines = [
            f"# Apply system-wide crypto policy: {policy} ({target})",
            f"update-crypto-policies --set {target}",
        ]
        if policy != "STIG":
            lines.append("# Generate any missing host keys (incl. Ed25519, not produced under FIPS)")
            lines.append("ssh-keygen -A")
        return "\n".join(lines) + "\n"

    def exception_entry(self, cfg: "HostConfig") -> ExceptionEntry | None:
        if cfg.crypto.policy.value == "STIG":
            return None
        return ExceptionEntry(
            rule_id="crypto_policy",
            summary=f"{cfg.crypto.policy.value} crypto policy",
            stig_rules_disabled=list(_TAILORED_WHEN_NOT_STIG),
            reason=(
                f"{cfg.crypto.policy.value} accepts loss of FIPS 140-3 certification "
                "in exchange for Curve25519 / Ed25519 / ChaCha20-Poly1305 support."
            ),
        )


RULE: Rule = _Rule()
```

- [ ] **Step 4: Run** — 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/rules/crypto_policy.py tests/rules/test_crypto_policy.py
git commit -S -m "feat(rules): crypto_policy switches system policy and tailors FIPS-mandating rules"
```

---

## Task 20: Rule `banner_text`

**Files:**
- Create: `src/ks_gen/rules/banner_text.py`
- Create: `tests/rules/test_banner_text.py`

- [ ] **Step 1: Failing test**

```python
from ks_gen.rules.banner_text import RULE


def test_post_writes_issue_files(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "/etc/issue" in out
    assert "/etc/issue.net" in out
    assert "/etc/motd" in out
    assert "private computer system" in out


def test_tailoring_disables_banner_content_rules(minimal_cfg):
    ops = RULE.emit_tailoring(minimal_cfg)
    disabled = {o.rule_id for o in ops if o.action == "disable"}
    assert any("banner_etc_issue" in r for r in disabled)
    assert any("banner_etc_issue_net" in r for r in disabled)


def test_post_does_not_contain_dod_text(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "U.S. Government" not in out
    assert "USG" not in out


def test_exception_entry_always_present(minimal_cfg):
    assert RULE.exception_entry(minimal_cfg) is not None
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

`src/ks_gen/rules/banner_text.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_PREFIX = "xccdf_org.ssgproject.content_rule_"
_TAILORED = [
    f"{_PREFIX}banner_etc_issue",
    f"{_PREFIX}banner_etc_issue_net",
    f"{_PREFIX}dconf_gnome_banner_enabled",
]

_TARGET = {
    "issue": "/etc/issue",
    "issue_net": "/etc/issue.net",
    "motd": "/etc/motd",
}


@dataclass(frozen=True)
class _Rule:
    id: str = "banner_text"
    summary: str = "Write civilian-equivalent login banner; suppress DoD-text oscap rules."
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=lambda: list(_TAILORED))

    def applies(self, cfg: "HostConfig") -> bool:
        return True

    def emit_tailoring(self, cfg: "HostConfig") -> list[TailoringOp]:
        return [TailoringOp(rule_id=r, action="disable") for r in _TAILORED]

    def emit_post(self, cfg: "HostConfig") -> str:
        text = cfg.banner.text.rstrip("\n") + "\n"
        lines = ["# Civilian-equivalent login banner"]
        for target in cfg.banner.apply_to:
            if target == "gdm":
                continue  # GDM banner only meaningful with GUI; oscap rule above disabled
            path = _TARGET[target]
            lines.append(f"cat > {path} <<'__KS_GEN_EOF__'")
            lines.append(text.rstrip("\n"))
            lines.append("__KS_GEN_EOF__")
            lines.append(f"chmod 644 {path}")
        return "\n".join(lines) + "\n"

    def exception_entry(self, cfg: "HostConfig") -> ExceptionEntry | None:
        return ExceptionEntry(
            rule_id="banner_text",
            summary="Substitutes private-system banner for DISA-mandated DoD text.",
            stig_rules_disabled=list(_TAILORED),
            reason=(
                "Server is not a U.S. Government Information System; literal DoD banner "
                "would make false legal claims. Civilian text satisfies the rule intent "
                "(warn unauthorized users; consent to monitoring)."
            ),
        )


RULE: Rule = _Rule()
```

- [ ] **Step 4: Run** — 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/rules/banner_text.py tests/rules/test_banner_text.py
git commit -S -m "feat(rules): banner_text substitutes civilian banner for DoD text"
```

---

## Task 21: Rule `time_servers`

**Files:**
- Create: `src/ks_gen/rules/time_servers.py`
- Create: `tests/rules/test_time_servers.py`

- [ ] **Step 1: Failing test**

```python
from ks_gen.rules.time_servers import RULE


def test_post_writes_chrony_conf(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "/etc/chrony.conf" in out
    assert "server pool.ntp.org iburst" in out


def test_post_handles_multiple_servers(minimal_cfg):
    from ks_gen.config import Time
    cfg = minimal_cfg.model_copy(update={"time": Time(servers=["a.example", "b.example"])})
    out = RULE.emit_post(cfg)
    assert "server a.example iburst" in out
    assert "server b.example iburst" in out


def test_no_dod_servers_in_output(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "usno" not in out.lower()
    assert "navy.mil" not in out.lower()
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

`src/ks_gen/rules/time_servers.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


@dataclass(frozen=True)
class _Rule:
    id: str = "time_servers"
    summary: str = "Write chrony.conf with operator-chosen NTP servers (non-DoD by default)."
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: "HostConfig") -> bool:
        return True

    def emit_tailoring(self, cfg: "HostConfig") -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: "HostConfig") -> str:
        servers = "\n".join(f"server {s} iburst" for s in cfg.time.servers)
        thresh = cfg.time.chrony_makestep_threshold
        return f"""\
# Chrony configuration (servers from host.yaml; STIG-compliant base)
cat > /etc/chrony.conf <<'__KS_GEN_EOF__'
{servers}
driftfile /var/lib/chrony/drift
makestep {thresh} 3
rtcsync
logdir /var/log/chrony
__KS_GEN_EOF__
chmod 644 /etc/chrony.conf
"""

    def exception_entry(self, cfg: "HostConfig") -> ExceptionEntry | None:
        return None


RULE: Rule = _Rule()
```

- [ ] **Step 4: Run** — 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/rules/time_servers.py tests/rules/test_time_servers.py
git commit -S -m "feat(rules): time_servers writes chrony.conf from host.yaml time.servers"
```

---

## Task 22: Rule `dod_root_ca`

**Files:**
- Create: `src/ks_gen/rules/dod_root_ca.py`
- Create: `tests/rules/test_dod_root_ca.py`

- [ ] **Step 1: Failing test**

```python
from ks_gen.config import DodRootCaCfg, Overrides
from ks_gen.rules.dod_root_ca import RULE


def test_applies_only_when_install_false(minimal_cfg):
    assert RULE.applies(minimal_cfg)  # default False -> applies (we tailor it out)
    on = minimal_cfg.model_copy(
        update={"overrides": Overrides(dod_root_ca=DodRootCaCfg(install=True))}
    )
    assert not RULE.applies(on)


def test_tailoring_disables_dod_ca_rule(minimal_cfg):
    ops = RULE.emit_tailoring(minimal_cfg)
    assert ops
    assert all(o.action == "disable" for o in ops)
    assert any("dod" in o.rule_id.lower() for o in ops)


def test_post_is_empty(minimal_cfg):
    assert RULE.emit_post(minimal_cfg).strip() == ""


def test_exception_entry_when_disabled(minimal_cfg):
    entry = RULE.exception_entry(minimal_cfg)
    assert entry is not None
    assert "DoD" in entry.summary
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

`src/ks_gen/rules/dod_root_ca.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_RULE_ID = "xccdf_org.ssgproject.content_rule_install_DoD_intermediate_certificates"


@dataclass(frozen=True)
class _Rule:
    id: str = "dod_root_ca"
    summary: str = "Skip DoD root CA bundle installation."
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=lambda: [_RULE_ID])

    def applies(self, cfg: "HostConfig") -> bool:
        return not cfg.overrides.dod_root_ca.install

    def emit_tailoring(self, cfg: "HostConfig") -> list[TailoringOp]:
        return [TailoringOp(rule_id=_RULE_ID, action="disable")]

    def emit_post(self, cfg: "HostConfig") -> str:
        return ""

    def exception_entry(self, cfg: "HostConfig") -> ExceptionEntry | None:
        return ExceptionEntry(
            rule_id="dod_root_ca",
            summary="DoD root/intermediate CA bundle not installed.",
            stig_rules_disabled=[_RULE_ID],
            reason="Server is not a DoD asset; bundle is not applicable.",
        )


RULE: Rule = _Rule()
```

- [ ] **Step 4: Run** — 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/rules/dod_root_ca.py tests/rules/test_dod_root_ca.py
git commit -S -m "feat(rules): dod_root_ca tailors out DoD certificate bundle"
```

---

## Task 23: Rule `auditd_actions`

**Files:**
- Create: `src/ks_gen/rules/auditd_actions.py`
- Create: `tests/rules/test_auditd_actions.py`

- [ ] **Step 1: Failing test**

```python
from ks_gen.config import (
    AuditdActionsCfg,
    AuditdMaxFileAction,
    AuditdSystemAction,
    Overrides,
)
from ks_gen.rules.auditd_actions import RULE


def test_tailoring_uses_default_actions(minimal_cfg):
    ops = RULE.emit_tailoring(minimal_cfg)
    values = {o.rule_id: o.value for o in ops if o.action == "set_value"}
    assert any("disk_full_action" in k for k in values)
    assert "SUSPEND" in values.get(
        "xccdf_org.ssgproject.content_value_var_auditd_disk_full_action", ""
    )


def test_post_reasserts_auditd_conf(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "/etc/audit/auditd.conf" in out
    assert "disk_full_action = SUSPEND" in out
    assert "max_log_file_action = ROTATE" in out


def test_exception_when_actions_not_stig_default(minimal_cfg):
    assert RULE.exception_entry(minimal_cfg) is not None


def test_no_exception_when_strict_halt(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={
            "overrides": Overrides(
                auditd=AuditdActionsCfg(
                    disk_full_action=AuditdSystemAction.HALT,
                    disk_error_action=AuditdSystemAction.HALT,
                    max_log_file_action=AuditdMaxFileAction.KEEP_LOGS,
                )
            )
        }
    )
    assert RULE.exception_entry(cfg) is None
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

`src/ks_gen/rules/auditd_actions.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_PREFIX = "xccdf_org.ssgproject.content_value_"
_VAR_DISK_FULL = f"{_PREFIX}var_auditd_disk_full_action"
_VAR_DISK_ERROR = f"{_PREFIX}var_auditd_disk_error_action"
_VAR_MAX_LOG = f"{_PREFIX}var_auditd_max_log_file_action"


@dataclass(frozen=True)
class _Rule:
    id: str = "auditd_actions"
    summary: str = "auditd disk_full/disk_error/max_log_file actions (SUSPEND/ROTATE default)."
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: "HostConfig") -> bool:
        return True

    def emit_tailoring(self, cfg: "HostConfig") -> list[TailoringOp]:
        a = cfg.overrides.auditd
        return [
            TailoringOp(rule_id=_VAR_DISK_FULL, action="set_value", value=a.disk_full_action.value),
            TailoringOp(rule_id=_VAR_DISK_ERROR, action="set_value", value=a.disk_error_action.value),
            TailoringOp(rule_id=_VAR_MAX_LOG, action="set_value", value=a.max_log_file_action.value),
        ]

    def emit_post(self, cfg: "HostConfig") -> str:
        a = cfg.overrides.auditd
        return f"""\
# Re-assert auditd actions
sed -i -E 's|^disk_full_action.*|disk_full_action = {a.disk_full_action.value}|' /etc/audit/auditd.conf
sed -i -E 's|^disk_error_action.*|disk_error_action = {a.disk_error_action.value}|' /etc/audit/auditd.conf
sed -i -E 's|^max_log_file_action.*|max_log_file_action = {a.max_log_file_action.value}|' /etc/audit/auditd.conf
"""

    def exception_entry(self, cfg: "HostConfig") -> ExceptionEntry | None:
        a = cfg.overrides.auditd
        strict = (
            a.disk_full_action.value == "HALT"
            and a.disk_error_action.value == "HALT"
            and a.max_log_file_action.value == "keep_logs"
        )
        if strict:
            return None
        return ExceptionEntry(
            rule_id="auditd_actions",
            summary=(
                f"disk_full={a.disk_full_action.value}, "
                f"disk_error={a.disk_error_action.value}, "
                f"max_log_file={a.max_log_file_action.value}"
            ),
            stig_rules_disabled=[],
            reason=(
                "STIG defaults (HALT / keep_logs) can kill a remote server on a log-volume "
                "spike. SUSPEND/ROTATE keeps audit semantics while keeping the box reachable."
            ),
        )


RULE: Rule = _Rule()
```

- [ ] **Step 4: Run** — 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/rules/auditd_actions.py tests/rules/test_auditd_actions.py
git commit -S -m "feat(rules): auditd_actions overrides HALT/keep_logs with SUSPEND/ROTATE"
```

---

## Task 24: Rule `usbguard`

**Files:**
- Create: `src/ks_gen/rules/usbguard.py`
- Create: `tests/rules/test_usbguard.py`

- [ ] **Step 1: Failing test**

```python
from ks_gen.config import Overrides, UsbguardCfg
from ks_gen.rules.usbguard import RULE


def test_disabled_tailoring_disables_oscap_rules(minimal_cfg):
    ops = RULE.emit_tailoring(minimal_cfg)
    disabled = {o.rule_id for o in ops if o.action == "disable"}
    assert any("usbguard" in r for r in disabled)


def test_enabled_tailoring_selects_oscap_rules(minimal_cfg):
    cfg = minimal_cfg.model_copy(
        update={"overrides": Overrides(usbguard=UsbguardCfg(enable=True))}
    )
    ops = RULE.emit_tailoring(cfg)
    selected = {o.rule_id for o in ops if o.action == "select"}
    assert any("usbguard" in r for r in selected)


def test_exception_entry_only_when_disabled(minimal_cfg):
    assert RULE.exception_entry(minimal_cfg) is not None  # default disabled
    cfg = minimal_cfg.model_copy(
        update={"overrides": Overrides(usbguard=UsbguardCfg(enable=True))}
    )
    assert RULE.exception_entry(cfg) is None
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

`src/ks_gen/rules/usbguard.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_PREFIX = "xccdf_org.ssgproject.content_rule_"
_USBGUARD_RULES = [
    f"{_PREFIX}package_usbguard_installed",
    f"{_PREFIX}service_usbguard_enabled",
    f"{_PREFIX}configure_usbguard_auditbackend",
]


@dataclass(frozen=True)
class _Rule:
    id: str = "usbguard"
    summary: str = "Enable or disable USBGuard install + service per overrides."
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=lambda: list(_USBGUARD_RULES))

    def applies(self, cfg: "HostConfig") -> bool:
        return True

    def emit_tailoring(self, cfg: "HostConfig") -> list[TailoringOp]:
        action = "select" if cfg.overrides.usbguard.enable else "disable"
        return [TailoringOp(rule_id=r, action=action) for r in _USBGUARD_RULES]

    def emit_post(self, cfg: "HostConfig") -> str:
        return ""

    def exception_entry(self, cfg: "HostConfig") -> ExceptionEntry | None:
        if cfg.overrides.usbguard.enable:
            return None
        return ExceptionEntry(
            rule_id="usbguard",
            summary="USBGuard not installed/enabled.",
            stig_rules_disabled=list(_USBGUARD_RULES),
            reason=(
                "Cloud/headless VMs have no USB; USBGuard is overhead with no benefit. "
                "Enable explicitly on bare-metal hosts."
            ),
        )


RULE: Rule = _Rule()
```

- [ ] **Step 4: Run** — 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/rules/usbguard.py tests/rules/test_usbguard.py
git commit -S -m "feat(rules): usbguard toggles install/service per overrides.usbguard.enable"
```

---

## Task 25: Rule `kernel_module_blacklist`

**Files:**
- Create: `src/ks_gen/rules/kernel_module_blacklist.py`
- Create: `tests/rules/test_kernel_module_blacklist.py`

- [ ] **Step 1: Failing test**

```python
from ks_gen.rules.kernel_module_blacklist import RULE


def test_post_writes_modprobe_conf(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "/etc/modprobe.d/ks-gen-blacklist.conf" in out
    assert "install usb-storage /bin/true" in out
    assert "install squashfs /bin/true" in out


def test_does_not_apply_when_disabled(minimal_cfg):
    from ks_gen.config import KernelModuleBlacklistCfg, Overrides
    cfg = minimal_cfg.model_copy(
        update={
            "overrides": Overrides(
                kernel_module_blacklist=KernelModuleBlacklistCfg(enable=False)
            )
        }
    )
    assert not RULE.applies(cfg)
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

`src/ks_gen/rules/kernel_module_blacklist.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


@dataclass(frozen=True)
class _Rule:
    id: str = "kernel_module_blacklist"
    summary: str = "Write modprobe blacklist for unused/disallowed kernel modules."
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: "HostConfig") -> bool:
        return cfg.overrides.kernel_module_blacklist.enable

    def emit_tailoring(self, cfg: "HostConfig") -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: "HostConfig") -> str:
        modules = cfg.overrides.kernel_module_blacklist.modules
        body = "\n".join(f"install {m} /bin/true" for m in modules)
        return f"""\
# Disable specific kernel modules via modprobe install-trick
cat > /etc/modprobe.d/ks-gen-blacklist.conf <<'__KS_GEN_EOF__'
{body}
__KS_GEN_EOF__
chmod 644 /etc/modprobe.d/ks-gen-blacklist.conf
"""

    def exception_entry(self, cfg: "HostConfig") -> ExceptionEntry | None:
        return None


RULE: Rule = _Rule()
```

- [ ] **Step 4: Run** — 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/rules/kernel_module_blacklist.py tests/rules/test_kernel_module_blacklist.py
git commit -S -m "feat(rules): kernel_module_blacklist writes modprobe.d/ks-gen-blacklist.conf"
```

---

## Task 26: Rule `package_purge`

**Files:**
- Create: `src/ks_gen/rules/package_purge.py`
- Create: `tests/rules/test_package_purge.py`

- [ ] **Step 1: Failing test**

```python
from ks_gen.rules.package_purge import RULE


def test_post_removes_excluded_packages(minimal_cfg):
    out = RULE.emit_post(minimal_cfg)
    assert "dnf -y remove" in out
    assert "telnet-server" in out
    assert "rsh-server" in out


def test_does_not_apply_when_excluded_is_empty(minimal_cfg):
    from ks_gen.config import Packages
    cfg = minimal_cfg.model_copy(update={"packages": Packages(excluded=[])})
    assert not RULE.applies(cfg)
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

`src/ks_gen/rules/package_purge.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


@dataclass(frozen=True)
class _Rule:
    id: str = "package_purge"
    summary: str = "Remove disallowed packages after install (catches transitive pulls)."
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: "HostConfig") -> bool:
        return cfg.overrides.package_purge.enable and bool(cfg.packages.excluded)

    def emit_tailoring(self, cfg: "HostConfig") -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: "HostConfig") -> str:
        pkgs = " ".join(cfg.packages.excluded)
        return f"# Remove disallowed packages (no-op if not installed)\ndnf -y remove {pkgs} || true\n"

    def exception_entry(self, cfg: "HostConfig") -> ExceptionEntry | None:
        return None


RULE: Rule = _Rule()
```

- [ ] **Step 4: Run** — 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/rules/package_purge.py tests/rules/test_package_purge.py
git commit -S -m "feat(rules): package_purge removes excluded packages post-install"
```

---

## Task 27: Output writer (4-file bundle)

Wires everything: load rules → topo sort → render skeleton with `PostBlock`s → build tailoring → write all four files.

**Files:**
- Create: `src/ks_gen/writer.py`
- Create: `tests/test_writer.py`

- [ ] **Step 1: Failing test**

```python
import textwrap

from ks_gen.loader import load_host_config
from ks_gen.writer import build_bundle, write_bundle


YAML = textwrap.dedent(
    """\
    system: {hostname: web01.example.com}
    user:
      admin:
        name: opsadmin
        authorized_keys: ["ssh-ed25519 AAAA a@b"]
    """
)


def test_build_bundle_returns_four_artifacts(tmp_path):
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(YAML, encoding="utf-8")
    cfg = load_host_config(cfg_path, sets=[])
    bundle = build_bundle(cfg)
    assert "%post" in bundle.ks_cfg
    assert "<xccdf:Tailoring" in bundle.tailoring_xml
    assert "MODERN" in bundle.exceptions_md or "MODERN" in bundle.ks_cfg
    assert bundle.host_yaml.startswith("meta:") or "system:" in bundle.host_yaml


def test_write_bundle_creates_files(tmp_path):
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(YAML, encoding="utf-8")
    cfg = load_host_config(cfg_path, sets=[])
    bundle = build_bundle(cfg)
    out = tmp_path / "out"
    write_bundle(bundle, out)
    for name in ("ks.cfg", "tailoring.xml", "host.yaml", "exceptions.md"):
        assert (out / name).is_file()


def test_admin_user_block_precedes_sshd_in_post(tmp_path):
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(YAML, encoding="utf-8")
    cfg = load_host_config(cfg_path, sets=[])
    bundle = build_bundle(cfg)
    admin_idx = bundle.ks_cfg.find("# ===== admin_user_and_keys =====")
    ssh_idx = bundle.ks_cfg.find("# ===== ssh_config_apply =====")
    assert admin_idx != -1 and ssh_idx != -1
    assert admin_idx < ssh_idx
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

`src/ks_gen/writer.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from ks_gen.config import HostConfig
from ks_gen.exceptions_report import render_exceptions_md
from ks_gen.registry import load_rules
from ks_gen.skeleton import PostBlock, render_skeleton
from ks_gen.tailoring import build_tailoring_xml
from ks_gen.topo import topo_sort


@dataclass(frozen=True)
class Bundle:
    ks_cfg: str
    tailoring_xml: str
    host_yaml: str
    exceptions_md: str


def build_bundle(cfg: HostConfig) -> Bundle:
    rules = topo_sort(load_rules())
    applicable = [r for r in rules if r.applies(cfg)]

    post_blocks: list[PostBlock] = []
    tailoring_ops = []
    for r in applicable:
        body = r.emit_post(cfg).rstrip()
        if body:
            post_blocks.append(PostBlock(rule_id=r.id, body=body))
        tailoring_ops.extend(r.emit_tailoring(cfg))

    profile_id = f"xccdf_org.ssgproject.content_profile_{cfg.meta.profile}"
    tailoring_xml = build_tailoring_xml(tailoring_ops, profile_id=profile_id)
    ks_cfg = render_skeleton(cfg, post_blocks=list(post_blocks))
    host_yaml = yaml.safe_dump(
        cfg.model_dump(mode="json"), sort_keys=False, default_flow_style=False
    )
    exceptions_md = render_exceptions_md(cfg, applicable)
    return Bundle(
        ks_cfg=ks_cfg,
        tailoring_xml=tailoring_xml,
        host_yaml=host_yaml,
        exceptions_md=exceptions_md,
    )


def write_bundle(bundle: Bundle, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ks.cfg").write_text(bundle.ks_cfg, encoding="utf-8", newline="\n")
    (out_dir / "tailoring.xml").write_text(
        bundle.tailoring_xml, encoding="utf-8", newline="\n"
    )
    (out_dir / "host.yaml").write_text(bundle.host_yaml, encoding="utf-8", newline="\n")
    (out_dir / "exceptions.md").write_text(
        bundle.exceptions_md, encoding="utf-8", newline="\n"
    )
```

(Note: `exceptions_report.py` doesn't exist yet — Task 28 creates it. Tests in this task will fail at import until Task 28 lands. Either stub it now and complete in Task 28, or do Task 28 before re-running the writer tests. Recommended: write the minimal stub here, then flesh it out in Task 28.)

Minimal stub `src/ks_gen/exceptions_report.py`:
```python
from __future__ import annotations

from collections.abc import Iterable

from ks_gen.config import HostConfig
from ks_gen.rules._types import Rule


def render_exceptions_md(cfg: HostConfig, rules: Iterable[Rule]) -> str:
    return "# Exceptions report\n\n(stub; expanded in Task 28)\n"
```

- [ ] **Step 4: Run** — 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/writer.py src/ks_gen/exceptions_report.py tests/test_writer.py
git commit -S -m "feat(writer): build and write the 4-file output bundle"
```

---

## Task 28: `exceptions_report` — generate `exceptions.md`

**Files:**
- Modify: `src/ks_gen/exceptions_report.py`
- Create: `tests/test_exceptions_report.py`

- [ ] **Step 1: Failing test**

```python
from ks_gen.exceptions_report import render_exceptions_md
from ks_gen.registry import load_rules
from ks_gen.topo import topo_sort


def test_report_lists_applied_rules(minimal_cfg):
    rules = [r for r in topo_sort(load_rules()) if r.applies(minimal_cfg)]
    md = render_exceptions_md(minimal_cfg, rules)
    assert "# Exceptions report" in md
    assert "admin_user_and_keys" in md
    assert "crypto_policy" in md


def test_report_lists_disabled_xccdf_rules(minimal_cfg):
    rules = [r for r in topo_sort(load_rules()) if r.applies(minimal_cfg)]
    md = render_exceptions_md(minimal_cfg, rules)
    assert "banner_etc_issue" in md
    assert "sshd_use_approved_ciphers" in md


def test_report_includes_declared_exceptions(minimal_cfg):
    from ks_gen.config import ExceptionDecl
    cfg = minimal_cfg.model_copy(
        update={
            "exceptions": [
                ExceptionDecl(
                    id="no-luks",
                    reason="Cloud volumes encrypted by provider.",
                    stig_rules_disabled=[
                        "xccdf_org.ssgproject.content_rule_encrypt_partitions"
                    ],
                )
            ]
        }
    )
    rules = [r for r in topo_sort(load_rules()) if r.applies(cfg)]
    md = render_exceptions_md(cfg, rules)
    assert "no-luks" in md
    assert "encrypt_partitions" in md


def test_report_counts_summary(minimal_cfg):
    rules = [r for r in topo_sort(load_rules()) if r.applies(minimal_cfg)]
    md = render_exceptions_md(minimal_cfg, rules)
    assert "Applied rules:" in md
    assert "Tailored XCCDF rules:" in md
    assert "Declared exceptions:" in md
```

- [ ] **Step 2: Run — fail (stub returns nothing useful)**

- [ ] **Step 3: Implement**

`src/ks_gen/exceptions_report.py`:
```python
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone

from ks_gen.config import HostConfig
from ks_gen.rules._types import Rule


def render_exceptions_md(cfg: HostConfig, rules: Iterable[Rule]) -> str:
    rules = list(rules)
    entries = [(r, r.exception_entry(cfg)) for r in rules]
    disabled_xccdf: list[tuple[str, str]] = []
    for r, entry in entries:
        if entry is None:
            continue
        for rid in entry.stig_rules_disabled:
            disabled_xccdf.append((rid, r.id))

    lines: list[str] = []
    lines.append("# Exceptions report")
    lines.append("")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
    lines.append(f"Host: `{cfg.system.hostname}`")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- Applied rules: {len(rules)}")
    lines.append(f"- Tailored XCCDF rules: {len(disabled_xccdf)}")
    lines.append(f"- Declared exceptions: {len(cfg.exceptions)}")
    lines.append("")

    lines.append("## Applied rules")
    for r in rules:
        lines.append(f"- `{r.id}` — {r.summary}")
    lines.append("")

    lines.append("## Tailored XCCDF rules (oscap rules disabled or value-tailored)")
    if not disabled_xccdf:
        lines.append("_(none)_")
    else:
        lines.append("| XCCDF rule | Tailored by |")
        lines.append("|---|---|")
        for rid, owner in disabled_xccdf:
            lines.append(f"| `{rid}` | `{owner}` |")
    lines.append("")

    lines.append("## Rule exception details")
    for r, entry in entries:
        if entry is None:
            continue
        lines.append(f"### `{entry.rule_id}` — {entry.summary}")
        lines.append("")
        if entry.reason:
            lines.append(f"_Reason:_ {entry.reason}")
            lines.append("")
        if entry.stig_rules_disabled:
            lines.append("Disabled XCCDF rules:")
            for rid in entry.stig_rules_disabled:
                lines.append(f"- `{rid}`")
            lines.append("")

    lines.append("## Declared exceptions (from host.yaml)")
    if not cfg.exceptions:
        lines.append("_(none)_")
    else:
        for ex in cfg.exceptions:
            lines.append(f"### `{ex.id}`")
            lines.append("")
            lines.append(f"_Reason:_ {ex.reason}")
            lines.append("")
            lines.append("Disabled XCCDF rules:")
            for rid in ex.stig_rules_disabled:
                lines.append(f"- `{rid}`")
            lines.append("")

    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run** — 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/exceptions_report.py tests/test_exceptions_report.py
git commit -S -m "feat(exceptions): render audit-grade exceptions.md from rule entries"
```

---

## Task 29: Invariant tests (load-bearing safety properties)

**Files:**
- Create: `tests/test_invariants.py`

- [ ] **Step 1: Write tests**

```python
from __future__ import annotations

import itertools
import re

import pytest

from ks_gen.config import (
    AdminUser,
    Crypto,
    CryptoPolicy,
    HostConfig,
    Overrides,
    Ssh,
    System,
    UsbguardCfg,
    User,
)
from ks_gen.writer import build_bundle


def _cfg(**overrides_kwargs):
    overrides_obj = Overrides(**overrides_kwargs) if overrides_kwargs else None
    base = dict(
        system=System(hostname="x.example"),
        user=User(admin=AdminUser(name="ops", authorized_keys=["ssh-ed25519 A a@b"])),
    )
    if overrides_obj is not None:
        base["overrides"] = overrides_obj
    return HostConfig(**base)


def _fuzz_configs():
    yield _cfg()
    yield _cfg(usbguard=UsbguardCfg(enable=True))
    for port in (22, 2222):
        for pw in (True, False):
            yield HostConfig(
                system=System(hostname="x"),
                user=User(
                    admin=AdminUser(name="ops", authorized_keys=["ssh-ed25519 A a@b"])
                ),
                ssh=Ssh(port=port, password_authentication=pw),
            )
    for policy in CryptoPolicy:
        yield HostConfig(
            system=System(hostname="x"),
            user=User(admin=AdminUser(name="ops", authorized_keys=["ssh-ed25519 A a@b"])),
            crypto=Crypto(policy=policy),
        )


@pytest.mark.parametrize("cfg", list(_fuzz_configs()))
def test_authorized_keys_always_before_sshd_touches(cfg):
    ks = build_bundle(cfg).ks_cfg
    keys_idx = ks.find("authorized_keys")
    sshd_idx = ks.find("sshd_config.d/00-ks-gen.conf")
    assert keys_idx != -1, "authorized_keys must be written in %post"
    assert sshd_idx != -1, "sshd drop-in must be written in %post"
    assert keys_idx < sshd_idx, (
        "lockout-resistance invariant: authorized_keys must precede sshd config"
    )


@pytest.mark.parametrize("cfg", list(_fuzz_configs()))
def test_ssh_port_opened_in_firewalld_before_any_firewalld_enable_command(cfg):
    ks = build_bundle(cfg).ks_cfg
    port_idx = ks.find(f"--add-port={cfg.ssh.port}/tcp")
    enable_idx = re.search(r"systemctl\s+(enable|start)\s+firewalld", ks)
    assert port_idx != -1, "ssh.port must be added to firewalld in %post"
    if enable_idx:
        assert port_idx < enable_idx.start()


@pytest.mark.parametrize("cfg", list(_fuzz_configs()))
def test_no_disabled_xccdf_rule_without_exception_entry(cfg):
    from ks_gen.registry import load_rules

    for r in load_rules():
        if not r.applies(cfg):
            continue
        ops = r.emit_tailoring(cfg)
        disabled = [o.rule_id for o in ops if o.action == "disable"]
        if not disabled:
            continue
        entry = r.exception_entry(cfg)
        assert entry is not None, (
            f"rule {r.id} disabled XCCDF rules {disabled} without an exception_entry"
        )
        for rid in disabled:
            assert rid in entry.stig_rules_disabled, (
                f"rule {r.id} disabled {rid} but didn't name it in exception_entry"
            )
```

- [ ] **Step 2: Run** — all parametrized cases pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_invariants.py
git commit -S -m "test(invariants): lockout-resistance, firewall ordering, no silent drift"
```

---

## Task 30: `gen` CLI subcommand

**Files:**
- Create: `src/ks_gen/cli.py`
- Create: `tests/test_cli/__init__.py`
- Create: `tests/test_cli/test_gen.py`

- [ ] **Step 1: Failing test**

```python
import textwrap

from typer.testing import CliRunner

from ks_gen.cli import app


YAML = textwrap.dedent(
    """\
    system: {hostname: web01.example.com}
    user:
      admin:
        name: opsadmin
        authorized_keys: ["ssh-ed25519 AAAA a@b"]
    """
)


def test_gen_writes_bundle(tmp_path):
    runner = CliRunner()
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(YAML, encoding="utf-8")
    out_dir = tmp_path / "out"
    result = runner.invoke(app, ["gen", "--config", str(cfg_path), "--out", str(out_dir)])
    assert result.exit_code == 0, result.output
    for name in ("ks.cfg", "tailoring.xml", "host.yaml", "exceptions.md"):
        assert (out_dir / name).is_file()


def test_gen_set_override_applies(tmp_path):
    runner = CliRunner()
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(YAML, encoding="utf-8")
    out_dir = tmp_path / "out"
    result = runner.invoke(
        app,
        ["gen", "--config", str(cfg_path), "--out", str(out_dir), "--set", "ssh.port=2222"],
    )
    assert result.exit_code == 0
    assert "Port 2222" in (out_dir / "ks.cfg").read_text()


def test_gen_fips_conflict_returns_3(tmp_path):
    runner = CliRunner()
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(YAML, encoding="utf-8")
    out_dir = tmp_path / "out"
    result = runner.invoke(
        app,
        [
            "gen",
            "--config", str(cfg_path),
            "--out", str(out_dir),
            "--set", "overrides.fips_mode=true",
        ],
    )
    assert result.exit_code == 3, result.output
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement minimal CLI with `gen`**

`src/ks_gen/cli.py`:
```python
from __future__ import annotations

from pathlib import Path

import typer

from ks_gen.loader import ConfigError, ExitCode, load_host_config
from ks_gen.writer import build_bundle, write_bundle


app = typer.Typer(add_completion=False, no_args_is_help=True, help="ks-gen — DISA STIG AlmaLinux kickstart generator")


@app.command(help="Render ks.cfg + tailoring.xml + exceptions.md + host.yaml from a config.")
def gen(
    config: Path = typer.Option(..., "--config", "-c", exists=True, dir_okay=False, readable=True),
    out: Path = typer.Option(..., "--out", "-o", file_okay=False),
    set_: list[str] = typer.Option([], "--set", help="Dotted-path overrides, KEY=VALUE."),
) -> None:
    try:
        cfg = load_host_config(config, sets=set_)
    except ConfigError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=int(e.exit_code))
    bundle = build_bundle(cfg)
    write_bundle(bundle, out)
    typer.echo(f"Wrote bundle to {out}")


if __name__ == "__main__":
    app()
```

Create empty `tests/test_cli/__init__.py`.

- [ ] **Step 4: Run** — 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/cli.py tests/test_cli/__init__.py tests/test_cli/test_gen.py
git commit -S -m "feat(cli): gen subcommand wires loader -> writer -> bundle"
```

---

## Task 31: `lint.py` — ksvalidator + internal invariant re-parse

**Files:**
- Create: `src/ks_gen/lint.py`
- Create: `tests/test_lint.py`

- [ ] **Step 1: Failing test**

```python
import textwrap
from pathlib import Path

from ks_gen.lint import LintReport, lint_kickstart
from ks_gen.loader import load_host_config
from ks_gen.writer import build_bundle, write_bundle


YAML = textwrap.dedent(
    """\
    system: {hostname: web01.example.com}
    user:
      admin:
        name: opsadmin
        authorized_keys: ["ssh-ed25519 AAAA a@b"]
    """
)


def _generate(tmp_path) -> Path:
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(YAML, encoding="utf-8")
    cfg = load_host_config(cfg_path, sets=[])
    bundle = build_bundle(cfg)
    out = tmp_path / "out"
    write_bundle(bundle, out)
    return out


def test_lint_accepts_known_good(tmp_path):
    out = _generate(tmp_path)
    report = lint_kickstart(out / "ks.cfg")
    assert report.ok, report.failures


def test_lint_detects_missing_authorized_keys(tmp_path):
    out = _generate(tmp_path)
    ks = out / "ks.cfg"
    text = ks.read_text(encoding="utf-8").replace(".ssh/authorized_keys", ".ssh/DISARMED")
    ks.write_text(text, encoding="utf-8")
    report = lint_kickstart(ks)
    assert not report.ok
    assert any("authorized_keys" in f for f in report.failures)


def test_lint_detects_sshd_before_admin(tmp_path):
    out = _generate(tmp_path)
    ks = out / "ks.cfg"
    text = ks.read_text(encoding="utf-8")
    # Swap order: cut admin block, paste after sshd block
    admin_marker = "# ===== admin_user_and_keys ====="
    sshd_marker = "# ===== ssh_config_apply ====="
    a = text.index(admin_marker)
    b = text.index(sshd_marker)
    text = text[:a] + text[b:b+200] + text[a:b] + text[b+200:]
    ks.write_text(text, encoding="utf-8")
    report = lint_kickstart(ks)
    assert not report.ok
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

`src/ks_gen/lint.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LintReport:
    ok: bool
    failures: list[str] = field(default_factory=list)


def _ksvalidator_ok(path: Path) -> tuple[bool, str]:
    try:
        from pykickstart.parser import KickstartParser
        from pykickstart.version import makeVersion
    except ImportError as e:
        return False, f"pykickstart unavailable: {e}"
    try:
        parser = KickstartParser(makeVersion())
        parser.readKickstart(str(path))
        return True, ""
    except Exception as e:  # noqa: BLE001 — pykickstart raises broad exceptions
        return False, f"ksvalidator: {e}"


def _internal_checks(text: str) -> list[str]:
    failures: list[str] = []
    if "authorized_keys" not in text:
        failures.append("missing: authorized_keys write in %post")
    a = text.find("# ===== admin_user_and_keys =====")
    s = text.find("# ===== ssh_config_apply =====")
    if a == -1:
        failures.append("missing: admin_user_and_keys post block")
    if s == -1:
        failures.append("missing: ssh_config_apply post block")
    if a != -1 and s != -1 and a >= s:
        failures.append("ordering: admin_user_and_keys must precede ssh_config_apply")
    if "tailoring-path = /tailoring.xml" not in text:
        failures.append("missing: %addon does not reference tailoring.xml")
    return failures


def lint_kickstart(path: Path) -> LintReport:
    text = Path(path).read_text(encoding="utf-8")
    ok, msg = _ksvalidator_ok(path)
    failures = [] if ok else [msg]
    failures.extend(_internal_checks(text))
    return LintReport(ok=not failures, failures=failures)
```

- [ ] **Step 4: Run** — 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/lint.py tests/test_lint.py
git commit -S -m "feat(lint): ksvalidator + internal re-parse invariant checks"
```

---

## Task 32: `lint` CLI subcommand + auto-lint after `gen`

**Files:**
- Modify: `src/ks_gen/cli.py`
- Create: `tests/test_cli/test_lint.py`

- [ ] **Step 1: Failing test**

```python
import textwrap

from typer.testing import CliRunner

from ks_gen.cli import app


def test_lint_subcommand_passes_on_generated_ks(tmp_path):
    runner = CliRunner()
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(
        textwrap.dedent(
            """\
            system: {hostname: x}
            user:
              admin:
                name: ops
                authorized_keys: ["ssh-ed25519 A a@b"]
            """
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"
    assert runner.invoke(app, ["gen", "-c", str(cfg_path), "-o", str(out_dir)]).exit_code == 0
    result = runner.invoke(app, ["lint", str(out_dir / "ks.cfg")])
    assert result.exit_code == 0, result.output


def test_lint_fails_on_garbage(tmp_path):
    runner = CliRunner()
    bad = tmp_path / "bad.cfg"
    bad.write_text("this is not a kickstart", encoding="utf-8")
    result = runner.invoke(app, ["lint", str(bad)])
    assert result.exit_code == 4
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Extend `cli.py`**

Append:
```python
from ks_gen.lint import lint_kickstart


@app.command(name="lint", help="Validate a generated ks.cfg.")
def lint_cmd(ks_path: Path = typer.Argument(..., exists=True, dir_okay=False)) -> None:
    report = lint_kickstart(ks_path)
    if report.ok:
        typer.echo("OK")
        return
    for f in report.failures:
        typer.echo(f"FAIL: {f}", err=True)
    raise typer.Exit(code=int(ExitCode.LINT_FAIL))
```

And in `gen`, after `write_bundle`, run lint automatically:
```python
    from ks_gen.lint import lint_kickstart
    report = lint_kickstart(out / "ks.cfg")
    if not report.ok:
        for f in report.failures:
            typer.echo(f"lint FAIL: {f}", err=True)
        raise typer.Exit(code=int(ExitCode.LINT_FAIL))
```

- [ ] **Step 4: Run** — 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/cli.py tests/test_cli/test_lint.py
git commit -S -m "feat(cli): lint subcommand; gen auto-runs lint after writing"
```

---

## Task 33: `rules` CLI subcommand

**Files:**
- Modify: `src/ks_gen/cli.py`
- Create: `tests/test_cli/test_rules.py`

- [ ] **Step 1: Failing test**

```python
import json

from typer.testing import CliRunner

from ks_gen.cli import app


def test_rules_default_lists_ids():
    result = CliRunner().invoke(app, ["rules"])
    assert result.exit_code == 0
    assert "admin_user_and_keys" in result.output
    assert "crypto_policy" in result.output


def test_rules_id_filter_returns_detail():
    result = CliRunner().invoke(app, ["rules", "--id", "crypto_policy"])
    assert result.exit_code == 0
    assert "crypto_policy" in result.output
    assert "depends_on" in result.output or "Affects" in result.output


def test_rules_json_format_parses():
    result = CliRunner().invoke(app, ["rules", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert any(r["id"] == "admin_user_and_keys" for r in data)
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Extend `cli.py`**

```python
from typing import Optional
import json as _json

from ks_gen.registry import load_rules


@app.command(name="rules", help="List the shipped rule catalog.")
def rules_cmd(
    id_: Optional[str] = typer.Option(None, "--id", help="Show detail for one rule id."),
    format_: str = typer.Option("table", "--format", help="table | json"),
) -> None:
    catalog = load_rules()
    if id_:
        match = next((r for r in catalog if r.id == id_), None)
        if not match:
            typer.echo(f"unknown rule id: {id_}", err=True)
            raise typer.Exit(code=int(ExitCode.USAGE))
        typer.echo(f"id: {match.id}")
        typer.echo(f"summary: {match.summary}")
        typer.echo(f"depends_on: {match.depends_on}")
        typer.echo(f"stig_rules_affected ({len(match.stig_rules_affected)}):")
        for rid in match.stig_rules_affected:
            typer.echo(f"  - {rid}")
        return
    if format_ == "json":
        typer.echo(
            _json.dumps(
                [
                    {
                        "id": r.id,
                        "summary": r.summary,
                        "depends_on": r.depends_on,
                        "stig_rules_affected": r.stig_rules_affected,
                    }
                    for r in catalog
                ],
                indent=2,
            )
        )
        return
    width = max(len(r.id) for r in catalog)
    typer.echo(f"{'ID':<{width}}  AFFECTS  SUMMARY")
    for r in catalog:
        typer.echo(f"{r.id:<{width}}  {len(r.stig_rules_affected):<7}  {r.summary}")
```

- [ ] **Step 4: Run** — 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/cli.py tests/test_cli/test_rules.py
git commit -S -m "feat(cli): rules subcommand (table, json, --id detail)"
```

---

## Task 34: `schema` CLI subcommand

**Files:**
- Modify: `src/ks_gen/cli.py`
- Create: `tests/test_cli/test_schema.py`

- [ ] **Step 1: Failing test**

```python
import json

from typer.testing import CliRunner

from ks_gen.cli import app


def test_schema_emits_jsonschema():
    result = CliRunner().invoke(app, ["schema"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["title"] == "HostConfig"
    assert "system" in data["properties"]
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Extend `cli.py`**

```python
from ks_gen.config import HostConfig


@app.command(name="schema", help="Emit JSON Schema for host.yaml on stdout.")
def schema_cmd() -> None:
    typer.echo(_json.dumps(HostConfig.model_json_schema(), indent=2))
```

- [ ] **Step 4: Run** — 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/cli.py tests/test_cli/test_schema.py
git commit -S -m "feat(cli): schema subcommand emits host.yaml JSON Schema"
```

---

## Task 35: Wizard + `new` CLI subcommand

The interactive wizard is the largest single CLI piece. Tests use typer's `CliRunner` with a scripted stdin (`input=` parameter).

**Files:**
- Create: `src/ks_gen/wizard.py`
- Modify: `src/ks_gen/cli.py`
- Create: `tests/test_cli/test_new.py`

- [ ] **Step 1: Failing test**

```python
import textwrap

from typer.testing import CliRunner

from ks_gen.cli import app


def test_new_runs_with_scripted_stdin(tmp_path):
    runner = CliRunner()
    # Minimal happy path: accept all defaults except hostname, admin name, and one key.
    stdin = textwrap.dedent(
        """\
        web01.example.com



        opsadmin


        ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA test@laptop

        """
    )
    out_dir = tmp_path / "out"
    result = runner.invoke(
        app,
        ["new", "--out", str(out_dir)],
        input=stdin,
    )
    assert result.exit_code == 0, result.output
    for name in ("ks.cfg", "tailoring.xml", "host.yaml", "exceptions.md"):
        assert (out_dir / "web01.example.com" / name).is_file()


def test_new_non_interactive_errors_without_required_fields(tmp_path):
    runner = CliRunner()
    result = runner.invoke(app, ["new", "--out", str(tmp_path / "x"), "--non-interactive"])
    assert result.exit_code != 0
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement `wizard.py`**

`src/ks_gen/wizard.py`:
```python
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

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


def run_wizard(*, interactive: bool) -> tuple[HostConfig, str]:
    hostname = _ask("Hostname", None, interactive=interactive)
    timezone = _ask("Timezone", "UTC", interactive=interactive)
    locale = _ask("Locale", "en_US.UTF-8", interactive=interactive)
    admin_name = _ask("Admin username", "opsadmin", interactive=interactive)
    sudo = _ask("Admin sudo mode (nopasswd_no/nopasswd_yes)", "nopasswd_no", interactive=interactive)
    keys = _ask_keys(interactive)
    ssh_port_raw = _ask("SSH port", "22", interactive=interactive)
    crypto_policy = _ask("Crypto policy (STIG/MODERN/FUTURE)", "MODERN", interactive=interactive)

    payload: dict[str, Any] = {
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
    cfg = HostConfig.model_validate(payload)
    yaml_text = yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False, default_flow_style=False)
    return cfg, yaml_text


def write_initial(out_root: Path, cfg: HostConfig, yaml_text: str) -> Path:
    host_dir = out_root / cfg.system.hostname
    host_dir.mkdir(parents=True, exist_ok=True)
    (host_dir / "host.yaml").write_text(yaml_text, encoding="utf-8", newline="\n")
    return host_dir
```

- [ ] **Step 4: Wire into `cli.py`**

```python
from ks_gen.wizard import WizardError, run_wizard, write_initial


@app.command(name="new", help="Interactive wizard: produce host.yaml + ks bundle.")
def new_cmd(
    out: Path = typer.Option(..., "--out", "-o", file_okay=False),
    non_interactive: bool = typer.Option(False, "--non-interactive"),
) -> None:
    try:
        cfg, yaml_text = run_wizard(interactive=not non_interactive)
    except WizardError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=int(ExitCode.USAGE))
    host_dir = write_initial(out, cfg, yaml_text)
    bundle = build_bundle(cfg)
    write_bundle(bundle, host_dir)
    report = lint_kickstart(host_dir / "ks.cfg")
    if not report.ok:
        for f in report.failures:
            typer.echo(f"lint FAIL: {f}", err=True)
        raise typer.Exit(code=int(ExitCode.LINT_FAIL))
    typer.echo(f"Wrote bundle to {host_dir}")
```

- [ ] **Step 5: Run** — 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/wizard.py src/ks_gen/cli.py tests/test_cli/test_new.py
git commit -S -m "feat(cli): new subcommand drives interactive wizard"
```

---

## Task 36: `iso.py` and `iso` CLI subcommand

`xorriso` is mocked at the subprocess boundary in tests (per spec section 6.5).

**Files:**
- Create: `src/ks_gen/iso.py`
- Modify: `src/ks_gen/cli.py`
- Create: `tests/test_iso.py`

- [ ] **Step 1: Failing test**

```python
from pathlib import Path
from unittest.mock import patch

from ks_gen.iso import IsoBuildError, build_iso


def test_build_iso_calls_xorriso(tmp_path):
    src = tmp_path / "src.iso"
    src.write_bytes(b"\0" * 1024)
    ks = tmp_path / "ks.cfg"
    ks.write_text("text\n", encoding="utf-8")
    tail = tmp_path / "tailoring.xml"
    tail.write_text("<x/>", encoding="utf-8")
    out = tmp_path / "out.iso"
    with patch("ks_gen.iso.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        build_iso(src, ks, tail, out, volid="ALMA9")
    assert run.called
    args = run.call_args[0][0]
    assert args[0] == "xorriso"
    assert str(out) in args


def test_build_iso_missing_xorriso_raises(tmp_path):
    src = tmp_path / "src.iso"
    src.write_bytes(b"\0")
    ks = tmp_path / "ks.cfg"
    ks.write_text("x", encoding="utf-8")
    tail = tmp_path / "t.xml"
    tail.write_text("x", encoding="utf-8")
    out = tmp_path / "out.iso"
    with patch("ks_gen.iso.shutil.which", return_value=None):
        try:
            build_iso(src, ks, tail, out, volid="ALMA9")
        except IsoBuildError as e:
            assert "xorriso" in str(e)
        else:
            raise AssertionError("expected IsoBuildError")
```

- [ ] **Step 2: Run — fail**

- [ ] **Step 3: Implement**

`src/ks_gen/iso.py`:
```python
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class IsoBuildError(Exception):
    pass


def build_iso(
    src_iso: Path,
    ks_cfg: Path,
    tailoring_xml: Path,
    out_iso: Path,
    *,
    volid: str,
    keep_original_default: bool = False,
) -> None:
    if shutil.which("xorriso") is None:
        raise IsoBuildError("xorriso not on PATH (install: dnf install xorriso / brew install xorriso)")
    args = [
        "xorriso",
        "-indev", str(src_iso),
        "-outdev", str(out_iso),
        "-boot_image", "any", "replay",
        "-volid", volid,
        "-map", str(ks_cfg), "/ks.cfg",
        "-map", str(tailoring_xml), "/tailoring.xml",
        "-chmod", "0444", "/ks.cfg", "/tailoring.xml", "--",
    ]
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise IsoBuildError(f"xorriso failed: {result.stderr}")
```

- [ ] **Step 4: Wire CLI**

```python
from ks_gen.iso import IsoBuildError, build_iso


@app.command(name="iso", help="Repackage AlmaLinux DVD ISO with ks.cfg + tailoring embedded.")
def iso_cmd(
    src: Path = typer.Option(..., "--src", exists=True, dir_okay=False),
    ks: Path = typer.Option(..., "--ks", exists=True, dir_okay=False),
    tailoring: Path = typer.Option(..., "--tailoring", exists=True, dir_okay=False),
    out: Path = typer.Option(..., "--out", dir_okay=False),
    volid: str = typer.Option("ALMA9", "--volid"),
) -> None:
    try:
        build_iso(src, ks, tailoring, out, volid=volid)
    except IsoBuildError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=int(ExitCode.TOOL_MISSING))
    typer.echo(f"Wrote {out}")
```

- [ ] **Step 5: Run** — 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/iso.py src/ks_gen/cli.py tests/test_iso.py
git commit -S -m "feat(iso): xorriso wrapper + iso CLI subcommand"
```

---

## Tasks 37–40: Golden snapshots

These tests use **syrupy** to compare the generated bundle to committed snapshots. First run generates the snapshots; subsequent runs diff against them.

### Task 37: `minimal-dhcp` golden

**Files:**
- Create: `tests/golden/__init__.py`
- Create: `tests/golden/minimal-dhcp.host.yaml`
- Create: `tests/golden/test_minimal_dhcp.py`
- Create: `tests/golden/__snapshots__/test_minimal_dhcp.ambr` *(auto-generated)*

- [ ] **Step 1: Source YAML**

`tests/golden/minimal-dhcp.host.yaml`:
```yaml
system:
  hostname: web01.example.com
user:
  admin:
    name: opsadmin
    authorized_keys:
      - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEYminimaldhcp test@laptop"
```

- [ ] **Step 2: Snapshot test**

`tests/golden/test_minimal_dhcp.py`:
```python
from pathlib import Path
import re

from ks_gen.loader import load_host_config
from ks_gen.writer import build_bundle


def _normalize(text: str) -> str:
    text = re.sub(r"Generated by ks-gen v\S+ on \S+", "Generated by ks-gen vSNAP on SNAP", text)
    text = re.sub(r"Generated: \S+", "Generated: SNAP", text)
    text = re.sub(r"<xccdf:version time=\"[^\"]+\"", "<xccdf:version time=\"SNAP\"", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def test_minimal_dhcp(snapshot):
    yaml_path = Path(__file__).parent / "minimal-dhcp.host.yaml"
    cfg = load_host_config(yaml_path, sets=[])
    bundle = build_bundle(cfg)
    assert _normalize(bundle.ks_cfg) == snapshot(name="ks.cfg")
    assert _normalize(bundle.tailoring_xml) == snapshot(name="tailoring.xml")
    assert _normalize(bundle.exceptions_md) == snapshot(name="exceptions.md")
```

- [ ] **Step 3: Generate snapshots**

```bash
.venv/Scripts/python.exe -m pytest tests/golden/test_minimal_dhcp.py --snapshot-update -v
```

Review the generated `.ambr` file under `tests/golden/__snapshots__/`. Confirm:
- ks.cfg references `tailoring.xml` in the addon block
- ks.cfg contains the admin user block before the sshd block
- exceptions.md shows MODERN crypto rules disabled and the civilian banner

- [ ] **Step 4: Lock snapshots and commit**

```bash
.venv/Scripts/python.exe -m pytest tests/golden/test_minimal_dhcp.py -v
git add tests/golden/__init__.py tests/golden/minimal-dhcp.host.yaml tests/golden/test_minimal_dhcp.py tests/golden/__snapshots__
git commit -S -m "test(golden): minimal-dhcp scenario snapshot"
```

### Task 38: `stig-strict` golden

Same shape; YAML uses `STIG` crypto, `fips_mode: true`, USBGuard on.

**Files:**
- Create: `tests/golden/stig-strict.host.yaml`
- Create: `tests/golden/test_stig_strict.py`

`tests/golden/stig-strict.host.yaml`:
```yaml
system:
  hostname: stig01.example.com
user:
  admin:
    name: stigops
    authorized_keys:
      - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEYstigstrict ops@bastion"
crypto:
  policy: STIG
overrides:
  fips_mode: true
  usbguard:
    enable: true
  faillock:
    enable: true
    deny: 3
    unlock_time: 0
    even_deny_root: true
  auditd:
    disk_full_action: HALT
    disk_error_action: HALT
    max_log_file_action: keep_logs
```

Test mirrors Task 37 with the new filename. Snapshot-update and commit identically.

```bash
.venv/Scripts/python.exe -m pytest tests/golden/test_stig_strict.py --snapshot-update -v
.venv/Scripts/python.exe -m pytest tests/golden/test_stig_strict.py -v
git add tests/golden/stig-strict.host.yaml tests/golden/test_stig_strict.py tests/golden/__snapshots__
git commit -S -m "test(golden): stig-strict scenario snapshot"
```

### Task 39: `modern-crypto` golden

`tests/golden/modern-crypto.host.yaml`:
```yaml
system:
  hostname: mod01.example.com
user:
  admin:
    name: modops
    authorized_keys:
      - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEYmoderncrypto ops@host"
crypto:
  policy: MODERN
overrides:
  fips_mode: false
```

Test, snapshot-update, commit per pattern.

### Task 40: `bare-metal-usbguard` golden

`tests/golden/bare-metal-usbguard.host.yaml`:
```yaml
system:
  hostname: baremetal01.example.com
network:
  interfaces:
    - device: eno1
      bootproto: static
      ip: 192.168.50.10
      netmask: 255.255.255.0
      gateway: 192.168.50.1
      nameservers: [1.1.1.1, 9.9.9.9]
user:
  admin:
    name: physadmin
    authorized_keys:
      - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEYbaremetalusbguard ops@kvm"
ssh:
  port: 2222
overrides:
  usbguard:
    enable: true
```

Test, snapshot-update, commit per pattern.

---

## Task 41: README and CHANGELOG

**Files:**
- Create: `README.md`
- Create: `CHANGELOG.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# ks-gen — remote-safe DISA STIG kickstart generator for AlmaLinux 9

`ks-gen` turns a small YAML file into a fully baked AlmaLinux 9 kickstart that:

- Applies the upstream DISA STIG profile via `scap-security-guide` + `oscap-anaconda-addon`.
- Stays remote-safe by default — won't lock you out of a cloud or headless box.
- Substitutes civilian text for DoD-specific banners, certificate bundles, time servers.
- Emits an `exceptions.md` audit report naming every XCCDF rule it disables and why.

See the design spec at `docs/superpowers/specs/2026-06-01-alma-stig-kickstart-design.md`.

## Quickstart

```bash
pipx install .
ks-gen new --out ./build
# Walks you through a few prompts, writes ./build/<hostname>/{host.yaml,ks.cfg,tailoring.xml,exceptions.md}

ks-gen gen --config ./build/<hostname>/host.yaml --out ./build/<hostname>
ks-gen iso --src AlmaLinux-9-latest-x86_64-dvd.iso \
           --ks ./build/<hostname>/ks.cfg \
           --tailoring ./build/<hostname>/tailoring.xml \
           --out ./<hostname>-installer.iso
```

## Subcommands

| Command | Purpose |
|---|---|
| `ks-gen new` | Interactive wizard; produces the 4-file bundle |
| `ks-gen gen` | Non-interactive re-render from `host.yaml` |
| `ks-gen lint` | Validate a `ks.cfg` (ksvalidator + invariants) |
| `ks-gen iso` | Repackage the AlmaLinux DVD ISO with kickstart embedded |
| `ks-gen rules` | List the override rule catalog |
| `ks-gen schema` | Emit JSON Schema for `host.yaml` |

## Exit codes

`0` success · `1` usage · `2` config invalid · `3` rule conflict · `4` lint failure · `5` external tool missing.

## License

Apache-2.0.
```

- [ ] **Step 2: Write `CHANGELOG.md`**

```markdown
# Changelog

All notable changes to ks-gen are tracked here. Rule additions especially:
the catalog drives the audit story.

## [0.1.0] — 2026-06-01

### Added
- Initial implementation per design spec.
- 12 override rules: admin_user_and_keys, ssh_keep_open, ssh_config_apply,
  faillock_safety, crypto_policy, banner_text, time_servers, dod_root_ca,
  auditd_actions, usbguard, kernel_module_blacklist, package_purge.
- CLI subcommands: new, gen, iso, lint, rules, schema.
- Four golden snapshots: minimal-dhcp, stig-strict, modern-crypto, bare-metal-usbguard.
```

- [ ] **Step 3: Commit**

```bash
git add README.md CHANGELOG.md
git commit -S -m "docs: README quickstart and initial CHANGELOG"
```

---

## Self-review (run before declaring the plan complete)

1. **Spec coverage** — every numbered spec section maps to at least one task:
   - §1 motivation — captured in `README.md` (Task 41) and the working agreements.
   - §2 architecture — Tasks 11, 12, 13, 14, 27.
   - §2.1 hybrid STIG application — encoded in the Rule contract (Task 3) and the writer (Task 27).
   - §2.2 external deps — `pyproject.toml` (Task 1), `iso.py` (Task 36).
   - §3 data model — Tasks 4–10.
   - §3.2 crypto policy semantics — Task 7 + Task 19.
   - §3.3 disk layout — Task 14 (partitioning partials).
   - §3.4 cross-field validators — Task 9.
   - §4 rule contract + catalog — Tasks 3, 15–26.
   - §4.3 invariants — Task 29.
   - §5 CLI surface — Tasks 30, 32, 33, 34, 35, 36.
   - §6 testing — Tasks 4–40 inclusive; specifically §6.3 golden = Tasks 37–40.
   - §6.6 CI — Task 2.
   - §7 repo layout / packaging — Task 1.

2. **Placeholder scan** — no `TBD`, `TODO`, or "implement later" in any step.

3. **Type consistency** — `Rule` protocol defined in Task 3 is used identically in Tasks 11, 15–26, 27. `TailoringOp` constructor signature is consistent across all rule tasks. `HostConfig` builder pattern (`minimal_cfg` fixture) is consistent across Tasks 14–26.

4. **Scope** — single subsystem (one CLI, one config schema, one rule catalog). Appropriate for a single plan.

