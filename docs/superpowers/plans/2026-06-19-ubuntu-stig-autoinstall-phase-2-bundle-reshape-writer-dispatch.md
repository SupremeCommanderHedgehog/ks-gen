# Ubuntu 24.04 STIG Autoinstall Phase 2 — Bundle Reshape and Writer Dispatch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reshape the `Bundle` dataclass so it can carry either an alma9 `ks.cfg` payload or an ubuntu2404 `user-data`+`meta-data` payload, and route `build_bundle` / `write_bundle` / `cli.gen` through a distro discriminator — emitting an empty/placeholder ubuntu2404 bundle that is structurally valid but contains no rule output yet.

**Architecture:** Phase 2 of the Ubuntu STIG autoinstall roadmap (spec §11, item 2). Phase 1 (PR #90, squash `60d83a1`) added `cfg.distro` and per-distro rule discovery; phase 2 makes the writer act on it. `Bundle` becomes a discriminated dataclass: shared fields (`distro`, `tailoring_xml`, `host_yaml`, `exceptions_md`) plus one of two optional payload sets (`ks_cfg` for alma9, `user_data`+`meta_data` for ubuntu2404). `build_bundle` dispatches on `cfg.distro`; `write_bundle` writes distro-appropriate files; `cli.gen` skips the kickstart-shaped `lint_kickstart` call for ubuntu2404. Existing alma9 behavior is byte-identical — every golden snapshot under `tests/golden/__snapshots__/` is unchanged.

**Tech Stack:** Python 3.11+, pydantic 2, jinja2 (existing `src/ks_gen/templates/` dir), syrupy snapshots (`tests/golden/__snapshots__/`). No new runtime dependencies.

**Branch:** This plan assumes the controller has created a feature branch (e.g. `feat/phase-2-bundle-reshape-writer-dispatch`) checked out from `main` at v0.14.0 (commit `919244b` or later). Tasks 1–4 commit to this branch; Task 5 pushes and opens a PR against `main`.

**Acceptance bar:** zero behavior change for existing alma9 users; every golden snapshot byte-identical to the post-phase-1 main branch.

---

## File Structure

**Create (3 files):**

- `src/ks_gen/rules/ubuntu2404/__init__.py` — empty package marker so phase 3 has a home for ubuntu rule modules. `load_rules("ubuntu2404")` continues to return `[]` (no module files yet, just an empty package).
- `src/ks_gen/templates/user-data.j2` — minimal Subiquity autoinstall + cloud-init template. Emits `#cloud-config` header, `autoinstall: version: 1` block, an `identity:` block derived from `cfg.system.hostname` + `cfg.user.admin.name` with a locked password, and an empty `late-commands: []` list. Phase 3 will populate `late-commands`.
- `src/ks_gen/templates/meta-data.j2` — cloud-init `instance-id` + `local-hostname` template, both derived from `cfg.system.hostname`.

**Modify (3 files):**

- `src/ks_gen/writer.py` — Reshape `Bundle` dataclass with `distro` discriminator + optional payload fields + `__post_init__` invariant. Refactor `build_bundle` into a top-level dispatch with two private helpers `_build_alma9_bundle(cfg)` (current body, renamed) and `_build_ubuntu2404_bundle(cfg)` (new). Update `write_bundle` to dispatch on `bundle.distro`.
- `src/ks_gen/skeleton.py` — Add `render_user_data(cfg)` and `render_meta_data(cfg)` functions alongside the existing `render_skeleton`.
- `src/ks_gen/cli.py` — `gen()` skips the `lint_kickstart` call when `bundle.distro != "alma9"`. `new_cmd` is untouched (wizard always produces `distro: alma9` today; the guard there is YAGNI until the wizard learns to prompt for distro in a later phase).

**New test files (2):**

- `tests/test_skeleton_ubuntu.py` — Unit tests for `render_user_data` and `render_meta_data` (parses output as YAML, asserts on shape).
- `tests/test_cli_gen_ubuntu.py` — Integration test that `ks-gen gen` against a `distro: ubuntu2404` config writes the expected five files to disk and exits 0.

**Append to existing test files (2):**

- `tests/test_writer.py` — `Bundle` invariant tests, `build_bundle` dispatch tests, `write_bundle` dispatch tests.
- `tests/test_registry.py` — confirm the new empty package exists.

---

### Task 1: Empty `rules/ubuntu2404/` package + `Bundle` dataclass reshape

**Files:**
- Create: `src/ks_gen/rules/ubuntu2404/__init__.py`
- Modify: `src/ks_gen/writer.py` — replace `Bundle` dataclass, add `Literal` import, update existing `Bundle(...)` constructor call in `build_bundle`
- Test: `tests/test_writer.py` (append), `tests/test_registry.py` (append)

**Goal:** Lay the foundation — an empty ubuntu2404 rule package and a reshaped `Bundle` dataclass that enforces invariants at construction time.

- [ ] **Step 1: Create the empty ubuntu2404 package marker**

PowerShell:
```powershell
New-Item -ItemType File -Path src\ks_gen\rules\ubuntu2404\__init__.py -Force | Out-Null
```

Verify:
```powershell
Test-Path src\ks_gen\rules\ubuntu2404\__init__.py
```
Expected: `True`. The file is empty (0 bytes).

- [ ] **Step 2: Add a regression test that the package now exists**

Append to `tests/test_registry.py`:

```python
def test_registry_ubuntu2404_package_exists():
    """ubuntu2404 package marker exists post-phase-2 so phase 3 has a home.

    Before this file existed, `load_rules('ubuntu2404')` returned [] via the
    `ModuleNotFoundError` branch; now it returns [] via a real (empty)
    package iterated by pkgutil.
    """
    import importlib

    pkg = importlib.import_module("ks_gen.rules.ubuntu2404")
    assert pkg.__path__  # truthy => is a real package
```

- [ ] **Step 3: Run the registry tests (expect PASS)**

Run: `pytest tests/test_registry.py -v`
Expected: all four `test_registry_*` tests PASS. `test_registry_ubuntu2404_returns_empty_list` still passes because empty package → 0 modules → empty list.

- [ ] **Step 4: Write failing tests for the reshaped `Bundle` invariants**

Append to `tests/test_writer.py`:

```python
import pytest

from ks_gen.writer import Bundle


def test_bundle_alma9_requires_ks_cfg_and_rejects_user_data():
    # alma9 bundle MUST have ks_cfg set; MUST NOT have user_data or meta_data.
    Bundle(
        distro="alma9",
        tailoring_xml="<x/>",
        host_yaml="meta: {}\n",
        exceptions_md="# x\n",
        ks_cfg="cmdline\n%end\n",
    )  # OK
    with pytest.raises(ValueError, match="alma9 bundle requires ks_cfg"):
        Bundle(
            distro="alma9",
            tailoring_xml="<x/>",
            host_yaml="meta: {}\n",
            exceptions_md="# x\n",
            ks_cfg=None,
        )
    with pytest.raises(ValueError, match="alma9 bundle must not set user_data"):
        Bundle(
            distro="alma9",
            tailoring_xml="<x/>",
            host_yaml="meta: {}\n",
            exceptions_md="# x\n",
            ks_cfg="cmdline\n",
            user_data="#cloud-config\n",
        )


def test_bundle_ubuntu2404_requires_user_data_meta_data_and_rejects_ks_cfg():
    # ubuntu2404 bundle MUST have user_data AND meta_data; MUST NOT have ks_cfg.
    Bundle(
        distro="ubuntu2404",
        tailoring_xml="<x/>",
        host_yaml="meta: {}\n",
        exceptions_md="# x\n",
        user_data="#cloud-config\nautoinstall: {version: 1}\n",
        meta_data="instance-id: x\n",
    )  # OK
    with pytest.raises(ValueError, match="ubuntu2404 bundle requires user_data"):
        Bundle(
            distro="ubuntu2404",
            tailoring_xml="<x/>",
            host_yaml="meta: {}\n",
            exceptions_md="# x\n",
            user_data=None,
            meta_data="instance-id: x\n",
        )
    with pytest.raises(ValueError, match="ubuntu2404 bundle requires meta_data"):
        Bundle(
            distro="ubuntu2404",
            tailoring_xml="<x/>",
            host_yaml="meta: {}\n",
            exceptions_md="# x\n",
            user_data="#cloud-config\n",
            meta_data=None,
        )
    with pytest.raises(ValueError, match="ubuntu2404 bundle must not set ks_cfg"):
        Bundle(
            distro="ubuntu2404",
            tailoring_xml="<x/>",
            host_yaml="meta: {}\n",
            exceptions_md="# x\n",
            user_data="#cloud-config\n",
            meta_data="instance-id: x\n",
            ks_cfg="cmdline\n",
        )
```

- [ ] **Step 5: Run the failing tests**

Run: `pytest tests/test_writer.py::test_bundle_alma9_requires_ks_cfg_and_rejects_user_data tests/test_writer.py::test_bundle_ubuntu2404_requires_user_data_meta_data_and_rejects_ks_cfg -v`
Expected: both FAIL with `TypeError: Bundle.__init__() got an unexpected keyword argument 'distro'` (the dataclass doesn't have these fields yet).

- [ ] **Step 6: Reshape the `Bundle` dataclass and add the `Literal` import**

Edit `src/ks_gen/writer.py`.

First, add the `Literal` import. Find the existing line `from pathlib import Path` (line 4) and immediately after it add:

```python
from typing import Literal
```

Second, replace the existing `Bundle` definition (currently lines 16–22, the `@dataclass(frozen=True)\nclass Bundle:\n    ks_cfg: str\n    tailoring_xml: str\n    host_yaml: str\n    exceptions_md: str` block) with:

```python
@dataclass(frozen=True)
class Bundle:
    """Generated artifacts for one host.

    Fields split into a shared core (always populated) and a distro-specific
    payload (exactly one set populated per `distro`). `__post_init__` enforces
    the invariant so callers downstream of construction can rely on it.
    """

    distro: Literal["alma9", "ubuntu2404"]
    tailoring_xml: str
    host_yaml: str
    exceptions_md: str
    ks_cfg: str | None = None
    user_data: str | None = None
    meta_data: str | None = None

    def __post_init__(self) -> None:
        if self.distro == "alma9":
            if self.ks_cfg is None:
                raise ValueError("alma9 bundle requires ks_cfg")
            if self.user_data is not None or self.meta_data is not None:
                raise ValueError("alma9 bundle must not set user_data/meta_data")
        elif self.distro == "ubuntu2404":
            if self.user_data is None:
                raise ValueError("ubuntu2404 bundle requires user_data")
            if self.meta_data is None:
                raise ValueError("ubuntu2404 bundle requires meta_data")
            if self.ks_cfg is not None:
                raise ValueError("ubuntu2404 bundle must not set ks_cfg")
```

- [ ] **Step 7: Update the existing `build_bundle` constructor call to pass `distro="alma9"`**

In `src/ks_gen/writer.py`, find the existing `return Bundle(...)` block inside `build_bundle` (currently lines 66–71). Replace:

```python
    return Bundle(
        ks_cfg=ks_cfg,
        tailoring_xml=tailoring_xml,
        host_yaml=host_yaml,
        exceptions_md=exceptions_md,
    )
```

with:

```python
    return Bundle(
        distro="alma9",
        ks_cfg=ks_cfg,
        tailoring_xml=tailoring_xml,
        host_yaml=host_yaml,
        exceptions_md=exceptions_md,
    )
```

- [ ] **Step 8: Run the Bundle invariant tests (expect PASS)**

Run: `pytest tests/test_writer.py::test_bundle_alma9_requires_ks_cfg_and_rejects_user_data tests/test_writer.py::test_bundle_ubuntu2404_requires_user_data_meta_data_and_rejects_ks_cfg -v`
Expected: both PASS.

- [ ] **Step 9: Run the full existing test suite to confirm no regressions**

Run: `pytest -q`
Expected: all tests pass. Every existing test constructs Bundles via `build_bundle(cfg)`, which now sets `distro="alma9"` automatically. Golden snapshots are byte-identical because the only change is a new field, not a content change.

- [ ] **Step 10: Commit**

```powershell
git add src\ks_gen\rules\ubuntu2404\__init__.py src\ks_gen\writer.py tests\test_writer.py tests\test_registry.py
git -c user.email="github.v5f9w@bitbucket.onl" `
    -c user.signingkey=BE707B220C995478 `
    commit -S -m "feat(writer): reshape Bundle with distro discriminator + invariants

Add Bundle.distro Literal field plus optional user_data/meta_data payload
fields; ks_cfg becomes Optional. __post_init__ enforces the invariant that
alma9 bundles carry ks_cfg and ubuntu2404 bundles carry user_data+meta_data.
build_bundle now sets distro=alma9 explicitly. No behavior change for
alma9 consumers; golden snapshots byte-identical.

Bootstrap empty ks_gen.rules.ubuntu2404 package so phase 3 rule ports have
a home. load_rules('ubuntu2404') continues to return []."
```

---

### Task 2: Ubuntu skeleton templates + renderers

**Files:**
- Create: `src/ks_gen/templates/user-data.j2`
- Create: `src/ks_gen/templates/meta-data.j2`
- Modify: `src/ks_gen/skeleton.py` (append two new render functions after `render_skeleton`)
- Test: `tests/test_skeleton_ubuntu.py`

**Goal:** Two Jinja templates and two rendering functions that produce a minimal, syntactically-valid Subiquity autoinstall `user-data` plus cloud-init NoCloud `meta-data` from a `HostConfig`.

- [ ] **Step 1: Write the failing render tests**

Create `tests/test_skeleton_ubuntu.py`:

```python
import yaml

from ks_gen.config import AdminUser, HostConfig, System, User
from ks_gen.skeleton import render_meta_data, render_user_data


def _ubuntu_cfg(hostname: str = "u2404-host", admin: str = "ops") -> HostConfig:
    return HostConfig(
        distro="ubuntu2404",
        system=System(hostname=hostname),
        user=User(
            admin=AdminUser(
                name=admin,
                authorized_keys=["ssh-ed25519 AAAA a@b"],
                sudo="nopasswd_yes",
            )
        ),
    )


def test_render_user_data_starts_with_cloud_config_header():
    text = render_user_data(_ubuntu_cfg())
    assert text.splitlines()[0] == "#cloud-config"


def test_render_user_data_parses_as_yaml_with_autoinstall_v1():
    text = render_user_data(_ubuntu_cfg())
    doc = yaml.safe_load(text)
    assert isinstance(doc, dict)
    assert "autoinstall" in doc
    assert doc["autoinstall"]["version"] == 1


def test_render_user_data_carries_hostname_and_admin_username():
    text = render_user_data(_ubuntu_cfg(hostname="u24-test", admin="opsadmin"))
    doc = yaml.safe_load(text)
    identity = doc["autoinstall"]["identity"]
    assert identity["hostname"] == "u24-test"
    assert identity["username"] == "opsadmin"


def test_render_user_data_password_is_locked():
    # Locked password ("*") forces SSH-key-only — matches the alma9 path's
    # rootpw --lock / user --lock convention. Phase 3 will derive this
    # from cfg.user.admin.password (None => locked, otherwise hash).
    text = render_user_data(_ubuntu_cfg())
    doc = yaml.safe_load(text)
    assert doc["autoinstall"]["identity"]["password"] == "*"


def test_render_user_data_late_commands_is_empty_list():
    # Phase 2 emits a placeholder bundle: no rules yet, no late-commands.
    # Phase 3 will populate this list from the ubuntu2404 rule registry.
    text = render_user_data(_ubuntu_cfg())
    doc = yaml.safe_load(text)
    assert doc["autoinstall"]["late-commands"] == []


def test_render_meta_data_carries_hostname():
    text = render_meta_data(_ubuntu_cfg(hostname="u24-meta-test"))
    doc = yaml.safe_load(text)
    assert doc["instance-id"] == "u24-meta-test"
    assert doc["local-hostname"] == "u24-meta-test"
```

- [ ] **Step 2: Run the failing tests**

Run: `pytest tests/test_skeleton_ubuntu.py -v`
Expected: all six FAIL with `ImportError: cannot import name 'render_user_data' from 'ks_gen.skeleton'`.

- [ ] **Step 3: Create the user-data Jinja template**

Create `src/ks_gen/templates/user-data.j2` with this exact content (trailing newline included):

```jinja
#cloud-config
autoinstall:
  version: 1
  identity:
    hostname: {{ cfg.system.hostname }}
    realname: {{ cfg.user.admin.name }}
    username: {{ cfg.user.admin.name }}
    password: "*"
  late-commands: []
```

- [ ] **Step 4: Create the meta-data Jinja template**

Create `src/ks_gen/templates/meta-data.j2` with this exact content (trailing newline included):

```jinja
instance-id: {{ cfg.system.hostname }}
local-hostname: {{ cfg.system.hostname }}
```

- [ ] **Step 5: Add the render functions to `skeleton.py`**

Edit `src/ks_gen/skeleton.py`. Append after the existing `render_skeleton` function (so the file ends with these two new functions):

```python


def render_user_data(cfg: HostConfig) -> str:
    """Render the autoinstall + cloud-init user-data for an ubuntu2404 host.

    Phase 2: emits a minimal placeholder (identity + empty late-commands).
    Phase 3 will populate late-commands from the ubuntu2404 rule registry.
    """
    env = _env()
    template = env.get_template("user-data.j2")
    return template.render(cfg=cfg)


def render_meta_data(cfg: HostConfig) -> str:
    """Render the cloud-init NoCloud meta-data for an ubuntu2404 host."""
    env = _env()
    template = env.get_template("meta-data.j2")
    return template.render(cfg=cfg)
```

- [ ] **Step 6: Run the tests (expect PASS)**

Run: `pytest tests/test_skeleton_ubuntu.py -v`
Expected: all six PASS. Confirms the templates render, parse as YAML, and carry the expected fields.

- [ ] **Step 7: Commit**

```powershell
git add src\ks_gen\templates\user-data.j2 src\ks_gen\templates\meta-data.j2 src\ks_gen\skeleton.py tests\test_skeleton_ubuntu.py
git -c user.email="github.v5f9w@bitbucket.onl" `
    -c user.signingkey=BE707B220C995478 `
    commit -S -m "feat(skeleton): add user-data + meta-data templates and renderers

Minimal Subiquity autoinstall + cloud-init NoCloud templates for the
ubuntu2404 path. user-data emits a placeholder identity block with a
locked password and an empty late-commands list; meta-data emits
instance-id + local-hostname keyed off cfg.system.hostname.

Phase 3 will populate late-commands from the ubuntu2404 rule registry."
```

---

### Task 3: `build_bundle` distro dispatch

**Files:**
- Modify: `src/ks_gen/writer.py` — refactor `build_bundle`, add `_build_alma9_bundle` and `_build_ubuntu2404_bundle` helpers, expand imports
- Test: `tests/test_writer.py` (append)

**Goal:** Refactor `build_bundle` so it dispatches on `cfg.distro`. The existing body becomes `_build_alma9_bundle`. The new `_build_ubuntu2404_bundle` builds with empty rules (since no ubuntu rules exist yet) → empty tailoring, placeholder user-data, placeholder meta-data. The alma9 path must be byte-identical to today.

- [ ] **Step 1: Write the failing tests for ubuntu2404 dispatch**

Append to `tests/test_writer.py`:

```python
def test_build_bundle_ubuntu2404_returns_distro_tagged_bundle(tmp_path):
    yaml_text = textwrap.dedent(
        """\
        distro: ubuntu2404
        system: {hostname: u24-test}
        user:
          admin:
            name: opsadmin
            authorized_keys: ["ssh-ed25519 AAAA a@b"]
            sudo: nopasswd_yes
        """
    )
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(yaml_text, encoding="utf-8")
    cfg = load_host_config(cfg_path, sets=[])
    bundle = build_bundle(cfg)
    assert bundle.distro == "ubuntu2404"
    assert bundle.ks_cfg is None
    assert bundle.user_data is not None
    assert bundle.meta_data is not None
    assert bundle.user_data.startswith("#cloud-config")
    assert "instance-id: u24-test" in bundle.meta_data


def test_build_bundle_ubuntu2404_tailoring_is_valid_xccdf_skeleton(tmp_path):
    # No ubuntu2404 rules exist yet (phase 3 ports them), so the tailoring
    # should be a valid XCCDF document with no select/disable ops — just
    # the profile skeleton. Phase 3 starts populating it.
    yaml_text = textwrap.dedent(
        """\
        distro: ubuntu2404
        system: {hostname: u24-empty}
        user:
          admin:
            name: ops
            authorized_keys: ["ssh-ed25519 AAAA a@b"]
            sudo: nopasswd_yes
        """
    )
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(yaml_text, encoding="utf-8")
    cfg = load_host_config(cfg_path, sets=[])
    bundle = build_bundle(cfg)
    assert "<xccdf:Tailoring" in bundle.tailoring_xml
    # No rule overrides yet — no <xccdf:select> tags.
    assert "<xccdf:select" not in bundle.tailoring_xml


def test_build_bundle_alma9_default_unchanged_when_distro_omitted(tmp_path):
    # Regression guard for the dispatch refactor: a config with no `distro:`
    # still defaults to alma9 and produces a ks_cfg-bearing bundle.
    yaml_text = textwrap.dedent(
        """\
        system: {hostname: alma-default}
        user:
          admin:
            name: ops
            authorized_keys: ["ssh-ed25519 AAAA a@b"]
            sudo: nopasswd_yes
        """
    )
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(yaml_text, encoding="utf-8")
    cfg = load_host_config(cfg_path, sets=[])
    bundle = build_bundle(cfg)
    assert bundle.distro == "alma9"
    assert bundle.ks_cfg is not None
    assert "%post" in bundle.ks_cfg
    assert bundle.user_data is None
    assert bundle.meta_data is None
```

- [ ] **Step 2: Run the failing tests**

Run: `pytest tests/test_writer.py::test_build_bundle_ubuntu2404_returns_distro_tagged_bundle tests/test_writer.py::test_build_bundle_ubuntu2404_tailoring_is_valid_xccdf_skeleton tests/test_writer.py::test_build_bundle_alma9_default_unchanged_when_distro_omitted -v`
Expected: the two ubuntu2404 tests FAIL (current `build_bundle` runs the alma9 path on an ubuntu2404 config, which tries to render the kickstart skeleton with ubuntu's defaults and either crashes or produces alma9-shaped output; ultimately the `Bundle(distro="alma9", ...)` constructor will fail because `cfg.distro` was `"ubuntu2404"` not `"alma9"` — but the Bundle's `distro` is hardcoded `"alma9"` in the current return statement, so the test asserting `bundle.distro == "ubuntu2404"` will FAIL). The alma9-default test PASSES (existing behavior).

- [ ] **Step 3: Expand the imports in `writer.py`**

Edit `src/ks_gen/writer.py`. Find the existing import:

```python
from ks_gen.skeleton import PostBlock, render_skeleton
```

Replace with:

```python
from ks_gen.skeleton import PostBlock, render_meta_data, render_skeleton, render_user_data
```

- [ ] **Step 4: Refactor `build_bundle` to dispatch on `cfg.distro`**

In `src/ks_gen/writer.py`, replace the existing `build_bundle` function (currently spanning from `def build_bundle(cfg: HostConfig) -> Bundle:` through the closing `)` of the `Bundle(distro="alma9", ...)` return — lines 41 through about line 71 after Task 1's edits) with this dispatch + two helper functions:

```python
def build_bundle(cfg: HostConfig) -> Bundle:
    if cfg.distro == "alma9":
        return _build_alma9_bundle(cfg)
    if cfg.distro == "ubuntu2404":
        return _build_ubuntu2404_bundle(cfg)
    raise AssertionError(f"unhandled distro: {cfg.distro!r}")


def _build_alma9_bundle(cfg: HostConfig) -> Bundle:
    rules = topo_sort(load_rules(cfg.distro))
    applicable = [r for r in rules if r.applies(cfg)]

    post_blocks: list[PostBlock] = []
    tailoring_ops = []
    rule_packages: list[str] = []
    already = set(cfg.packages.effective_required)
    for r in applicable:
        body = r.emit_post(cfg).rstrip()
        if body:
            post_blocks.append(PostBlock(rule_id=r.id, body=body))
        tailoring_ops.extend(r.emit_tailoring(cfg))
        for pkg in r.emit_packages(cfg):
            if pkg not in already:
                rule_packages.append(pkg)
                already.add(pkg)

    profile_id = f"xccdf_org.ssgproject.content_profile_{cfg.meta.profile}"
    tailoring_xml = build_tailoring_xml(tailoring_ops, profile_id=profile_id)
    ks_cfg = render_skeleton(cfg, post_blocks=list(post_blocks), rule_packages=rule_packages)
    host_yaml = yaml.safe_dump(
        cfg.model_dump(mode="json"), sort_keys=False, default_flow_style=False
    )
    exceptions_md = render_exceptions_md(cfg, applicable)
    return Bundle(
        distro="alma9",
        ks_cfg=ks_cfg,
        tailoring_xml=tailoring_xml,
        host_yaml=host_yaml,
        exceptions_md=exceptions_md,
    )


def _build_ubuntu2404_bundle(cfg: HostConfig) -> Bundle:
    # Phase 2: empty/placeholder bundle. Phase 3 ports rules into
    # rules/ubuntu2404/; their emit_post bodies will populate late-commands
    # via render_user_data once that template wires the list in.
    rules = topo_sort(load_rules(cfg.distro))
    applicable = [r for r in rules if r.applies(cfg)]

    tailoring_ops = []
    for r in applicable:
        tailoring_ops.extend(r.emit_tailoring(cfg))

    profile_id = f"xccdf_org.ssgproject.content_profile_{cfg.meta.profile}"
    tailoring_xml = build_tailoring_xml(tailoring_ops, profile_id=profile_id)
    user_data = render_user_data(cfg)
    meta_data = render_meta_data(cfg)
    host_yaml = yaml.safe_dump(
        cfg.model_dump(mode="json"), sort_keys=False, default_flow_style=False
    )
    exceptions_md = render_exceptions_md(cfg, applicable)
    return Bundle(
        distro="ubuntu2404",
        tailoring_xml=tailoring_xml,
        host_yaml=host_yaml,
        exceptions_md=exceptions_md,
        user_data=user_data,
        meta_data=meta_data,
    )
```

- [ ] **Step 5: Run the new tests (expect PASS)**

Run: `pytest tests/test_writer.py -v`
Expected: all `test_build_bundle_*` tests PASS, plus the Task 1 Bundle invariant tests still PASS, plus all pre-existing tests in `test_writer.py` still PASS.

- [ ] **Step 6: Run the full golden snapshot suite — zero diff for alma9**

Run: `pytest tests/golden/ -v`
Expected: all 18 golden tests PASS with no `--snapshot-update` needed. If any golden fails, the alma9 dispatch path is not byte-identical: investigate (likely a refactor typo) and fix before continuing. Do NOT regenerate snapshots — the acceptance bar for this phase is that alma9 is unchanged.

- [ ] **Step 7: Commit**

```powershell
git add src\ks_gen\writer.py tests\test_writer.py
git -c user.email="github.v5f9w@bitbucket.onl" `
    -c user.signingkey=BE707B220C995478 `
    commit -S -m "feat(writer): dispatch build_bundle on cfg.distro

Top-level build_bundle now routes to _build_alma9_bundle (current body,
unchanged) or _build_ubuntu2404_bundle (new). The ubuntu2404 path builds
an empty/placeholder bundle: tailoring with no select/disable ops,
user-data with no late-commands, meta-data with hostname.

Existing alma9 golden snapshots are byte-identical. Phase 3 populates
the rule body via the ubuntu2404 rule ports."
```

---

### Task 4: `write_bundle` distro dispatch + CLI lint guard

**Files:**
- Modify: `src/ks_gen/writer.py` — `write_bundle` function
- Modify: `src/ks_gen/cli.py` — `gen` command's lint block
- Test: `tests/test_writer.py` (append), `tests/test_cli_gen_ubuntu.py` (new)

**Goal:** `write_bundle` writes the distro-appropriate file set. `cli.gen` skips the kickstart-shaped `lint_kickstart` call for ubuntu2404 (lint validates ks.cfg invariants which don't apply to user-data). An end-to-end CLI test verifies `ks-gen gen` against an ubuntu2404 YAML writes the right files and exits 0.

- [ ] **Step 1: Write the failing tests for `write_bundle` dispatch**

Append to `tests/test_writer.py`:

```python
def test_write_bundle_ubuntu2404_writes_seed_files(tmp_path):
    yaml_text = textwrap.dedent(
        """\
        distro: ubuntu2404
        system: {hostname: u24-write}
        user:
          admin:
            name: ops
            authorized_keys: ["ssh-ed25519 AAAA a@b"]
            sudo: nopasswd_yes
        """
    )
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(yaml_text, encoding="utf-8")
    cfg = load_host_config(cfg_path, sets=[])
    bundle = build_bundle(cfg)
    out = tmp_path / "out"
    write_bundle(bundle, out)
    for name in ("user-data", "meta-data", "tailoring.xml", "host.yaml", "exceptions.md"):
        assert (out / name).is_file(), f"missing {name}"
    # ks.cfg must NOT be written for ubuntu2404.
    assert not (out / "ks.cfg").exists()


def test_write_bundle_alma9_does_not_write_ubuntu_seed_files(tmp_path):
    # Regression guard: the alma9 path keeps writing ks.cfg + the three
    # shared artifacts and must NOT spuriously write user-data/meta-data.
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(YAML, encoding="utf-8")
    cfg = load_host_config(cfg_path, sets=[])
    bundle = build_bundle(cfg)
    out = tmp_path / "out"
    write_bundle(bundle, out)
    assert (out / "ks.cfg").is_file()
    assert not (out / "user-data").exists()
    assert not (out / "meta-data").exists()
```

- [ ] **Step 2: Run the failing tests**

Run: `pytest tests/test_writer.py::test_write_bundle_ubuntu2404_writes_seed_files tests/test_writer.py::test_write_bundle_alma9_does_not_write_ubuntu_seed_files -v`
Expected: the ubuntu test FAILS — current `write_bundle` unconditionally tries to write `bundle.ks_cfg` which is `None` for an ubuntu2404 bundle, raising `TypeError`. The alma test PASSES already (regression guard — today's `write_bundle` doesn't write user-data/meta-data, so this just locks that in).

- [ ] **Step 3: Update `write_bundle` to dispatch on `bundle.distro`**

In `src/ks_gen/writer.py`, replace the existing `write_bundle` function (currently lines 74–79 in the post-Task-1/2/3 file) with:

```python
def write_bundle(bundle: Bundle, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "tailoring.xml").write_text(bundle.tailoring_xml, encoding="utf-8", newline="\n")
    (out_dir / "host.yaml").write_text(bundle.host_yaml, encoding="utf-8", newline="\n")
    (out_dir / "exceptions.md").write_text(bundle.exceptions_md, encoding="utf-8", newline="\n")
    if bundle.distro == "alma9":
        assert bundle.ks_cfg is not None  # Bundle.__post_init__ guarantees this
        (out_dir / "ks.cfg").write_text(bundle.ks_cfg, encoding="utf-8", newline="\n")
    elif bundle.distro == "ubuntu2404":
        assert bundle.user_data is not None and bundle.meta_data is not None
        (out_dir / "user-data").write_text(bundle.user_data, encoding="utf-8", newline="\n")
        (out_dir / "meta-data").write_text(bundle.meta_data, encoding="utf-8", newline="\n")
```

- [ ] **Step 4: Run the `write_bundle` tests (expect PASS)**

Run: `pytest tests/test_writer.py -v`
Expected: all `test_write_bundle_*` tests PASS, plus all prior Task 1–3 tests still PASS.

- [ ] **Step 5: Write the failing CLI integration test**

Create `tests/test_cli_gen_ubuntu.py`:

```python
import textwrap

from typer.testing import CliRunner

from ks_gen.cli import app

UBUNTU_YAML = textwrap.dedent(
    """\
    distro: ubuntu2404
    system: {hostname: u24-cli-test}
    user:
      admin:
        name: ops
        authorized_keys: ["ssh-ed25519 AAAA a@b"]
        sudo: nopasswd_yes
    """
)


def test_gen_ubuntu2404_writes_seed_files_and_skips_kickstart_lint(tmp_path):
    cfg_path = tmp_path / "host.yaml"
    cfg_path.write_text(UBUNTU_YAML, encoding="utf-8")
    out_dir = tmp_path / "out"
    result = CliRunner().invoke(app, ["gen", "--config", str(cfg_path), "--out", str(out_dir)])
    assert result.exit_code == 0, result.output
    # Five expected files; ks.cfg is NOT one of them.
    for name in ("user-data", "meta-data", "tailoring.xml", "host.yaml", "exceptions.md"):
        assert (out_dir / name).is_file(), f"missing {name}: {result.output}"
    assert not (out_dir / "ks.cfg").exists()
    assert "Wrote bundle to" in result.output
```

- [ ] **Step 6: Run the failing CLI test**

Run: `pytest tests/test_cli_gen_ubuntu.py -v`
Expected: FAIL — exit code is non-zero. `gen` calls `lint_kickstart(out / "ks.cfg")` on the ubuntu2404 output and `ks.cfg` doesn't exist, so lint_kickstart raises an OSError that surfaces as exit code 1.

- [ ] **Step 7: Skip the kickstart-shaped lint for ubuntu2404 in `cli.gen`**

In `src/ks_gen/cli.py`, find the body of the `gen` command (currently lines 33–52). Replace the section after `write_bundle(bundle, out)` (currently lines 47–52 — the `report = lint_kickstart(...)` through `typer.echo(f"Wrote bundle to {out}")` block) with:

```python
    write_bundle(bundle, out)
    if bundle.distro == "alma9":
        report = lint_kickstart(out / "ks.cfg")
        if not report.ok:
            for f in report.failures:
                typer.echo(f"lint FAIL: {f}", err=True)
            raise typer.Exit(code=int(ExitCode.LINT_FAIL))
    typer.echo(f"Wrote bundle to {out}")
```

The diff is two lines: wrap the existing `report = lint_kickstart(...)` block in `if bundle.distro == "alma9":` and indent its body. Existing behavior for alma9 is unchanged.

- [ ] **Step 8: Run the CLI test (expect PASS)**

Run: `pytest tests/test_cli_gen_ubuntu.py -v`
Expected: PASS — exit code 0, all five files written, `ks.cfg` absent.

- [ ] **Step 9: Run the full CI parity check (per `CLAUDE.md`)**

Run each, fix any failure before proceeding:
```powershell
ruff check src tests
ruff format --check src tests
mypy
pytest -q
```
Expected behavior for failures:
- `ruff check` failure → fix the offending file (e.g. unused import).
- `ruff format --check` failure → run `ruff format src tests` to autofix, then re-run `--check`.
- `mypy` failure → most likely `bundle.ks_cfg` being `str | None` at a consumer site; the project pattern is `assert bundle.ks_cfg is not None` to narrow.
- `pytest` failure → triage by test name; if a golden fails, the alma9 path is not byte-identical (investigate, do NOT regenerate snapshots).

- [ ] **Step 10: Commit**

```powershell
git add src\ks_gen\writer.py src\ks_gen\cli.py tests\test_writer.py tests\test_cli_gen_ubuntu.py
git -c user.email="github.v5f9w@bitbucket.onl" `
    -c user.signingkey=BE707B220C995478 `
    commit -S -m "feat(writer,cli): distro-aware write_bundle and gen lint skip

write_bundle now dispatches on bundle.distro: alma9 writes ks.cfg,
ubuntu2404 writes user-data + meta-data. The three shared artifacts
(tailoring.xml, host.yaml, exceptions.md) are always written.

cli.gen skips lint_kickstart (which validates kickstart-shaped output)
when bundle.distro != alma9. A ubuntu2404-specific lint can land in a
later phase if/when there are useful invariants to check on the
generated user-data."
```

---

### Task 5: Final verification + push + PR

**Goal:** Confirm zero behavior change for alma9 one more time, push the branch, open a PR against `main`.

- [ ] **Step 1: Confirm the current branch**

Run:
```powershell
git -C C:\Users\yizshachuck\source\ks-gen branch --show-current
```
Expected: a feature branch name like `feat/phase-2-bundle-reshape-writer-dispatch` (whatever the controller set up). If the output is `main`, STOP — phase 2 work should never sit on `main`. Surface this to the controller before pushing anything.

- [ ] **Step 2: Confirm the branch has exactly four commits past `main`**

Run:
```powershell
git -C C:\Users\yizshachuck\source\ks-gen log --oneline main..HEAD
```
Expected: four commits (one per Task 1–4). If fewer or more, investigate before pushing — a missed commit or an accidental merge needs to be resolved.

- [ ] **Step 3: Run the full CI parity check one final time**

```powershell
ruff check src tests
ruff format --check src tests
mypy
pytest -q
```
Expected: all four green.

- [ ] **Step 4: Confirm goldens are byte-identical**

```powershell
pytest tests\golden\ -v
```
Expected: all 18 golden tests PASS. If any FAILs, the alma9 path is not byte-identical — investigate and fix before pushing. Do NOT regenerate snapshots; the acceptance bar for this phase is that alma9 is unchanged.

- [ ] **Step 5: Push the branch**

```powershell
git push -u origin HEAD
```
Expected: branch created on origin, signed commits accepted.

- [ ] **Step 6: Open the PR against `main`**

```powershell
gh pr create --base main --head $(git branch --show-current) --title "feat(writer,cli): bundle reshape + distro dispatch (#81 phase 2)" --body "$(cat <<'EOF'
Phase 2 of the Ubuntu 24.04 STIG autoinstall roadmap (#81). Builds on phase 1
(PR #90, squash 60d83a1), which added the `distro:` discriminator and
per-distro rule discovery.

## Summary

- Reshape `Bundle` dataclass: shared core (`distro`, `tailoring_xml`,
  `host_yaml`, `exceptions_md`) + optional payload fields (`ks_cfg` for
  alma9, `user_data` + `meta_data` for ubuntu2404). `__post_init__`
  enforces the invariant so consumers downstream can rely on it.
- `build_bundle` dispatches on `cfg.distro` to internal helpers. The
  alma9 path is byte-identical to today — every golden snapshot
  unchanged.
- `write_bundle` writes distro-appropriate files: alma9 emits `ks.cfg`;
  ubuntu2404 emits `user-data` + `meta-data` (cloud-init NoCloud +
  Subiquity autoinstall placeholder).
- `cli.gen` skips the kickstart-shaped `lint_kickstart` call for
  ubuntu2404 bundles.
- Bootstrap empty `ks_gen.rules.ubuntu2404` package so phase 3 has a
  home. `load_rules('ubuntu2404')` continues to return `[]`.
- Two new Jinja templates (`user-data.j2`, `meta-data.j2`) and two new
  renderers in `skeleton.py`. The ubuntu2404 `user-data` is a
  placeholder: syntactically valid Subiquity autoinstall with empty
  `late-commands`. Phase 3 populates it from the ported rules.

## What this PR does NOT do

- No ubuntu2404 rule ports (phase 3).
- No verify-side distro awareness (phase 4).
- No ISO repack for ubuntu (deferred to #87).
- No CLI distro prompt in the wizard.

## Test plan

- [x] `ruff check src tests` clean
- [x] `ruff format --check src tests` clean
- [x] `mypy` clean
- [x] `pytest -q` green (existing + new tests)
- [x] All 18 golden snapshots byte-identical (alma9 zero-behavior-change guarantee)
- [x] New CLI integration test: `ks-gen gen --config ubuntu.yaml` writes
      `user-data` + `meta-data` + `tailoring.xml` + `host.yaml` +
      `exceptions.md`, exit 0, no `ks.cfg`
EOF
)"
```

- [ ] **Step 7: Capture and report the PR URL**

The `gh pr create` output ends with the new PR URL. Capture it and report back to the controller along with task completion.

---

## Done criteria

- `Bundle` is a discriminated dataclass with `distro` + optional payload fields, invariant enforced at construction time.
- `build_bundle(cfg)` and `write_bundle(bundle, out)` dispatch on `cfg.distro` / `bundle.distro` respectively.
- `cli.gen` works end-to-end for `distro: ubuntu2404`, writing five files and skipping the alma9 lint.
- `load_rules("ubuntu2404")` returns `[]` (empty package iterated by pkgutil).
- Every existing golden snapshot is byte-identical — the alma9 path is unchanged.
- Four signed commits land on a feature branch; PR opened against `main`.

## What is NOT in this plan

- Porting any ubuntu2404 rule. Phase 3 (per spec §6) does one PR per rule.
- Verify (`verify/*`) distro awareness. Phase 4.
- Bootloader / ISO repack for ubuntu. Deferred to #87.
- Wizard distro prompt. Belongs alongside the first ubuntu2404 rule port (phase 3) so the wizard can sanely guide the operator through the choice.
- `MANUAL.md` / `README.md` updates. Premature — a placeholder ubuntu bundle is not yet operator-useful.
