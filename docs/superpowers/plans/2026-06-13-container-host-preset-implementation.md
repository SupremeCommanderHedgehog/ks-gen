# Container-Host Preset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in `containers:` config block that provisions /srv/containers (auto-injected XFS logvol), installs the rootless-podman tooling stack, drops the `create-rootless-user.sh` script to /root, writes a system-wide `storage.conf`, and creates the configured container users via the same script.

**Architecture:** New `Containers`/`ContainerUser`/`ContainerVolume` pydantic models gated by `containers.enabled` (default false → no behavior change). New rule `container_host.py` reads the shipped script via `importlib.resources` and emits a `%post` block that drops the script, writes storage.conf, and per-user calls the script. Template auto-appends one `logvol /srv/containers` line after the existing preset-or-layout partition block.

**Tech Stack:** Python 3.11+, pydantic v2 (frozen StrictModel + field/model validators), Jinja2 templates, syrupy snapshot tests, pytest. Bash script ships as a repo asset and is loaded via `importlib.resources`.

**Spec:** `docs/superpowers/specs/2026-06-13-container-host-preset-design.md` (on branch `spec/container-host-preset`). Appendix A of the spec is the authoritative script body.

---

## File Structure

**Create:**
- `src/ks_gen/assets/__init__.py` — empty marker so `importlib.resources` sees the dir as a package
- `src/ks_gen/assets/create-rootless-user.sh` — byte-identical copy of spec Appendix A
- `src/ks_gen/rules/container_host.py` — the new rule
- `tests/golden/container-host.host.yaml` — fixture, containers.enabled + default packages
- `tests/golden/test_container_host.py` — golden test
- `tests/golden/container-host-lean.host.yaml` — fixture, containers.enabled + lean preset
- `tests/golden/test_container_host_lean.py` — golden test

**Modify:**
- `src/ks_gen/config.py` — add `re` import; add `ContainerVolume`, `ContainerUser`, `Containers`; add `containers: Containers` field on `HostConfig`; add cross-cutting `model_validator` on `HostConfig`
- `src/ks_gen/templates/ks.cfg.j2` — append one Jinja `{% if cfg.containers.enabled %}` block after the partition-include block
- `pyproject.toml` — add `ks_gen.assets` to the `tool.hatch.build.targets.wheel` packages list so the script ships in the wheel
- `tests/test_config_schema.py` — append unit tests for the three new models and the HostConfig validator
- `MANUAL.md` — add a new section 4.X for `containers:` between the existing 4.10 (`packages`) and 4.11 (`overrides`)

**Untouched (intentional):**
- No new lint rules — HostConfig validator catches the only meaningful misconfiguration.
- No changes to existing rules.
- No changes to writer.py — the rule contract handles emit_packages composition automatically.

---

### Task 1: Add `ContainerVolume` model

**Files:**
- Modify: `src/ks_gen/config.py` (add `import re` near the top if not present; add the model near the existing `Packages` model)
- Modify: `tests/test_config_schema.py`

- [ ] **Step 1: Write failing tests**

First add `ContainerVolume` to the import block at the top of `tests/test_config_schema.py` (alphabetical, between `Banner` and `Crypto`).

Append to `tests/test_config_schema.py`:

```python
def test_container_volume_defaults():
    v = ContainerVolume()
    assert v.size == "20G"
    assert v.fsoptions == "nodev,nosuid"
    assert v.size_mib == 20480


def test_container_volume_size_mib_megabytes():
    assert ContainerVolume(size="500M").size_mib == 500


def test_container_volume_size_mib_terabytes():
    assert ContainerVolume(size="1T").size_mib == 1048576


def test_container_volume_rejects_invalid_size_pattern():
    with pytest.raises(ValidationError):
        ContainerVolume(size="20GB")  # only M|G|T allowed, no double-letter
    with pytest.raises(ValidationError):
        ContainerVolume(size="big")


def test_container_volume_rejects_noexec_fsoption():
    with pytest.raises(ValidationError):
        ContainerVolume(fsoptions="nodev,nosuid,noexec")


def test_container_volume_rejects_noexec_with_spaces():
    with pytest.raises(ValidationError):
        ContainerVolume(fsoptions="nodev, noexec , nosuid")


def test_container_volume_accepts_other_options():
    v = ContainerVolume(fsoptions="nodev,nosuid,noatime")
    assert v.fsoptions == "nodev,nosuid,noatime"
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config_schema.py -k "container_volume" -v
```

Expected: 7 tests fail (ImportError on `ContainerVolume`).

- [ ] **Step 3: Add the model**

In `src/ks_gen/config.py`:

1. Confirm `import re` is at the top (just below `from __future__ import annotations`). If absent, add it.

2. Just before `class Packages(StrictModel):` (around line 369, after the `Crypto` class), add:

```python
class ContainerVolume(StrictModel):
    size: str = Field(default="20G", pattern=r"^\d+(M|G|T)$")
    fsoptions: str = "nodev,nosuid"

    @field_validator("fsoptions")
    @classmethod
    def _reject_noexec(cls, v: str) -> str:
        tokens = [t for t in re.split(r"[,\s]+", v) if t]
        if "noexec" in tokens:
            raise ValueError(
                "containers.volume.fsoptions: noexec is incompatible with "
                "container image execution; remove it"
            )
        return v

    @property
    def size_mib(self) -> int:
        unit = self.size[-1]
        n = int(self.size[:-1])
        if unit == "M":
            return n
        if unit == "G":
            return n * 1024
        # unit == "T" — pattern guarantees one of M|G|T
        return n * 1024 * 1024
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config_schema.py -k "container_volume" -v
.\.venv\Scripts\python.exe -m mypy
```

Expected: 7 new tests PASS; mypy clean.

- [ ] **Step 5: Commit**

```powershell
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -am "feat(config): add ContainerVolume model with size_mib and fsoptions noexec rejection"
```

---

### Task 2: Add `ContainerUser` model

**Files:**
- Modify: `src/ks_gen/config.py` (add the model after `ContainerVolume`)
- Modify: `tests/test_config_schema.py`

- [ ] **Step 1: Write failing tests**

Add `ContainerUser` to the alphabetical import block.

Append to `tests/test_config_schema.py`:

