# Lean Package Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `packages.preset` field to `host.yaml` that, when set to `lean`, strips `@standard` from the emitted base groups and auto-adds the STIG-required compensating packages (logrotate, postfix, cronie, crontabs, parted). Default preset is `standard` — no behavior change for existing configs.

**Architecture:** A `PackagesPreset` enum on the existing `Packages` config model, plus two `@property` accessors (`effective_base_groups`, `effective_required`) that compose raw user input with the preset's effect. The Jinja template and writer pull from the effective properties instead of the raw fields. Pure config + template change; no new modules, no new rules.

**Tech Stack:** Python 3.11+, pydantic v2 (`BaseModel` with `frozen=True, extra="forbid"`), Jinja2 templates, syrupy snapshot tests, pytest.

---

## File Structure

**Modify:**
- `src/ks_gen/config.py` — add `PackagesPreset` enum, `LEAN_EXTRA_PACKAGES` constant, `preset` field on `Packages`, two `@property` accessors
- `src/ks_gen/templates/ks.cfg.j2:44,46` — switch `cfg.packages.base_groups` → `effective_base_groups`, `cfg.packages.required` → `effective_required`
- `src/ks_gen/writer.py:48` — switch raw `cfg.packages.required` to `cfg.packages.effective_required` in the dedup set
- `tests/test_config_schema.py` — add Packages preset tests alongside existing ones
- `MANUAL.md:517-543` — document the preset field and tradeoffs

**Create:**
- `tests/golden/lean-preset.host.yaml` — minimal config with `packages.preset: lean`
- `tests/golden/test_lean_preset.py` — golden test using syrupy
- `tests/golden/__snapshots__/test_lean_preset.ambr` — generated via `--snapshot-update`

**Untouched (intentional):**
- No rule changes. Lean baseline is a config/template concern only.
- No CLI changes. Users set `packages.preset: lean` in `host.yaml`.

---

### Task 1: Add `PackagesPreset` enum and `preset` field to `Packages`

**Files:**
- Modify: `src/ks_gen/config.py` (Packages model around line 369)
- Modify: `tests/test_config_schema.py` (Packages test block around line 181)

- [ ] **Step 1: Write failing tests for the preset field**

Append to `tests/test_config_schema.py` after `test_packages_include_dnf_automatic_tooling`:

```python
def test_packages_preset_defaults_to_standard():
    from ks_gen.config import PackagesPreset

    p = Packages()
    assert p.preset == PackagesPreset.STANDARD


def test_packages_preset_accepts_lean():
    from ks_gen.config import PackagesPreset

    p = Packages(preset=PackagesPreset.LEAN)
    assert p.preset == PackagesPreset.LEAN


def test_packages_preset_accepts_string_value():
    p = Packages(preset="lean")
    assert p.preset.value == "lean"


def test_packages_preset_rejects_unknown_value():
    with pytest.raises(ValidationError):
        Packages(preset="ultra-lean")
```

Add `PackagesPreset` to the import block at the top of the file.

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config_schema.py -k "packages_preset" -v
```

Expected: ImportError or AttributeError on `PackagesPreset`; 4 tests fail.

- [ ] **Step 3: Add the enum and field**

In `src/ks_gen/config.py`, just before `class Packages(StrictModel):` (around line 369), add:

```python
class PackagesPreset(StrEnum):
    STANDARD = "standard"
    LEAN = "lean"
```

Then modify the `Packages` class to add `preset` as the first field:

```python
class Packages(StrictModel):
    preset: PackagesPreset = PackagesPreset.STANDARD
    base_groups: list[str] = Field(default_factory=lambda: ["@^minimal-environment", "@standard"])
    required: list[str] = Field(
        default_factory=lambda: [
            "scap-security-guide",
            "openscap-scanner",
            "aide",
            "audit",
            "rsyslog",
            "chrony",
            "firewalld",
            "sudo",
            "policycoreutils-python-utils",
            "dnf-automatic",
            "dnf-utils",
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

- [ ] **Step 4: Run tests to verify they pass**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config_schema.py -k "packages_preset" -v
.\.venv\Scripts\python.exe -m pytest tests/test_config_schema.py -k "packages" -v
```

Expected: 4 new tests PASS; the 3 pre-existing `test_packages_*` tests still PASS.

- [ ] **Step 5: Commit**

```powershell
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -am "feat(config): add Packages.preset field (standard | lean)"
```

---

### Task 2: Add `LEAN_EXTRA_PACKAGES` and `effective_*` properties

**Files:**
- Modify: `src/ks_gen/config.py` (Packages model)
- Modify: `tests/test_config_schema.py`

**Design note:** The two properties are plain `@property` methods (not pydantic `computed_field`) so they don't appear in `model_dump()` output — `host.yaml` round-trips stay clean.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_config_schema.py`:

```python
def test_effective_base_groups_standard_passthrough():
    p = Packages()
    assert p.effective_base_groups == ["@^minimal-environment", "@standard"]


def test_effective_base_groups_lean_strips_standard():
    p = Packages(preset="lean")
    assert p.effective_base_groups == ["@^minimal-environment"]


def test_effective_base_groups_lean_preserves_user_custom_groups():
    p = Packages(preset="lean", base_groups=["@^minimal-environment", "@standard", "@development"])
    assert p.effective_base_groups == ["@^minimal-environment", "@development"]


def test_effective_required_standard_passthrough():
    p = Packages()
    assert p.effective_required == list(p.required)


def test_effective_required_lean_adds_compensating_packages():
    p = Packages(preset="lean")
    for pkg in ("logrotate", "postfix", "cronie", "crontabs", "parted"):
        assert pkg in p.effective_required


def test_effective_required_lean_preserves_required_order_and_dedupes():
    # User already lists logrotate explicitly; should appear once, in its
    # original position relative to the rest of `required`.
    p = Packages(preset="lean", required=["scap-security-guide", "logrotate", "aide"])
    assert p.effective_required.count("logrotate") == 1
    # Original entries come first; lean extras append after, with already-
    # present ones skipped.
    assert p.effective_required[:3] == ["scap-security-guide", "logrotate", "aide"]
    for pkg in ("postfix", "cronie", "crontabs", "parted"):
        assert pkg in p.effective_required[3:]
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config_schema.py -k "effective_" -v
```

Expected: 6 tests fail (AttributeError on `effective_base_groups` / `effective_required`).

- [ ] **Step 3: Add the constant and properties**

In `src/ks_gen/config.py`, just before `class Packages(StrictModel):`, add:

```python
LEAN_EXTRA_PACKAGES: tuple[str, ...] = (
    "logrotate",
    "postfix",
    "cronie",
    "crontabs",
    "parted",
)
```

At the end of the `Packages` class body, add:

```python
    @property
    def effective_base_groups(self) -> list[str]:
        if self.preset == PackagesPreset.LEAN:
            return [g for g in self.base_groups if g != "@standard"]
        return list(self.base_groups)

    @property
    def effective_required(self) -> list[str]:
        if self.preset != PackagesPreset.LEAN:
            return list(self.required)
        existing = set(self.required)
        return list(self.required) + [p for p in LEAN_EXTRA_PACKAGES if p not in existing]
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_config_schema.py -v
```

Expected: all `test_packages_*` and `test_effective_*` tests PASS. No other test should regress.

- [ ] **Step 5: Commit**

```powershell
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -am "feat(config): add LEAN_EXTRA_PACKAGES and effective_* properties on Packages"
```

---

### Task 3: Wire template and writer to use `effective_*`

**Files:**
- Modify: `src/ks_gen/templates/ks.cfg.j2:44,46`
- Modify: `src/ks_gen/writer.py:48`

This task does NOT add tests — the existing 12 golden tests cover the standard-preset path and must remain green (no preset = no behavior change). Lean-preset coverage lands in Task 4.

- [ ] **Step 1: Update the template**

In `src/ks_gen/templates/ks.cfg.j2`, change lines 44 and 46:

```jinja
%packages
{% for grp in cfg.packages.effective_base_groups %}{{ grp }}
{% endfor -%}
{% for pkg in cfg.packages.effective_required %}{{ pkg }}
{% endfor -%}
{% for pkg in rule_packages %}{{ pkg }}
{% endfor -%}
{% for pkg in cfg.packages.extra %}{{ pkg }}
{% endfor -%}
{% for pkg in cfg.packages.excluded %}-{{ pkg }}
{% endfor -%}
%end
```

(Only the `base_groups` → `effective_base_groups` and `required` → `effective_required` lines change.)

- [ ] **Step 2: Update the writer**

In `src/ks_gen/writer.py:48`, change:

```python
    already = set(cfg.packages.required)
```

to:

```python
    already = set(cfg.packages.effective_required)
```

This ensures rule-emitted packages (`emit_packages`) don't double-add a package that the lean preset just inserted.

- [ ] **Step 3: Run the full snapshot suite to verify no drift**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/golden/ -v
```

Expected: all 12 golden tests PASS with no snapshot updates. (Standard preset is default; `effective_*` returns the same lists as the raw fields for the default preset.)

- [ ] **Step 4: Run mypy to catch any type drift**

```powershell
.\.venv\Scripts\python.exe -m mypy
```

Expected: `Success: no issues found`.

- [ ] **Step 5: Commit**

```powershell
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -am "feat(templates): emit effective_base_groups and effective_required for lean preset support"
```

---

### Task 4: Add golden coverage for the lean preset

**Files:**
- Create: `tests/golden/lean-preset.host.yaml`
- Create: `tests/golden/test_lean_preset.py`
- Create: `tests/golden/__snapshots__/test_lean_preset.ambr` (generated)

- [ ] **Step 1: Create the input fixture**

Write `tests/golden/lean-preset.host.yaml`:

```yaml
system:
  hostname: web01.example.com
user:
  admin:
    name: opsadmin
    authorized_keys:
      - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEYleanpreset test@laptop"
    sudo: nopasswd_yes
packages:
  preset: lean
```

(This is `minimal-dhcp.host.yaml` plus the preset field, so the diff against `test_minimal_dhcp` goldens isolates the lean-preset effect.)

- [ ] **Step 2: Create the test**

Write `tests/golden/test_lean_preset.py`:

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


def test_lean_preset(snapshot):
    yaml_path = Path(__file__).parent / "lean-preset.host.yaml"
    cfg = load_host_config(yaml_path, sets=[])
    bundle = build_bundle(cfg)
    assert _normalize(bundle.ks_cfg) == snapshot(name="ks.cfg")
    assert _normalize(bundle.tailoring_xml) == snapshot(name="tailoring.xml")
    assert _normalize(bundle.exceptions_md) == snapshot(name="exceptions.md")
```

- [ ] **Step 3: Generate the snapshot**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/golden/test_lean_preset.py --snapshot-update -v
```

Expected: snapshot file `tests/golden/__snapshots__/test_lean_preset.ambr` created; test passes on first run.

- [ ] **Step 4: Inspect the snapshot diff vs `test_minimal_dhcp`**

```powershell
git diff --no-index tests/golden/__snapshots__/test_minimal_dhcp.ambr tests/golden/__snapshots__/test_lean_preset.ambr
```

Expected differences and ONLY these differences:
- `%packages` block: `@standard` removed
- `%packages` block: `logrotate`, `postfix`, `cronie`, `crontabs`, `parted` added (after the existing required list, before rule_packages)
- Possibly the snapshot test name in the ambr header

No drift in `%post`, `partition`, network, services, or tailoring.xml. If anything else differs, stop and investigate before continuing.

- [ ] **Step 5: Re-run the full golden suite to confirm stability**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/golden/ -v
```

Expected: 13 tests PASS (12 existing + new `test_lean_preset`), 0 snapshot updates.

- [ ] **Step 6: Commit**

```powershell
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -am "test(golden): cover packages.preset=lean against minimal baseline"
```

---

### Task 5: Document the preset in MANUAL.md

**Files:**
- Modify: `MANUAL.md:517-543` (section 4.10)

- [ ] **Step 1: Replace the section 4.10 body**

Replace the contents of `### 4.10 packages` with:

````markdown
### 4.10 `packages`

```yaml
packages:
  preset: standard               # "standard" (default) or "lean"
  base_groups: ["@^minimal-environment", "@standard"]
  required:                        # STIG/oscap dependencies + ops baseline
    - scap-security-guide
    - openscap-scanner
    - aide
    - audit
    - rsyslog
    - chrony
    - firewalld
    - sudo
    - policycoreutils-python-utils
  extra: []
  excluded:                        # STIG-forbidden defaults
    - telnet-server
    - rsh-server
    - tftp-server
    - vsftpd
    - ypserv
```

`excluded` packages are both removed from `%packages` (`-package`)
and purged via `dnf -y remove` in `%post`. Belt and braces, because
some get pulled in transitively by groups.

#### `preset: standard` vs `preset: lean`

- **`standard`** (default) emits `base_groups` as written. The RHEL/Alma
  `@standard` group lands on the system: vim-enhanced, mlocate, sos,
  smartmontools, postfix, parted, and ~80 other conventional admin tools.
  Closest to the AlmaLinux DVD interactive install.
- **`lean`** strips `@standard` from the emitted base groups and
  auto-adds the packages the STIG profile expects to find regardless
  (`logrotate`, `postfix`, `cronie`, `crontabs`, `parted`). Cuts ~75
  packages off the install footprint with no oscap-remediation cost.
  Choose this for single-purpose appliance hosts (container hosts,
  edge nodes, bastions) where the full admin toolset is not wanted.

The preset is purely additive over `required` — explicitly listing any
of the lean compensating packages in `required` is safe; they are
deduped, not double-added.
````

- [ ] **Step 2: Verify the markdown renders**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

(Sanity rerun — docs change should not affect any test, but the run confirms nothing else regressed.)

Expected: 551 passed, 32 snapshots passed (550 existing + 1 new from Task 4), 0 failed.

- [ ] **Step 3: Commit**

```powershell
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 commit -S -am "docs(manual): document packages.preset lean/standard tradeoff"
```

---

### Task 6: Final CI parity + PR

**Files:** none (verification + git operations only)

- [ ] **Step 1: Run the full local CI parity chain**

```powershell
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m ruff format --check src tests
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest -q
```

Expected, in order:
- `All checks passed!`
- `N files already formatted`
- `Success: no issues found in 49 source files`
- `551 passed in <Ns>` and `32 snapshots passed`

If `ruff format --check` fails (project CLAUDE.md notes this is a real risk): run `.\.venv\Scripts\python.exe -m ruff format src tests`, re-verify with `--check`, and commit as `style:`.

- [ ] **Step 2: Push the branch**

```powershell
git push -u origin worktree-feat-65-lean-package-baseline
```

- [ ] **Step 3: Open the PR**

```powershell
gh pr create --title "feat(packages): add packages.preset (standard | lean)" --body @'
## Summary

- Add `packages.preset: standard | lean` to `host.yaml` schema. Default `standard` — no behavior change for existing configs.
- `lean` strips `@standard` from the emitted base groups and auto-adds the STIG-required compensating packages (`logrotate`, `postfix`, `cronie`, `crontabs`, `parted`), deduped against the user''s `required` list.
- Template and writer pull from new `effective_base_groups` / `effective_required` properties on `Packages`. Raw fields untouched so `host.yaml` round-trips stay clean.
- Documented in MANUAL.md §4.10.

Closes #65.

## Test plan

- [x] `ruff check src tests`
- [x] `ruff format --check src tests`
- [x] `mypy`
- [x] `pytest -q` — 551 passed, 32 snapshots passed
- [x] New golden `tests/golden/test_lean_preset.py` diff inspected: only `%packages` block changes vs `test_minimal_dhcp` baseline.
- [ ] Install-regression harness (`.scratch/install-regression/`) against a lean config — recommended before merge but not run in this PR per CLAUDE.md guidance (operator-discretion call).
'@
```

- [ ] **Step 4: Confirm the PR URL is returned and report it**

Expected output: a `https://github.com/SupremeCommanderHedgehog/ks-gen/pull/<N>` URL. Report it to the user.

---

## Self-review notes

- **Spec coverage:** Issue #65's "Proposed solution" → preset option (Task 1-2); compensating package list (Task 2 constant); acceptance criterion "decision recorded" → preset option chosen in plan header; "Packages model updated" → Tasks 1-2; "golden snapshots regenerated, diff inspected" → Task 4; "MANUAL.md updated" → Task 5. Install-regression harness flagged as optional in PR body per project CLAUDE.md (operator-discretion).
- **No placeholders:** all code blocks complete; all commands have expected output.
- **Type consistency:** `effective_base_groups` / `effective_required` names match across config.py, template, writer, and tests. `PackagesPreset` import in test file added.
- **YAGNI:** no new module, no rule, no CLI surface. Property-based composition is the smallest change that delivers the feature without polluting `model_dump`.