```python
def test_container_user_minimal():
    u = ContainerUser(name="webapp", authorized_keys=["ssh-ed25519 AAAA u@h"])
    assert u.name == "webapp"
    assert u.gecos == ""


def test_container_user_with_gecos():
    u = ContainerUser(
        name="webapp", gecos="Web app workloads", authorized_keys=["ssh-ed25519 AAAA u@h"]
    )
    assert u.gecos == "Web app workloads"


def test_container_user_rejects_root():
    with pytest.raises(ValidationError):
        ContainerUser(name="root", authorized_keys=["ssh-ed25519 AAAA u@h"])


def test_container_user_rejects_invalid_name_uppercase():
    with pytest.raises(ValidationError):
        ContainerUser(name="WebApp", authorized_keys=["ssh-ed25519 AAAA u@h"])


def test_container_user_rejects_name_starting_with_digit():
    with pytest.raises(ValidationError):
        ContainerUser(name="1webapp", authorized_keys=["ssh-ed25519 AAAA u@h"])


def test_container_user_rejects_name_starting_with_dash():
    with pytest.raises(ValidationError):
        ContainerUser(name="-webapp", authorized_keys=["ssh-ed25519 AAAA u@h"])


def test_container_user_requires_at_least_one_authorized_key():
    with pytest.raises(ValidationError):
        ContainerUser(name="webapp", authorized_keys=[])
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config_schema.py -k "container_user" -v
```

Expected: 7 tests fail (ImportError on `ContainerUser`).

- [ ] **Step 3: Add the model**

In `src/ks_gen/config.py`, immediately after `ContainerVolume`, add:

```python
class ContainerUser(StrictModel):
    name: str = Field(..., pattern=r"^[a-z_][a-z0-9_-]{0,31}$")
    gecos: str = ""
    authorized_keys: list[str] = Field(..., min_length=1)

    @field_validator("name")
    @classmethod
    def _not_root(cls, v: str) -> str:
        if v == "root":
            raise ValueError("containers.users[].name cannot be 'root'")
        return v
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config_schema.py -k "container_user" -v
.\.venv\Scripts\python.exe -m mypy
```

Expected: 7 tests PASS; mypy clean.

- [ ] **Step 5: Commit**

```powershell
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -am "feat(config): add ContainerUser model"
```

---

### Task 3: Add `Containers` model and wire it into `HostConfig`

**Files:**
- Modify: `src/ks_gen/config.py` (add the model after `ContainerUser`; add `containers` field on `HostConfig`)
- Modify: `tests/test_config_schema.py`

- [ ] **Step 1: Write failing tests**

Add `Containers` to the alphabetical import block.

Append to `tests/test_config_schema.py`:

```python
def test_containers_defaults_disabled():
    c = Containers()
    assert c.enabled is False
    assert c.users == []
    assert c.volume.size == "20G"


def test_containers_enabled_with_empty_users_ok():
    # Script is installed at /root even when users list is empty
    c = Containers(enabled=True)
    assert c.enabled is True
    assert c.users == []


def test_containers_rejects_duplicate_user_names_when_enabled():
    user_a = ContainerUser(name="webapp", authorized_keys=["ssh-ed25519 K1 a@h"])
    user_b = ContainerUser(name="webapp", authorized_keys=["ssh-ed25519 K2 b@h"])
    with pytest.raises(ValidationError):
        Containers(enabled=True, users=[user_a, user_b])


def test_containers_allows_duplicate_user_names_when_disabled():
    # No validation when feature is off — users list is unused
    user_a = ContainerUser(name="webapp", authorized_keys=["ssh-ed25519 K1 a@h"])
    user_b = ContainerUser(name="webapp", authorized_keys=["ssh-ed25519 K2 b@h"])
    c = Containers(enabled=False, users=[user_a, user_b])
    assert c.enabled is False


def test_hostconfig_containers_defaults_disabled(minimal_cfg):
    assert minimal_cfg.containers.enabled is False
```

(The `minimal_cfg` fixture comes from `tests/conftest.py` and provides a valid `HostConfig`.)

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config_schema.py -k "containers" -v
```

Expected: 5 tests fail (ImportError on `Containers`, AttributeError on `cfg.containers`).

- [ ] **Step 3: Add the model and wire it**

In `src/ks_gen/config.py`, immediately after `ContainerUser`, add:

```python
class Containers(StrictModel):
    enabled: bool = False
    users: list[ContainerUser] = Field(default_factory=list)
    volume: ContainerVolume = Field(default_factory=ContainerVolume)

    @model_validator(mode="after")
    def _validate_users_distinct(self) -> Containers:
        if not self.enabled:
            return self
        names = [u.name for u in self.users]
        if len(names) != len(set(names)):
            seen: set[str] = set()
            for n in names:
                if n in seen:
                    raise ValueError(f"containers.users duplicate name: {n}")
                seen.add(n)
        return self
```

In `HostConfig` (around line 542), add a `containers` field at the end of the existing field list (just after `custom_post`):

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
    containers: Containers = Field(default_factory=Containers)
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config_schema.py -k "containers" -v
.\.venv\Scripts\python.exe -m mypy
```

Expected: 5 tests PASS; mypy clean.

- [ ] **Step 5: Commit**

```powershell
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -am "feat(config): add Containers model and wire to HostConfig"
```

---

### Task 4: Add HostConfig cross-cutting validators

**Files:**
- Modify: `src/ks_gen/config.py` (add `model_validator` on `HostConfig`)
- Modify: `tests/test_config_schema.py`

This task adds the two cross-cutting checks the spec calls out:
1. No `containers.users[].name == cfg.user.admin.name` when `containers.enabled`.
2. No LV mounted at `/srv/containers` in `cfg.disk.layout` when `containers.enabled` (would conflict with the auto-injected logvol).

- [ ] **Step 1: Write failing tests**

Make sure `Disk`, `DiskLayout`, `DiskLvDef` are in the imports at the top of `tests/test_config_schema.py` (some are already there; add the missing ones alphabetically).

Append to `tests/test_config_schema.py`:

```python
def test_hostconfig_rejects_container_user_matching_admin_name():
    with pytest.raises(ValidationError) as exc_info:
        HostConfig(
            system=System(hostname="h"),
            user=User(
                admin=AdminUser(
                    name="opsadmin",
                    authorized_keys=["ssh-ed25519 K admin@h"],
                    sudo="nopasswd_yes",
                )
            ),
            containers=Containers(
                enabled=True,
                users=[ContainerUser(name="opsadmin", authorized_keys=["ssh-ed25519 K x@h"])],
            ),
        )
    assert "user.admin" in str(exc_info.value)


def test_hostconfig_allows_distinct_container_and_admin_names():
    cfg = HostConfig(
        system=System(hostname="h"),
        user=User(
            admin=AdminUser(
                name="opsadmin",
                authorized_keys=["ssh-ed25519 K admin@h"],
                sudo="nopasswd_yes",
            )
        ),
        containers=Containers(
            enabled=True,
            users=[ContainerUser(name="webapp", authorized_keys=["ssh-ed25519 K w@h"])],
        ),
    )
    assert cfg.containers.users[0].name == "webapp"


def test_hostconfig_rejects_layout_with_srv_containers_when_containers_enabled():
    with pytest.raises(ValidationError) as exc_info:
        HostConfig(
            system=System(hostname="h"),
            user=User(
                admin=AdminUser(
                    name="opsadmin",
                    authorized_keys=["ssh-ed25519 K admin@h"],
                    sudo="nopasswd_yes",
                )
            ),
            disk=Disk(
                layout=DiskLayout(
                    lvs=[
                        DiskLvDef(name="root", mount="/", size="15G"),
                        DiskLvDef(name="home", mount="/home", size="5G"),
                        DiskLvDef(name="tmp", mount="/tmp", size="3G"),
                        DiskLvDef(name="var", mount="/var", size="10G"),
                        DiskLvDef(name="varlog", mount="/var/log", size="5G"),
                        DiskLvDef(name="varlogaudit", mount="/var/log/audit", size="3G"),
                        DiskLvDef(name="vartmp", mount="/var/tmp", size="2G"),
                        DiskLvDef(name="containers", mount="/srv/containers", size="20G"),
                        DiskLvDef(name="swap", fstype="swap"),
                    ],
                )
            ),
            containers=Containers(enabled=True),
        )
    assert "/srv/containers" in str(exc_info.value)


def test_hostconfig_allows_layout_without_srv_containers_when_containers_enabled():
    cfg = HostConfig(
        system=System(hostname="h"),
        user=User(
            admin=AdminUser(
                name="opsadmin",
                authorized_keys=["ssh-ed25519 K admin@h"],
                sudo="nopasswd_yes",
            )
        ),
        disk=Disk(
            layout=DiskLayout(
                lvs=[
                    DiskLvDef(name="root", mount="/", size="15G"),
                    DiskLvDef(name="home", mount="/home", size="5G"),
                    DiskLvDef(name="tmp", mount="/tmp", size="3G"),
                    DiskLvDef(name="var", mount="/var", size="10G"),
                    DiskLvDef(name="varlog", mount="/var/log", size="5G"),
                    DiskLvDef(name="varlogaudit", mount="/var/log/audit", size="3G"),
                    DiskLvDef(name="vartmp", mount="/var/tmp", size="2G"),
                    DiskLvDef(name="swap", fstype="swap"),
                ],
            )
        ),
        containers=Containers(enabled=True),
    )
    assert cfg.containers.enabled is True


def test_hostconfig_allows_containers_with_default_disk_preset():
    # Default disk path (preset=STIG_SERVER) has no /srv/containers LV
    # in its partial, so this is always safe.
    cfg = HostConfig(
        system=System(hostname="h"),
        user=User(
            admin=AdminUser(
                name="opsadmin",
                authorized_keys=["ssh-ed25519 K admin@h"],
                sudo="nopasswd_yes",
            )
        ),
        containers=Containers(enabled=True),
    )
    assert cfg.containers.enabled is True
    assert cfg.disk.preset is not None  # default STIG_SERVER
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config_schema.py -k "hostconfig" -v
```

Expected: the 2 new "rejects" tests fail (no validator yet); the 3 "allows" tests may pass (no validator means everything is allowed). Note: only the rejection tests are the strong signal here.

- [ ] **Step 3: Add the cross-cutting validator**

In `src/ks_gen/config.py`, at the end of the `HostConfig` class body, add:

```python
    @model_validator(mode="after")
    def _validate_containers_integration(self) -> HostConfig:
        if not self.containers.enabled:
            return self

        admin_name = self.user.admin.name
        for u in self.containers.users:
            if u.name == admin_name:
                raise ValueError(
                    f"containers.users[].name {u.name!r} collides with "
                    f"user.admin.name; admin user and container users must be distinct"
                )

        if self.disk.layout is not None:
            for lv in self.disk.layout.lvs:
                if lv.mount == "/srv/containers":
                    raise ValueError(
                        "containers.enabled=True conflicts with disk.layout LV mounted at "
                        "/srv/containers; the container-host preset auto-injects this LV"
                    )

        return self
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config_schema.py -v
.\.venv\Scripts\python.exe -m mypy
```

Expected: all 5 new tests PASS; no other test should regress.

- [ ] **Step 5: Commit**

```powershell
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -am "feat(config): add HostConfig cross-cutting validators for containers preset"
```

---

### Task 5: Ship the `create-rootless-user.sh` script + minimal `container_host` rule

**Files:**
- Create: `src/ks_gen/assets/__init__.py`
- Create: `src/ks_gen/assets/create-rootless-user.sh`
- Create: `src/ks_gen/rules/container_host.py`
- Modify: `pyproject.toml`
- Modify: `tests/test_config_schema.py` (add a new test file? No — use existing test_registry.py pattern. See step 1.)

This task ships the asset, wires it into the wheel build, and creates the rule with `applies()`, `emit_packages()`, `emit_tailoring()`, `exception_entry()` — but `emit_post()` returns an empty string. Task 6 fills `emit_post()`.

- [ ] **Step 1: Locate the existing rule-registration test pattern**

Read `tests/test_registry.py` to see how rules are tested for discovery and contract conformance. The new rule must show up in `load_rules()`.

```powershell
.\.venv\Scripts\python.exe -c "from ks_gen.registry import load_rules; print(sorted(r.id for r in load_rules()))"
```

Expected output: a sorted list of 12 existing rule IDs (the lean baseline PR doesn't add any rules).

- [ ] **Step 2: Write failing test for asset loading**

Append a new test file `tests/test_assets.py`:

```python
from importlib.resources import files


def test_create_rootless_user_script_is_shipped():
    script = files("ks_gen.assets").joinpath("create-rootless-user.sh").read_text(encoding="utf-8")
    assert script.startswith("#!/usr/bin/env bash")
    assert 'CONTAINERS_ROOT="/srv/containers"' in script
    assert "create-rootless-user.sh" in script  # mentioned in usage banner


def test_create_rootless_user_script_is_executable_text():
    # We embed the script via a heredoc in %post; it must be plain text
    # without any null bytes or BOM that would break the heredoc.
    raw = files("ks_gen.assets").joinpath("create-rootless-user.sh").read_bytes()
    assert b"\x00" not in raw
    assert not raw.startswith(b"\xef\xbb\xbf")  # no UTF-8 BOM
```

- [ ] **Step 3: Write failing tests for rule basics**

Append to `tests/test_config_schema.py` (or create `tests/test_rule_container_host.py` if the file is getting too long; use the existing pattern):

```python
def test_container_host_rule_id_and_summary():
    from ks_gen.rules.container_host import RULE

    assert RULE.id == "container_host"
    assert "rootless" in RULE.summary.lower() or "container" in RULE.summary.lower()


def test_container_host_rule_does_not_apply_by_default(minimal_cfg):
    from ks_gen.rules.container_host import RULE

    assert RULE.applies(minimal_cfg) is False


def test_container_host_rule_applies_when_enabled(minimal_cfg):
    from ks_gen.config import Containers
    from ks_gen.rules.container_host import RULE

    enabled_cfg = minimal_cfg.model_copy(update={"containers": Containers(enabled=True)})
    assert RULE.applies(enabled_cfg) is True


def test_container_host_emit_packages_returns_podman_stack(minimal_cfg):
    from ks_gen.rules.container_host import RULE

    pkgs = RULE.emit_packages(minimal_cfg)
    assert "podman" in pkgs
    assert "crun" in pkgs
    assert "slirp4netns" in pkgs
    assert "fuse-overlayfs" in pkgs
    assert "containers-common" in pkgs
    assert "podman-plugins" in pkgs


def test_container_host_emit_tailoring_is_empty(minimal_cfg):
    from ks_gen.rules.container_host import RULE

    assert RULE.emit_tailoring(minimal_cfg) == []


def test_container_host_exception_entry_is_none(minimal_cfg):
    from ks_gen.rules.container_host import RULE

    assert RULE.exception_entry(minimal_cfg) is None


def test_container_host_rule_is_discoverable():
    from ks_gen.registry import load_rules

    rule_ids = {r.id for r in load_rules()}
    assert "container_host" in rule_ids
```

- [ ] **Step 4: Run tests to verify they fail**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_assets.py tests/test_config_schema.py -k "container_host or container_user_script" -v
```

Expected: ModuleNotFoundError / ImportError on `ks_gen.assets`, `ks_gen.rules.container_host`.

- [ ] **Step 5: Create the assets package**

Create `src/ks_gen/assets/__init__.py` as an empty file (or with a single-line comment — either works for `importlib.resources`):

```python
"""Static assets shipped with ks-gen (scripts, etc.) loaded via importlib.resources."""
```

- [ ] **Step 6: Copy the script verbatim**

Copy the **exact** contents of Appendix A from `docs/superpowers/specs/2026-06-13-container-host-preset-design.md` into `src/ks_gen/assets/create-rootless-user.sh`. Do not modify a single byte. The file should:

- Start with `#!/usr/bin/env bash`
- Use Unix line endings (LF, not CRLF) — verify with `file` or by hex-dump check
- Be saved as UTF-8 without BOM

After copying, sanity-check:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_assets.py -v
```

Expected: 2 tests PASS.

If the BOM check fails on Windows, you may need to re-save the file using an editor that explicitly writes UTF-8 without BOM (VS Code's encoding picker, or `Get-Content path | Out-File path -Encoding utf8NoBOM` in PowerShell 7+).

- [ ] **Step 7: Wire the assets directory into the wheel build**

In `pyproject.toml`, the existing `[tool.hatch.build.targets.wheel]` section says:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/ks_gen"]
```

This already covers `src/ks_gen/assets/` as a sub-package because `assets/__init__.py` makes it a package. But hatch doesn't include non-`.py` files by default. Add a `force-include` line to ensure the `.sh` ships:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/ks_gen"]

[tool.hatch.build.targets.wheel.force-include]
"src/ks_gen/assets/create-rootless-user.sh" = "ks_gen/assets/create-rootless-user.sh"
```

Verify the wheel build picks it up:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade build --quiet
.\.venv\Scripts\python.exe -m build --wheel --outdir /tmp/wheel-check
.\.venv\Scripts\python.exe -c "import zipfile; z = zipfile.ZipFile([f for f in __import__('pathlib').Path('/tmp/wheel-check').glob('*.whl')][-1]); names = z.namelist(); assert any('create-rootless-user.sh' in n for n in names), 'script missing from wheel'; print('OK: script in wheel')"
```

Expected: prints `OK: script in wheel`. If it doesn't, debug the hatch config before proceeding.

(Cleanup: `Remove-Item /tmp/wheel-check -Recurse -Force`.)

- [ ] **Step 8: Create the minimal rule**

Create `src/ks_gen/rules/container_host.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from importlib.resources import files
from typing import TYPE_CHECKING, cast

from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


# Loaded once at import time; embedded verbatim in every %post emission.
_SCRIPT = files("ks_gen.assets").joinpath("create-rootless-user.sh").read_text(encoding="utf-8")


@dataclass(frozen=True)
class _Rule:
    id: str = "container_host"
    summary: str = (
        "Install rootless-container helper, storage.conf, and per-user setup on /srv/containers."
    )
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return cfg.containers.enabled

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        # Task 6 fills this in. For now, return empty — rule still applies()
        # and shows up in the catalog, but the %post block is empty.
        return ""

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return [
            "podman",
            "crun",
            "slirp4netns",
            "fuse-overlayfs",
            "containers-common",
            "podman-plugins",
        ]

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return None


RULE: Rule = cast(Rule, _Rule())
```

- [ ] **Step 9: Run tests to verify they pass**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -v -k "container_host or assets"
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: all new tests PASS; full suite passes (no existing test regresses); mypy clean.

- [ ] **Step 10: Commit**

```powershell
git add src/ks_gen/assets/ src/ks_gen/rules/container_host.py pyproject.toml tests/test_assets.py tests/test_config_schema.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "feat(rules): ship create-rootless-user.sh asset + container_host rule skeleton"
```

---

### Task 6: Implement `container_host.emit_post`

**Files:**
- Modify: `src/ks_gen/rules/container_host.py`
- Modify: `tests/test_config_schema.py` (or a focused test file)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_config_schema.py`:

```python
def test_container_host_emit_post_drops_script_and_storage_conf(minimal_cfg):
    from ks_gen.config import Containers
    from ks_gen.rules.container_host import RULE

    cfg = minimal_cfg.model_copy(update={"containers": Containers(enabled=True)})
    body = RULE.emit_post(cfg)

    # Script lands at /root with 0550 perms
    assert "cat > /root/create-rootless-user.sh <<'__KS_GEN_EOF__'" in body
    assert "chmod 0550 /root/create-rootless-user.sh" in body
    assert "chown root:root /root/create-rootless-user.sh" in body

    # storage.conf with rootless_storage_path pointing at the mirror
    assert "cat > /etc/containers/storage.conf <<'__KS_GEN_EOF__'" in body
    assert 'rootless_storage_path = "/srv/containers/$USER/storage"' in body


def test_container_host_emit_post_empty_users_still_drops_script(minimal_cfg):
    from ks_gen.config import Containers
    from ks_gen.rules.container_host import RULE

    cfg = minimal_cfg.model_copy(update={"containers": Containers(enabled=True, users=[])})
    body = RULE.emit_post(cfg)

    assert "/root/create-rootless-user.sh" in body
    # No per-user provisioning calls when users list is empty
    assert "-l -c" not in body


def test_container_host_emit_post_provisions_each_user(minimal_cfg):
    from ks_gen.config import Containers, ContainerUser
    from ks_gen.rules.container_host import RULE

    cfg = minimal_cfg.model_copy(
        update={
            "containers": Containers(
                enabled=True,
                users=[
                    ContainerUser(
                        name="webapp",
                        gecos="Web app workloads",
                        authorized_keys=["ssh-ed25519 K1 w@bastion"],
                    ),
                    ContainerUser(
                        name="dbproxy",
                        authorized_keys=["ssh-ed25519 K2 d@bastion"],
                    ),
                ],
            )
        }
    )
    body = RULE.emit_post(cfg)

    # Each user gets a script invocation with -l (linger always-on at kickstart)
    assert '/root/create-rootless-user.sh -l -c "Web app workloads" webapp' in body
    assert '/root/create-rootless-user.sh -l -c "dbproxy" dbproxy' in body  # gecos defaults to name

    # Per-user authorized_keys file written after the script call
    assert "install -d -m 0700 -o webapp -g webapp /home/webapp/.ssh" in body
    assert "/home/webapp/.ssh/authorized_keys" in body
    assert "install -d -m 0700 -o dbproxy -g dbproxy /home/dbproxy/.ssh" in body
    assert "/home/dbproxy/.ssh/authorized_keys" in body


def test_container_host_emit_post_handles_multiple_keys(minimal_cfg):
    from ks_gen.config import Containers, ContainerUser
    from ks_gen.rules.container_host import RULE

    cfg = minimal_cfg.model_copy(
        update={
            "containers": Containers(
                enabled=True,
                users=[
                    ContainerUser(
                        name="webapp",
                        authorized_keys=[
                            "ssh-ed25519 KEY_ONE webapp@bastion",
                            "ssh-ed25519 KEY_TWO webapp@laptop",
                        ],
                    ),
                ],
            )
        }
    )
    body = RULE.emit_post(cfg)

    assert "ssh-ed25519 KEY_ONE webapp@bastion" in body
    assert "ssh-ed25519 KEY_TWO webapp@laptop" in body


def test_container_host_emit_post_no_quadlet_scaffold(minimal_cfg):
    # Kickstart-time provisioning never passes -q (Quadlet scaffold is
    # post-install only).
    from ks_gen.config import Containers, ContainerUser
    from ks_gen.rules.container_host import RULE

    cfg = minimal_cfg.model_copy(
        update={
            "containers": Containers(
                enabled=True,
                users=[ContainerUser(name="webapp", authorized_keys=["ssh-ed25519 K w@h"])],
            )
        }
    )
    body = RULE.emit_post(cfg)

    # Spot-check: no '-q' flag on any script call
    for line in body.splitlines():
        if line.strip().startswith("/root/create-rootless-user.sh "):
            assert " -q" not in line
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config_schema.py -k "container_host_emit_post" -v
```

Expected: 5 tests fail (emit_post returns empty string).

- [ ] **Step 3: Implement emit_post**

Replace the `_Rule.emit_post` method body in `src/ks_gen/rules/container_host.py`. Also add the `_emit` helper above the `_Rule` class:

```python
def _emit(cfg: HostConfig) -> str:
    parts: list[str] = []

    # Drop the helper script to /root for operator post-install use
    parts.append("# Install the rootless-container-user helper at /root for post-install use")
    parts.append("cat > /root/create-rootless-user.sh <<'__KS_GEN_EOF__'")
    parts.append(_SCRIPT.rstrip())
    parts.append("__KS_GEN_EOF__")
    parts.append("chown root:root /root/create-rootless-user.sh")
    parts.append("chmod 0550 /root/create-rootless-user.sh")
    parts.append("")

    # System-wide storage.conf: pin rootless graphroot under the mirror
    parts.append(
        "# System-wide storage.conf -- pins rootless graphroot to the /srv/containers mirror"
    )
    parts.append("install -d -m 0755 /etc/containers")
    parts.append("cat > /etc/containers/storage.conf <<'__KS_GEN_EOF__'")
    parts.append("[storage]")
    parts.append('driver = "overlay"')
    parts.append('rootless_storage_path = "/srv/containers/$USER/storage"')
    parts.append("__KS_GEN_EOF__")
    parts.append("chmod 0644 /etc/containers/storage.conf")

    # Provision each configured container user via the same script the
    # operator will use post-install. -l (linger) always on; -q (Quadlet
    # scaffold) intentionally off for kickstart-time creation.
    for u in cfg.containers.users:
        gecos = u.gecos or u.name
        parts.append("")
        parts.append(f"# Provision container user: {u.name}")
        parts.append(f'/root/create-rootless-user.sh -l -c "{gecos}" {u.name}')
        parts.append(f"install -d -m 0700 -o {u.name} -g {u.name} /home/{u.name}/.ssh")
        parts.append(f"cat > /home/{u.name}/.ssh/authorized_keys <<'__KS_GEN_EOF__'")
        parts.extend(u.authorized_keys)
        parts.append("__KS_GEN_EOF__")
        parts.append(f"chown {u.name}:{u.name} /home/{u.name}/.ssh/authorized_keys")
        parts.append(f"chmod 0600 /home/{u.name}/.ssh/authorized_keys")
        parts.append(f"restorecon -R /home/{u.name}/.ssh")

    return "\n".join(parts) + "\n"
```

And in `_Rule`:

```python
    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config_schema.py -k "container_host_emit_post" -v
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: 5 tests PASS; full suite green; mypy clean.

- [ ] **Step 5: Commit**

```powershell
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -am "feat(rules): implement container_host.emit_post with per-user provisioning"
```

---

### Task 7: Template change — auto-inject `/srv/containers` logvol

**Files:**
- Modify: `src/ks_gen/templates/ks.cfg.j2`

No new tests in this task — the existing 13 golden tests (12 pre-#65 + the `test_lean_preset` added in #65) must remain green because every existing fixture has `containers.enabled=False` by default. The container-host golden coverage lands in Task 8.

- [ ] **Step 1: Update the template**

In `src/ks_gen/templates/ks.cfg.j2`, locate the existing partition include block (around line 34-38):

```jinja
{% if cfg.disk.layout -%}
{% include 'partials/partitioning_layout.j2' %}
{% else -%}
{% include 'partials/partitioning_' ~ cfg.disk.preset.value ~ '.j2' %}
{% endif %}
```

Add the container logvol block immediately after, before the `services` line:

```jinja
{% if cfg.disk.layout -%}
{% include 'partials/partitioning_layout.j2' %}
{% else -%}
{% include 'partials/partitioning_' ~ cfg.disk.preset.value ~ '.j2' %}
{% endif %}
{% if cfg.containers.enabled -%}
logvol /srv/containers --vgname={{ cfg.disk.layout.vg_name if cfg.disk.layout else 'vg_root' }} --name=containers --fstype=xfs --size={{ cfg.containers.volume.size_mib }} --fsoptions="{{ cfg.containers.volume.fsoptions }}"
{% endif %}
services --enabled=chronyd,firewalld,auditd,rsyslog,sshd
```

- [ ] **Step 2: Run the full snapshot suite — no drift**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/golden/ -v
```

Expected: 13 tests PASS with zero snapshot updates. (`containers.enabled` defaults to False, so the new Jinja block produces no output for any existing fixture.)

- [ ] **Step 3: Run mypy**

```powershell
.\.venv\Scripts\python.exe -m mypy
```

Expected: `Success: no issues found`.

- [ ] **Step 4: Commit**

```powershell
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -am "feat(templates): auto-inject /srv/containers logvol when containers.enabled"
```

---

### Task 8: Golden coverage — container-host and container-host + lean

**Files:**
- Create: `tests/golden/container-host.host.yaml`
- Create: `tests/golden/test_container_host.py`
- Create: `tests/golden/__snapshots__/test_container_host.ambr` (generated)
- Create: `tests/golden/container-host-lean.host.yaml`
- Create: `tests/golden/test_container_host_lean.py`
- Create: `tests/golden/__snapshots__/test_container_host_lean.ambr` (generated)

This task ships two new fixtures and two new tests. The lean-composed fixture proves #65 and #66 compose orthogonally — its `%packages` block should be the standard container-host packages set, but with `@standard` stripped and the lean compensating packages added (just like `test_lean_preset` did relative to `test_minimal_dhcp`).

- [ ] **Step 1: Create the container-host fixture**

Write `tests/golden/container-host.host.yaml`:

```yaml
system:
  hostname: web01.example.com
user:
  admin:
    name: opsadmin
    authorized_keys:
      - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEYcontainerhost test@laptop"
    sudo: nopasswd_yes
containers:
  enabled: true
  users:
    - name: webapp
      gecos: "Web app workloads"
      authorized_keys:
        - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEYwebapp1 webapp@bastion"
        - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEYwebapp2 webapp@laptop"
    - name: dbproxy
      authorized_keys:
        - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEYdbproxy dbproxy@bastion"
```

- [ ] **Step 2: Create the container-host test**

Write `tests/golden/test_container_host.py`:

```python
import re
from pathlib import Path

from ks_gen.loader import load_host_config
from ks_gen.writer import build_bundle


def _normalize(text: str) -> str:
    text = re.sub(r"Generated by ks-gen v\S+ on \S+", "Generated by ks-gen vSNAP on SNAP", text)
    text = re.sub(r"Generated: \S+", "Generated: SNAP", text)
    text = re.sub(r'<xccdf:version time="[^"]+"', '<xccdf:version time="SNAP"', text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def test_container_host(snapshot):
    yaml_path = Path(__file__).parent / "container-host.host.yaml"
    cfg = load_host_config(yaml_path, sets=[])
    bundle = build_bundle(cfg)
    assert _normalize(bundle.ks_cfg) == snapshot(name="ks.cfg")
    assert _normalize(bundle.tailoring_xml) == snapshot(name="tailoring.xml")
    assert _normalize(bundle.exceptions_md) == snapshot(name="exceptions.md")
```

- [ ] **Step 3: Generate the container-host snapshot**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/golden/test_container_host.py --snapshot-update -v
```

Expected: snapshot file created; test passes on first run.

- [ ] **Step 4: Inspect the container-host snapshot diff vs `test_minimal_dhcp`**

```powershell
git diff --no-index tests/golden/__snapshots__/test_minimal_dhcp.ambr tests/golden/__snapshots__/test_container_host.ambr
```

Expected differences AND ONLY these:
- Cosmetic: snapshot test name in header, SSH key strings
- `%packages` block: the 6 podman-stack packages appear (after the existing required, before exclusions)
- Partition block: one new line `logvol /srv/containers --vgname=vg_root --name=containers --fstype=xfs --size=20480 --fsoptions="nodev,nosuid"` appears after the swap LV
- `%post` block: a new `# ===== container_host =====` section after the existing rule blocks, containing:
  - The full `create-rootless-user.sh` heredoc (250+ lines)
  - The `storage.conf` heredoc
  - `webapp` provisioning (script call + authorized_keys heredoc with both keys)
  - `dbproxy` provisioning (script call + authorized_keys heredoc with one key)

No drift in network, services, tailoring.xml, or other rule blocks. If anything else differs, STOP and investigate before continuing.

- [ ] **Step 5: Create the lean-composed fixture**

Write `tests/golden/container-host-lean.host.yaml`:

```yaml
system:
  hostname: web01.example.com
user:
  admin:
    name: opsadmin
    authorized_keys:
      - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEYcontainerhostlean test@laptop"
    sudo: nopasswd_yes
packages:
  preset: lean
containers:
  enabled: true
  users:
    - name: webapp
      gecos: "Web app workloads"
      authorized_keys:
        - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEYwebapplean webapp@bastion"
```

- [ ] **Step 6: Create the lean-composed test**

Write `tests/golden/test_container_host_lean.py`:

```python
import re
from pathlib import Path

from ks_gen.loader import load_host_config
from ks_gen.writer import build_bundle


def _normalize(text: str) -> str:
    text = re.sub(r"Generated by ks-gen v\S+ on \S+", "Generated by ks-gen vSNAP on SNAP", text)
    text = re.sub(r"Generated: \S+", "Generated: SNAP", text)
    text = re.sub(r'<xccdf:version time="[^"]+"', '<xccdf:version time="SNAP"', text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def test_container_host_lean(snapshot):
    yaml_path = Path(__file__).parent / "container-host-lean.host.yaml"
    cfg = load_host_config(yaml_path, sets=[])
    bundle = build_bundle(cfg)
    assert _normalize(bundle.ks_cfg) == snapshot(name="ks.cfg")
    assert _normalize(bundle.tailoring_xml) == snapshot(name="tailoring.xml")
    assert _normalize(bundle.exceptions_md) == snapshot(name="exceptions.md")
```

- [ ] **Step 7: Generate the lean-composed snapshot**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/golden/test_container_host_lean.py --snapshot-update -v
```

Expected: snapshot file created; test passes.

- [ ] **Step 8: Inspect the lean-composed snapshot diff vs `test_container_host`**

```powershell
git diff --no-index tests/golden/__snapshots__/test_container_host.ambr tests/golden/__snapshots__/test_container_host_lean.ambr
```

Expected differences AND ONLY these:
- Cosmetic: test name, SSH key, one user fewer (dbproxy absent in the lean fixture)
- `%packages` block: `@standard` removed; `logrotate`, `postfix`, `cronie`, `crontabs`, `parted` appear (from the lean preset)
- `%post` block: dbproxy provisioning block absent

No other drift. The container-host post block and the `/srv/containers` partition line should be byte-identical.

- [ ] **Step 9: Re-run the full golden suite**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/golden/ -v
```

Expected: 15 tests PASS (13 existing + 2 new), 0 snapshot updates.

- [ ] **Step 10: Commit**

```powershell
git add tests/golden/container-host.host.yaml tests/golden/test_container_host.py tests/golden/__snapshots__/test_container_host.ambr tests/golden/container-host-lean.host.yaml tests/golden/test_container_host_lean.py tests/golden/__snapshots__/test_container_host_lean.ambr
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -m "test(golden): cover containers.enabled, including composition with packages.preset=lean"
```

---

### Task 9: Document `containers:` in MANUAL.md

**Files:**
- Modify: `MANUAL.md` (insert a new section 4.10.5 or 4.11 — placement and exact section number to be chosen so it sits between the existing 4.10 `packages` and the current 4.11 `overrides`)

This task is documentation-only. The section number depends on prior MANUAL.md state; pick the next free number that fits before the existing `overrides` section.

- [ ] **Step 1: Locate the existing section bounds**

Read `MANUAL.md` around section 4.10 (packages) and 4.11 (overrides). Note the line where 4.10 ends and 4.11 begins. The new section goes there.

- [ ] **Step 2: Insert the new section**

Insert the following content immediately before the `### 4.11 overrides — the conflict-point matrix` line (renumber subsequent sections if needed — but the existing structure may already allow inserting a 4.10.5 sub-section instead of pushing 4.11 → 4.12; prefer the smallest-disruption choice):

````markdown
### 4.11 `containers` — rootless container host preset

```yaml
containers:
  enabled: true                  # default false
  users:                         # may be empty; script still installs at /root
    - name: webapp
      gecos: "Web app workloads"
      authorized_keys:
        - "ssh-ed25519 AAAA... webapp@bastion"
        - "ssh-ed25519 BBBB... webapp@laptop"
    - name: dbproxy
      authorized_keys:
        - "ssh-ed25519 CCCC... dbproxy@bastion"
  volume:
    size: "20G"                  # default 20G; pattern ^\d+(M|G|T)$
    fsoptions: "nodev,nosuid"    # default; `noexec` token is rejected
```

When `enabled: true`, the generated kickstart:

1. Auto-injects an extra logvol `/srv/containers` (XFS, sized per `volume.size`, mounted with `volume.fsoptions`) into the partition layout. Works for both `disk.preset` and `disk.layout` shapes.
2. Adds the rootless-podman package stack to `%packages`: `podman`, `crun`, `slirp4netns`, `fuse-overlayfs`, `containers-common`, `podman-plugins`.
3. Drops `/root/create-rootless-user.sh` (mode 0550, root:root) — the same script the kickstart uses to create users is available to the operator for post-install user provisioning.
4. Writes `/etc/containers/storage.conf` with `rootless_storage_path = "/srv/containers/$USER/storage"` so podman lands new users' graphroot on the mirror automatically.
5. For each `users[]` entry: calls the script with `-l` (linger always-on) and the configured `gecos`, then writes the full `authorized_keys` file. Container users have no sudo, no wheel group, and a real shell (`/bin/bash`) for SSH login.

#### Recommended pairing with `packages.preset: lean`

A container-host typically wants the lean package baseline (see §4.10). The two presets compose orthogonally:

```yaml
packages:
  preset: lean
containers:
  enabled: true
  users:
    - name: webapp
      authorized_keys: ["..."]
```

#### Post-install user provisioning

After install, the operator can add additional rootless container users with the same script kickstart used:

```bash
sudo /root/create-rootless-user.sh -l -c "Analytics workloads" analytics
# add a public key:
sudo /root/create-rootless-user.sh -l -k "$(cat ~/.ssh/id_ed25519.pub)" deploy
# scaffold a starter Quadlet set for testing:
sudo /root/create-rootless-user.sh -l -q -c "Sandbox" sandbox
```

The script is idempotent — re-running it on an existing user is safe and will just (re)apply any options you pass.

#### Constraints

- Container users' names must be distinct from `user.admin.name` (container users are for rootless workloads; admins manage the host).
- If you're using `disk.layout` (not `disk.preset`), don't add a `/srv/containers` LV yourself — the container-host preset auto-injects it.
- `volume.fsoptions` rejects `noexec`. Container image layers must execute.

````

- [ ] **Step 3: Sanity-check the manual still loads cleanly**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: full suite PASS (docs change should not affect any test).

- [ ] **Step 4: Commit**

```powershell
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -am "docs(manual): document containers config block and post-install provisioning"
```

---

### Task 10: Final CI parity + PR

**Files:** none (verification + git operations only)

- [ ] **Step 1: Run the full local CI parity chain**

```powershell
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest -q
```

Expected:
- `All checks passed!`
- `N files already formatted`
- `Success: no issues found in <50 source files`
- All tests pass (count = 562 from #65 baseline + new tests added in this PR; specific count depends on whether #65 has merged)

If `ruff format --check` fails: run `.\.venv\Scripts\python.exe -m ruff format src tests`, re-verify with `--check`, commit as `style:`.

- [ ] **Step 2: Push the branch**

```powershell
git push -u origin <branch-name>
```

(Branch name is whatever worktree branch the implementer is on — likely something like `feat-66-container-host-preset`.)

- [ ] **Step 3: Open the PR**

```powershell
gh pr create --title "feat(containers): add container-host preset with /srv/containers and rootless user provisioning" --body @'
## Summary

- Adds `containers:` config block to `host.yaml`. Default `enabled: false` — no behavior change for existing configs.
- When `enabled: true`: auto-injects `/srv/containers` XFS logvol, installs rootless-podman package stack, drops `/root/create-rootless-user.sh` (mode 0550), writes `/etc/containers/storage.conf`, and provisions each configured container user via the same script.
- New `Containers`/`ContainerUser`/`ContainerVolume` pydantic models gated by `containers.enabled`. `ContainerVolume.fsoptions` rejects `noexec` (container layers must execute). Cross-cutting `HostConfig` validators reject admin-name conflicts and `disk.layout` LVs that already mount `/srv/containers`.
- The shipped `create-rootless-user.sh` is the single source of truth for user provisioning: same script runs at kickstart time and post-install for the operator. Idempotent.
- Composes orthogonally with `packages.preset: lean` (#65) — golden test `test_container_host_lean` covers the recommended pairing.
- Documented in MANUAL.md §4.11.

Closes #66. Tracked under #67.

## Test plan

- [x] `ruff check src tests` clean
- [x] `ruff format --check src tests` clean
- [x] `mypy` clean
- [x] `pytest -q` — all tests pass, all snapshots pass
- [x] Unit tests cover: model defaults, size_mib parsing (M/G/T), fsoptions noexec rejection, name pattern + root rejection, min_length=1 keys, duplicate-name rejection (when enabled), admin-name conflict rejection, disk.layout `/srv/containers` conflict rejection, rule applies/emit_packages/emit_post markers, multi-key handling.
- [x] Golden tests: `test_container_host` diff vs `test_minimal_dhcp` shows ONLY the partition + `%packages` + `%post` additions. `test_container_host_lean` diff vs `test_container_host` shows ONLY the lean preset effect on `%packages`.
- [ ] Install-regression harness (`.scratch/install-regression/`) — strongly recommended before merge per project CLAUDE.md; this PR touches `%packages`, partition layout, AND `%post` rule emission. Acceptance checks listed in the design spec (`docs/superpowers/specs/2026-06-13-container-host-preset-design.md` §Testing).
'@
```

- [ ] **Step 4: Report PR URL**

Expected: a `https://github.com/SupremeCommanderHedgehog/ks-gen/pull/<N>` URL. Report it to the user.

---

## Self-review notes

- **Spec coverage:**
  - Activation surface (top-level `containers:` block) — Task 3
  - Disk integration (auto-inject logvol) — Task 7
  - User scope (container users distinct from admin) — Tasks 2, 4
  - Container-user access (SSH login w/ authorized_keys) — Task 2 (model), Task 6 (emit_post writes keys)
  - Provisioning logic (single script, kickstart + operator) — Tasks 5, 6
  - Quadlet scaffold off at kickstart — Task 6 (test asserts no -q flag)
  - Linger always on at kickstart — Task 6 (test asserts -l flag)
  - All seven validation rules from spec §Validation rules — Tasks 1, 2, 3, 4
  - Testing — Tasks 1-8 (unit + golden), Task 10 (install-regression flagged in PR)

- **Type consistency:** field names (`size`, `fsoptions`, `size_mib`, `name`, `gecos`, `authorized_keys`, `enabled`, `users`, `volume`) match across config.py, the rule, the template, and tests. The rule's `_emit` function refers to `cfg.containers.users`, `u.name`, `u.gecos`, `u.authorized_keys` — all defined in Tasks 2-3.

- **No placeholders:** all code blocks complete; commands have expected output; commit messages exact.

- **YAGNI:** no extra fields (no `containers.optional_packages`, no `containers.extra_users`, no `volume.extra_logvols`). The `users[]` list can be empty without breaking; the script is the single extension point for the operator.
