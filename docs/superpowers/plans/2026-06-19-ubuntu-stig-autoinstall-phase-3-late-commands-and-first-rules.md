# Ubuntu 24.04 STIG Autoinstall Phase 3.0 — Late-Commands Infrastructure + First Two Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `late-commands` end-to-end for ubuntu2404 bundles, port the first two rules (`admin_user_and_keys` skeleton-only; `ssh_keep_open` as the first late-command), and pin the result with the first ubuntu2404 golden snapshot.

**Architecture:** Phase 3 of the Ubuntu STIG autoinstall roadmap (spec §6, §11 item 3). Phase 2 left `_build_ubuntu2404_bundle` ignoring rule post bodies and `render_user_data` hardcoding `late-commands: []`. This PR fills that gap: `render_user_data` gains a `post_blocks` parameter (mirroring `render_skeleton`), `_build_ubuntu2404_bundle` collects post blocks the same way the alma9 helper does, and a new private `_format_late_commands` helper in `skeleton.py` assembles a YAML list of `curtin in-target -- bash -c <quoted body>` entries — wrapped in YAML `|` literal blocks so multi-line bash bodies stay valid YAML. Two ubuntu2404 rule modules ship in this PR: `admin_user_and_keys` (emits its output in the autoinstall `identity:` block plus a new cloud-init `users:` block — `emit_post` returns empty), and `ssh_keep_open` (single `ufw allow <port>/tcp` late-command, depends on a new `ensure_ufw_port` field on `SshKeepOpenCfg`).

**Tech Stack:** Python 3.11+, pydantic 2, jinja2, syrupy snapshots, `shlex` from the standard library. No new runtime dependencies.

**Branch:** This plan assumes the controller has created a feature branch (e.g. `feat/phase-3-late-commands-and-first-rules`) checked out from `main` at commit `4304799` (post-phase-2). Tasks 1–5 commit to this branch; Task 6 pushes and opens a PR against `main`.

**Acceptance bar:**
- alma9 golden snapshots byte-identical (zero behavior change for alma9 users)
- new ubuntu2404 minimal golden snapshot captures `user-data` with `identity:` + `users:` + one `late-commands` entry, plus `meta-data`, `tailoring.xml`, `exceptions.md`, `host.yaml`
- `yaml.safe_load(user_data)` succeeds for both rules' output
- `emit_tailoring()` and `exception_entry()` deliberately return empty for both ubuntu2404 rules — the audit story for these rules is tracked separately (see "What is NOT in this plan")

---

## Design decisions locked into the plan

These trade-offs are settled before implementation. The implementer should not revisit them — if they discover a real problem with one, escalate as BLOCKED rather than diverge:

1. **Late-commands wrapping format.** Each `PostBlock` becomes one YAML list entry of the shape `- |\n    curtin in-target --target=/target -- bash -c <shlex-quoted body>`. The YAML `|` literal block preserves embedded newlines verbatim, so a multi-line bash body (e.g. a heredoc inside `cat > /etc/foo <<EOF`) stays valid YAML. `shlex.quote` handles embedded single quotes in the bash body. The rule's `id` is emitted as a `# rule:<id>` comment at the top of each bash body, preserving the audit trail kickstart gets from `PostBlock(rule_id=...)`.

2. **Where the formatting work lives.** The shlex-quoting + YAML indentation work happens in Python (`_format_late_commands` in `skeleton.py`), not in a Jinja filter. Multi-line YAML literal blocks have strict indentation rules that are awkward to express in Jinja with `trim_blocks=True`; doing it in Python keeps the template simple.

3. **`admin_user_and_keys` for ubuntu2404 emits no late-command.** Per spec §6, cloud-init handles user creation natively via the autoinstall `identity:` block (already from phase 2) plus a new top-level `users:` block in `user-data`. The rule's `emit_post` returns the empty string; the cloud-init `users:` block is rendered directly from `cfg.user.admin` by `user-data.j2`.

4. **`ssh_keep_open` for ubuntu2404 uses ufw, not firewalld or SELinux.** Single line: `ufw allow {port}/tcp`. Distinct from alma9 (which uses `semanage` + `firewall-offline-cmd`). Gated by a new `SshKeepOpenCfg.ensure_ufw_port` field (defaults `True`), separate from the alma9 `ensure_firewalld_port` / `ensure_selinux_port` fields. Cross-distro post-validators that reject the wrong field on the wrong distro (spec §3.3) are deferred to a follow-up PR.

5. **`emit_tailoring()` and `exception_entry()` for both rules return empty for this PR.** The XCCDF rule IDs in `ssg-ubuntu2404-ds.xml` need a datastream survey before we can tailor the right rules out. Emitting placeholder rule IDs would snapshot and ship — too dangerous. Audit story for these two rules lands in a follow-up PR after the survey.

---

## File Structure

**Create (5 files):**

- `src/ks_gen/rules/ubuntu2404/admin_user_and_keys.py` — ubuntu2404 implementation of the rule. `emit_post` returns empty (the work lives in `user-data.j2`); `emit_tailoring` / `exception_entry` return empty/None for this PR.
- `src/ks_gen/rules/ubuntu2404/ssh_keep_open.py` — ubuntu2404 implementation. `emit_post` returns `ufw allow {port}/tcp`; `emit_packages` returns `["ufw"]`; `applies` checks `cfg.overrides.ssh_keep_open.ensure_ufw_port`; `emit_tailoring` / `exception_entry` return empty/None.
- `tests/rules/test_ubuntu2404_admin_user_and_keys.py` — mirrors `test_admin_user_and_keys.py` shape for the new ubuntu2404 module.
- `tests/rules/test_ubuntu2404_ssh_keep_open.py` — mirrors `test_ssh_keep_open.py` shape.
- `tests/golden/ubuntu-minimal.host.yaml` — first ubuntu2404 golden fixture (minimal config). Snapshot file at `tests/golden/__snapshots__/test_ubuntu_minimal.ambr` will be syrupy-generated on first run.
- `tests/golden/test_ubuntu_minimal.py` — golden test mirroring `test_minimal_dhcp.py` shape.

**Modify (4 files):**

- `src/ks_gen/config.py` — add `ensure_ufw_port: bool = True` to `SshKeepOpenCfg`.
- `src/ks_gen/skeleton.py` — change `render_user_data(cfg) -> str` to `render_user_data(cfg, post_blocks) -> str`; add private `_format_late_commands(post_blocks)` helper; pass the formatted block to the template as `late_commands_block`.
- `src/ks_gen/templates/user-data.j2` — add a top-level cloud-init `users:` block (built from `cfg.user.admin`) between `identity:` and `late-commands:`; replace the hardcoded `late-commands: []` with `late-commands:{{ late_commands_block }}`.
- `src/ks_gen/writer.py` — `_build_ubuntu2404_bundle` collects `post_blocks` from rules (mirroring `_build_alma9_bundle`'s pattern minus the `rule_packages` accumulation, which is alma9-specific) and passes them to `render_user_data(cfg, post_blocks)`.

**Append tests to existing files (3):**

- `tests/test_skeleton_ubuntu.py` — new tests covering the `users:` block shape, `late-commands` formatting for empty + one-entry + multi-line-body cases.
- `tests/test_writer.py` — new test asserting an ubuntu2404 bundle now has a non-empty `late-commands` list when ubuntu rules are active.
- `tests/test_config.py` (or wherever `SshKeepOpenCfg` is tested — verify with `grep -l "ensure_firewalld_port" tests/`) — test that `SshKeepOpenCfg().ensure_ufw_port` defaults to `True`.

---

### Task 1: Add `SshKeepOpenCfg.ensure_ufw_port`

**Files:**
- Modify: `src/ks_gen/config.py` (the `SshKeepOpenCfg` class, currently lines 580–582)
- Test: `tests/test_config.py` (or wherever the existing `SshKeepOpenCfg` defaults are tested — confirm with a grep before writing the test, then append there)

**Goal:** Add the field that the ubuntu2404 `ssh_keep_open` rule will gate on. One field, one default-value test, isolated.

- [ ] **Step 1: Locate the existing SshKeepOpenCfg defaults tests**

Run:
```powershell
Select-String -Path tests\*.py -Pattern "ensure_firewalld_port|SshKeepOpenCfg" -SimpleMatch
```
Expected: at least one test file references the existing two fields. Append the new test in that file. If no test file references them, append to `tests/test_config.py`.

- [ ] **Step 2: Write the failing test**

Append this test (substitute the actual `from ks_gen.config import` line in the file if SshKeepOpenCfg isn't already imported there):

```python
def test_ssh_keep_open_cfg_defaults_include_ufw_port():
    from ks_gen.config import SshKeepOpenCfg

    cfg = SshKeepOpenCfg()
    assert cfg.ensure_firewalld_port is True
    assert cfg.ensure_selinux_port is True
    assert cfg.ensure_ufw_port is True
```

- [ ] **Step 3: Run the failing test**

Run: `pytest -k test_ssh_keep_open_cfg_defaults_include_ufw_port -v`
Expected: FAIL with `AttributeError: 'SshKeepOpenCfg' object has no attribute 'ensure_ufw_port'`.

- [ ] **Step 4: Add the field**

Edit `src/ks_gen/config.py`. Find the existing `SshKeepOpenCfg`:

```python
class SshKeepOpenCfg(StrictModel):
    ensure_firewalld_port: bool = True
    ensure_selinux_port: bool = True
```

Replace with:

```python
class SshKeepOpenCfg(StrictModel):
    ensure_firewalld_port: bool = True
    ensure_selinux_port: bool = True
    ensure_ufw_port: bool = True
```

- [ ] **Step 5: Run the test (expect PASS)**

Run: `pytest -k test_ssh_keep_open_cfg_defaults_include_ufw_port -v`
Expected: PASS.

- [ ] **Step 6: Confirm no regressions**

Run: `pytest -q`
Expected: all tests pass. The alma9 `ssh_keep_open.applies` checks `ensure_firewalld_port or ensure_selinux_port` — adding a third independent field is a no-op for alma9 behavior.

- [ ] **Step 7: Commit**

```powershell
git add src\ks_gen\config.py tests\test_config.py
git -c user.email="github.v5f9w@bitbucket.onl" `
    -c user.signingkey=BE707B220C995478 `
    commit -S -m "feat(config): add SshKeepOpenCfg.ensure_ufw_port (default true)

Specced in phase 1 §3.4 as the ubuntu2404 equivalent of the existing
firewalld/SELinux toggles, but deferred. Adding it now so the
ubuntu2404 ssh_keep_open rule (phase 3) can gate on it. Alma9 path
unchanged; the existing applies() check on
ensure_firewalld_port or ensure_selinux_port still produces the same
behavior for every existing config."
```

(If the test file you appended to was not `tests/test_config.py`, adjust the `git add` accordingly.)

---

### Task 2: `render_user_data(cfg, post_blocks)` + late-commands formatter

**Files:**
- Modify: `src/ks_gen/skeleton.py` — change `render_user_data` signature, add `_format_late_commands` helper
- Modify: `src/ks_gen/templates/user-data.j2` — replace `late-commands: []` with a `{{ late_commands_block }}` substitution
- Modify: `src/ks_gen/writer.py` — `_build_ubuntu2404_bundle` collects `post_blocks` and passes them to `render_user_data`
- Modify: `tests/test_skeleton_ubuntu.py` — update existing tests to pass `post_blocks=[]`; add new tests for empty / one-block / multi-line cases
- Modify: `tests/test_writer.py` — existing ubuntu2404 tests pass through the changed signature transparently (no edits expected); verify

**Goal:** Wire late-commands through the writer + template + renderer. With zero rules contributing, output is `late-commands: []` (byte-identical to phase 2 for that key). With one or more `PostBlock`s, output is a YAML list of `- |\n    curtin in-target ... bash -c '<quoted body>'` entries.

- [ ] **Step 1: Update existing `test_skeleton_ubuntu.py` tests to pass `post_blocks=[]`**

Edit `tests/test_skeleton_ubuntu.py`. Every `render_user_data(ubuntu_cfg_factory(...))` call needs to become `render_user_data(ubuntu_cfg_factory(...), post_blocks=[])`. Specifically these test functions all need the second arg added:

- `test_render_user_data_starts_with_cloud_config_header`
- `test_render_user_data_parses_as_yaml_with_autoinstall_v1`
- `test_render_user_data_carries_hostname_and_admin_username`
- `test_render_user_data_password_is_locked`
- `test_render_user_data_late_commands_is_empty_list`
- both parametrized YAML-reserved-hostname tests (whichever you find that call `render_user_data`)

Example change:
```python
def test_render_user_data_starts_with_cloud_config_header(ubuntu_cfg_factory):
    text = render_user_data(ubuntu_cfg_factory(), post_blocks=[])
    assert text.splitlines()[0] == "#cloud-config"
```

- [ ] **Step 2: Run the updated tests (expect FAIL)**

Run: `pytest tests/test_skeleton_ubuntu.py -v`
Expected: every test FAILs with `TypeError: render_user_data() got an unexpected keyword argument 'post_blocks'` — the signature change hasn't happened yet.

- [ ] **Step 3: Add new failing tests for the late-commands formatter behavior**

Append to `tests/test_skeleton_ubuntu.py`:

```python
from ks_gen.skeleton import PostBlock


def test_render_user_data_empty_post_blocks_emits_inline_empty_list(ubuntu_cfg_factory):
    text = render_user_data(ubuntu_cfg_factory(), post_blocks=[])
    doc = yaml.safe_load(text)
    assert doc["autoinstall"]["late-commands"] == []


def test_render_user_data_one_post_block_emits_curtin_bash_entry(ubuntu_cfg_factory):
    block = PostBlock(rule_id="dummy_rule", body="echo hi")
    text = render_user_data(ubuntu_cfg_factory(), post_blocks=[block])
    doc = yaml.safe_load(text)
    late = doc["autoinstall"]["late-commands"]
    assert len(late) == 1
    entry = late[0]
    assert entry.startswith("curtin in-target --target=/target -- bash -c '")
    assert "# rule:dummy_rule" in entry
    assert "echo hi" in entry


def test_render_user_data_multi_line_post_block_round_trips_through_yaml(ubuntu_cfg_factory):
    body = "set -euxo pipefail\ncat > /etc/foo <<'__EOF__'\nhello\n__EOF__"
    block = PostBlock(rule_id="multi", body=body)
    text = render_user_data(ubuntu_cfg_factory(), post_blocks=[block])
    doc = yaml.safe_load(text)
    entry = doc["autoinstall"]["late-commands"][0]
    # Multi-line bash body is preserved verbatim inside the shell-quoted arg.
    assert "set -euxo pipefail" in entry
    assert "cat > /etc/foo <<'__EOF__'" in entry
    assert "hello" in entry


def test_render_user_data_post_block_with_single_quotes_survives_shlex_quote(ubuntu_cfg_factory):
    # shlex.quote handles embedded single quotes by closing the outer quote,
    # appending an escaped quote, and reopening — '\\''. The YAML round-trip
    # must preserve the original body byte-for-byte after bash reinterprets.
    block = PostBlock(rule_id="quoty", body="echo 'hello world'")
    text = render_user_data(ubuntu_cfg_factory(), post_blocks=[block])
    doc = yaml.safe_load(text)
    entry = doc["autoinstall"]["late-commands"][0]
    assert "echo" in entry
    # The original single quotes appear somewhere in the shlex-quoted form.
    assert "'\\''hello world'\\''" in entry
```

- [ ] **Step 4: Run the new tests (expect FAIL with import or signature errors)**

Run: `pytest tests/test_skeleton_ubuntu.py -v`
Expected: the new tests fail at the `render_user_data(..., post_blocks=...)` call. Existing tests also still failing per Step 2.

- [ ] **Step 5: Change `render_user_data`'s signature + add the helper**

Edit `src/ks_gen/skeleton.py`. First, add an import at the top of the file (after `from importlib.resources import files`):

```python
from shlex import quote as _shlex_quote
```

Second, replace the existing `render_user_data` with the new signature + helper:

```python
def render_user_data(cfg: HostConfig, post_blocks: list[PostBlock]) -> str:
    """Render the autoinstall + cloud-init user-data for an ubuntu2404 host.

    Emits a ``#cloud-config`` document with ``autoinstall.version: 1``, an
    ``identity`` block from ``cfg.system.hostname`` and ``cfg.user.admin.name``,
    a cloud-init ``users:`` block from ``cfg.user.admin``, and a ``late-commands:``
    list with one entry per ``PostBlock`` (wrapped as
    ``curtin in-target --target=/target -- bash -c <shlex-quoted body>`` inside a
    YAML literal block).
    """
    env = _env()
    template = env.get_template("user-data.j2")
    return template.render(
        cfg=cfg,
        late_commands_block=_format_late_commands(post_blocks),
    )


def _format_late_commands(post_blocks: list[PostBlock]) -> str:
    """Format a list of PostBlocks as the YAML suffix for the late-commands key.

    Returns either ``" []"`` (so the template emits ``late-commands: []`` on
    one line) or ``"\\n  - |\\n    <entry>\\n  - |\\n    ..."`` (so each entry
    becomes a YAML list item under late-commands at the correct indentation).
    Each bash body is shell-quoted with shlex.quote so embedded single quotes
    survive bash re-parse; the per-entry ``# rule:<id>`` comment lives inside
    the quoted body so it stays attached to its bash payload through the YAML
    parser.
    """
    if not post_blocks:
        return " []"
    lines: list[str] = []
    for block in post_blocks:
        body = f"# rule:{block.rule_id}\n{block.body}"
        bash_cmd = (
            f"curtin in-target --target=/target -- bash -c {_shlex_quote(body)}"
        )
        # YAML literal block requires every body line to share at least the
        # first line's indentation. The template renders entries at column 2
        # (sibling of `version:`), so the literal block content lives at
        # column 4.
        indented_body = "\n    ".join(bash_cmd.splitlines())
        lines.append(f"  - |\n    {indented_body}")
    return "\n" + "\n".join(lines)
```

- [ ] **Step 6: Update `user-data.j2` to consume `late_commands_block`**

Edit `src/ks_gen/templates/user-data.j2`. Find the existing `late-commands: []` line and replace with:

```jinja
  late-commands:{{ late_commands_block }}
```

(Note: there is NO space between `:` and `{{` — the helper output already has a leading space or newline.)

- [ ] **Step 7: Update `_build_ubuntu2404_bundle` to collect post_blocks**

Edit `src/ks_gen/writer.py`. Find `_build_ubuntu2404_bundle` (currently a body that builds tailoring + user_data + meta_data without collecting post bodies). Replace the entire function body with:

```python
def _build_ubuntu2404_bundle(cfg: HostConfig) -> Bundle:
    rules = topo_sort(load_rules(cfg.distro))
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
    user_data = render_user_data(cfg, post_blocks)
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

(Diff from phase 2: added `post_blocks` accumulation; pass `post_blocks` to `render_user_data`. The empty-iteration loop body for `tailoring_ops` is unchanged — no rules ship `emit_tailoring` content this PR per design decision #5.)

- [ ] **Step 8: Run the skeleton tests (expect PASS)**

Run: `pytest tests/test_skeleton_ubuntu.py -v`
Expected: all tests PASS — both the existing tests with the new `post_blocks=[]` arg and the four new formatter tests.

- [ ] **Step 9: Run the full suite (expect PASS)**

Run: `pytest -q`
Expected: all tests pass. The two existing ubuntu2404 writer tests (`test_build_bundle_ubuntu2404_returns_distro_tagged_bundle`, `test_build_bundle_ubuntu2404_tailoring_is_valid_xccdf_skeleton`) still pass because there are still no ubuntu2404 rules contributing post bodies — `late-commands` is still `[]` from the writer's perspective at this point.

- [ ] **Step 10: Verify the alma9 goldens are byte-identical**

Run: `pytest tests/golden/ -v`
Expected: all 18 alma9 golden tests pass with zero `--snapshot-update` needed. The changes were entirely on the ubuntu2404 surface.

- [ ] **Step 11: Commit**

```powershell
git add src\ks_gen\skeleton.py src\ks_gen\templates\user-data.j2 src\ks_gen\writer.py tests\test_skeleton_ubuntu.py
git -c user.email="github.v5f9w@bitbucket.onl" `
    -c user.signingkey=BE707B220C995478 `
    commit -S -m "feat(skeleton,writer): wire late-commands for ubuntu2404 bundles

render_user_data gains a post_blocks parameter mirroring render_skeleton.
A new private _format_late_commands helper in skeleton.py turns a list of
PostBlocks into the YAML suffix for the late-commands key: an inline
'' []'' when empty, or one YAML literal block per entry wrapped as
'curtin in-target --target=/target -- bash -c <shlex-quoted body>' when
non-empty. The # rule:<id> comment lives inside the quoted body so it
stays attached to its bash payload.

_build_ubuntu2404_bundle now collects PostBlocks from rules (mirroring
the alma9 helper's pattern minus the rule_packages accumulation). No
ubuntu rules contribute bodies yet, so late-commands stays empty at
runtime — the wiring is in place for the rule ports in the next two
tasks. Alma9 path unchanged; golden snapshots byte-identical."
```

---

### Task 3: Port `admin_user_and_keys` for ubuntu2404

**Files:**
- Create: `src/ks_gen/rules/ubuntu2404/admin_user_and_keys.py`
- Modify: `src/ks_gen/templates/user-data.j2` — add the cloud-init `users:` block
- Create: `tests/rules/test_ubuntu2404_admin_user_and_keys.py`
- Modify: `tests/test_skeleton_ubuntu.py` — new tests for the `users:` block shape

**Goal:** Ship the first ubuntu2404 rule. Per spec §6, `admin_user_and_keys` for ubuntu2404 is skeleton-only — the rule's `emit_post` returns empty; the work lives in the user-data template's new `users:` block.

- [ ] **Step 1: Write failing tests for the `users:` block**

Append to `tests/test_skeleton_ubuntu.py`:

```python
def test_render_user_data_emits_cloud_init_users_block(ubuntu_cfg_factory):
    text = render_user_data(ubuntu_cfg_factory(admin="opsadmin"), post_blocks=[])
    doc = yaml.safe_load(text)
    users = doc["autoinstall"]["users"]
    assert isinstance(users, list) and len(users) == 1
    assert users[0]["name"] == "opsadmin"
    assert users[0]["shell"] == "/bin/bash"


def test_render_user_data_users_block_nopasswd_sudo(ubuntu_cfg_factory):
    text = render_user_data(ubuntu_cfg_factory(), post_blocks=[])
    doc = yaml.safe_load(text)
    assert doc["autoinstall"]["users"][0]["sudo"] == "ALL=(ALL) NOPASSWD:ALL"


def test_render_user_data_users_block_carries_authorized_keys(ubuntu_cfg_factory):
    cfg = ubuntu_cfg_factory()
    text = render_user_data(cfg, post_blocks=[])
    doc = yaml.safe_load(text)
    keys = doc["autoinstall"]["users"][0]["ssh_authorized_keys"]
    assert keys == cfg.user.admin.authorized_keys


def test_render_user_data_users_block_no_keys_emits_empty_list(ubuntu_cfg_factory):
    from ks_gen.config import AdminUser, HostConfig, System, User

    cfg = HostConfig(
        distro="ubuntu2404",
        system=System(hostname="u24-nokeys"),
        user=User(
            admin=AdminUser(
                name="ops",
                authorized_keys=[],
                sudo="nopasswd_yes",
                password="$6$abc$hash",
            )
        ),
    )
    text = render_user_data(cfg, post_blocks=[])
    doc = yaml.safe_load(text)
    assert doc["autoinstall"]["users"][0]["ssh_authorized_keys"] == []


def test_render_user_data_users_block_password_sudo_no(ubuntu_cfg_factory):
    from ks_gen.config import AdminUser, HostConfig, System, User

    cfg = HostConfig(
        distro="ubuntu2404",
        system=System(hostname="u24-pwsudo"),
        user=User(
            admin=AdminUser(
                name="ops",
                authorized_keys=["ssh-ed25519 AAAA a@b"],
                password="$6$abc$hash",
                sudo="nopasswd_no",
            )
        ),
    )
    text = render_user_data(cfg, post_blocks=[])
    doc = yaml.safe_load(text)
    assert doc["autoinstall"]["users"][0]["sudo"] == "ALL=(ALL) ALL"
```

(`password` is required on the `nopasswd_no` config because `HostConfig._admin_credential_mutex` rejects locked admin + password-required sudo.)

- [ ] **Step 2: Run the failing tests**

Run: `pytest tests/test_skeleton_ubuntu.py::test_render_user_data_emits_cloud_init_users_block tests/test_skeleton_ubuntu.py::test_render_user_data_users_block_nopasswd_sudo tests/test_skeleton_ubuntu.py::test_render_user_data_users_block_carries_authorized_keys tests/test_skeleton_ubuntu.py::test_render_user_data_users_block_no_keys_emits_empty_list tests/test_skeleton_ubuntu.py::test_render_user_data_users_block_password_sudo_no -v`
Expected: all five FAIL with `KeyError: 'users'` (or similar — the template doesn't emit a `users:` block yet).

- [ ] **Step 3: Add the `users:` block to `user-data.j2`**

Edit `src/ks_gen/templates/user-data.j2`. The current file (post-Task-2) has:

```jinja
#cloud-config
autoinstall:
  version: 1
  identity:
    hostname: {{ cfg.system.hostname | tojson }}
    realname: {{ cfg.user.admin.name | tojson }}
    username: {{ cfg.user.admin.name | tojson }}
    password: "*"
  late-commands:{{ late_commands_block }}
```

Replace with:

```jinja
#cloud-config
autoinstall:
  version: 1
  identity:
    hostname: {{ cfg.system.hostname | tojson }}
    realname: {{ cfg.user.admin.name | tojson }}
    username: {{ cfg.user.admin.name | tojson }}
    password: "*"
  users:
    - name: {{ cfg.user.admin.name | tojson }}
      sudo: {{ ("ALL=(ALL) NOPASSWD:ALL" if cfg.user.admin.sudo == "nopasswd_yes" else "ALL=(ALL) ALL") | tojson }}
      shell: /bin/bash
      ssh_authorized_keys:{% if not cfg.user.admin.authorized_keys %} []{% endif %}
{% for key in cfg.user.admin.authorized_keys %}
        - {{ key | tojson }}
{% endfor %}
  late-commands:{{ late_commands_block }}
```

- [ ] **Step 4: Run the failing tests (expect PASS)**

Run: `pytest tests/test_skeleton_ubuntu.py -v`
Expected: all tests PASS — the new five plus all prior.

- [ ] **Step 5: Write a failing test for the ubuntu2404 admin_user_and_keys rule**

Create `tests/rules/test_ubuntu2404_admin_user_and_keys.py`:

```python
from ks_gen.rules.ubuntu2404.admin_user_and_keys import RULE


def test_applies_always(ubuntu_cfg_factory):
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_id_and_summary_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules._meta import admin_user_and_keys as meta

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY


def test_emit_post_returns_empty_on_ubuntu(ubuntu_cfg_factory):
    # Ubuntu admin user creation happens via cloud-init `users:` in the
    # skeleton, not via a late-command. emit_post returns empty so the
    # writer never adds a bash payload for this rule.
    assert RULE.emit_post(ubuntu_cfg_factory()) == ""


def test_emit_tailoring_returns_empty(ubuntu_cfg_factory):
    # Tailoring deferred until ssg-ubuntu2404-ds.xml rule IDs are surveyed.
    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []


def test_emit_packages_returns_empty(ubuntu_cfg_factory):
    assert RULE.emit_packages(ubuntu_cfg_factory()) == []


def test_exception_entry_returns_none(ubuntu_cfg_factory):
    # Exceptions deferred until tailoring lands.
    assert RULE.exception_entry(ubuntu_cfg_factory()) is None
```

- [ ] **Step 6: Run the failing tests**

Run: `pytest tests/rules/test_ubuntu2404_admin_user_and_keys.py -v`
Expected: all FAIL with `ModuleNotFoundError: No module named 'ks_gen.rules.ubuntu2404.admin_user_and_keys'`.

- [ ] **Step 7: Create the rule module**

Create `src/ks_gen/rules/ubuntu2404/admin_user_and_keys.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import admin_user_and_keys as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        # ubuntu2404 admin user creation lives in the cloud-init `users:`
        # block of user-data.j2 (rendered directly from cfg.user.admin).
        # No late-command needed; cloud-init runs before late-commands and
        # handles user provisioning natively.
        return ""

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return None


RULE: Rule = cast(Rule, _Rule())
```

- [ ] **Step 8: Run the rule tests (expect PASS)**

Run: `pytest tests/rules/test_ubuntu2404_admin_user_and_keys.py -v`
Expected: all six PASS.

- [ ] **Step 9: Run the registry test that counts ubuntu2404 rules**

Run: `pytest tests/test_registry.py -v`
Expected: all pass. `test_registry_ubuntu2404_returns_empty_list` may need updating — it asserts `rules == []`. We now have one ubuntu rule. Update the test name and assertion:

If `test_registry_ubuntu2404_returns_empty_list` still exists, replace its body with:

```python
def test_registry_ubuntu2404_loads_admin_user_and_keys():
    rules = load_rules("ubuntu2404")
    ids = {r.id for r in rules}
    assert "admin_user_and_keys" in ids
```

(Rename if you prefer; the original test's assertion `rules == []` is no longer true.)

- [ ] **Step 10: Run the writer tests — they still pass because emit_post is empty**

Run: `pytest tests/test_writer.py -v`
Expected: all PASS. `test_build_bundle_ubuntu2404_returns_distro_tagged_bundle` and friends still produce a bundle with empty `late-commands` because `admin_user_and_keys.emit_post` returns empty.

- [ ] **Step 11: Confirm alma9 goldens still byte-identical**

Run: `pytest tests/golden/ -v`
Expected: all 18 pass with zero snapshot updates.

- [ ] **Step 12: Commit**

```powershell
git add src\ks_gen\rules\ubuntu2404\admin_user_and_keys.py src\ks_gen\templates\user-data.j2 tests\rules\test_ubuntu2404_admin_user_and_keys.py tests\test_skeleton_ubuntu.py tests\test_registry.py
git -c user.email="github.v5f9w@bitbucket.onl" `
    -c user.signingkey=BE707B220C995478 `
    commit -S -m "feat(rules/ubuntu2404): port admin_user_and_keys (skeleton-driven)

First ubuntu2404 rule. Per spec §6: cloud-init handles user creation
natively via the autoinstall `users:` block — no late-command, no
package, no tailoring. emit_post returns empty; the work lives in
user-data.j2's new top-level `users:` block (sibling to identity).

emit_tailoring and exception_entry return empty pending a survey of
ssg-ubuntu2404-ds.xml rule IDs; a follow-up PR will tailor the right
Ubuntu STIG rules out.

Updates the registry test that previously asserted ubuntu2404 had
zero rules."
```

---

### Task 4: Port `ssh_keep_open` for ubuntu2404 (first late-command)

**Files:**
- Create: `src/ks_gen/rules/ubuntu2404/ssh_keep_open.py`
- Create: `tests/rules/test_ubuntu2404_ssh_keep_open.py`
- Modify: `tests/test_writer.py` — new assertion that a ubuntu2404 bundle now produces a non-empty `late-commands`

**Goal:** Ship the first ubuntu2404 rule that produces a late-command. Single line: `ufw allow {port}/tcp`, gated by `cfg.overrides.ssh_keep_open.ensure_ufw_port`.

- [ ] **Step 1: Write failing tests for the rule**

Create `tests/rules/test_ubuntu2404_ssh_keep_open.py`:

```python
from ks_gen.rules.ubuntu2404.ssh_keep_open import RULE


def test_applies_when_ensure_ufw_port_true(ubuntu_cfg_factory):
    # Default ubuntu2404 cfg has ensure_ufw_port=True.
    assert RULE.applies(ubuntu_cfg_factory()) is True


def test_does_not_apply_when_ensure_ufw_port_false(ubuntu_cfg_factory):
    from ks_gen.config import Overrides, SshKeepOpenCfg

    base = ubuntu_cfg_factory()
    cfg = base.model_copy(
        update={
            "overrides": Overrides(
                ssh_keep_open=SshKeepOpenCfg(ensure_ufw_port=False),
            )
        }
    )
    assert RULE.applies(cfg) is False


def test_emit_post_uses_ufw_with_configured_port(ubuntu_cfg_factory):
    from ks_gen.config import Ssh

    base = ubuntu_cfg_factory()
    cfg = base.model_copy(update={"ssh": Ssh(port=2222)})
    out = RULE.emit_post(cfg)
    assert "ufw allow 2222/tcp" in out
    # No SELinux analog, no firewalld; this rule is ufw-only.
    assert "semanage" not in out
    assert "firewall-offline-cmd" not in out


def test_emit_post_default_port_22(ubuntu_cfg_factory):
    out = RULE.emit_post(ubuntu_cfg_factory())
    assert "ufw allow 22/tcp" in out


def test_emit_packages_includes_ufw(ubuntu_cfg_factory):
    assert RULE.emit_packages(ubuntu_cfg_factory()) == ["ufw"]


def test_emit_tailoring_returns_empty(ubuntu_cfg_factory):
    # Deferred until ssg-ubuntu2404-ds.xml survey lands.
    assert RULE.emit_tailoring(ubuntu_cfg_factory()) == []


def test_exception_entry_returns_none(ubuntu_cfg_factory):
    assert RULE.exception_entry(ubuntu_cfg_factory()) is None


def test_id_and_summary_come_from_shared_meta(ubuntu_cfg_factory):
    from ks_gen.rules._meta import ssh_keep_open as meta

    assert RULE.id == meta.ID
    assert RULE.summary == meta.SUMMARY
```

- [ ] **Step 2: Run the failing tests**

Run: `pytest tests/rules/test_ubuntu2404_ssh_keep_open.py -v`
Expected: all FAIL with `ModuleNotFoundError: No module named 'ks_gen.rules.ubuntu2404.ssh_keep_open'`.

- [ ] **Step 3: Create the rule module**

Create `src/ks_gen/rules/ubuntu2404/ssh_keep_open.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from ks_gen.rules._meta import ssh_keep_open as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp

if TYPE_CHECKING:
    from ks_gen.config import HostConfig


def _emit(cfg: HostConfig) -> str:
    if not cfg.overrides.ssh_keep_open.ensure_ufw_port:
        return ""
    return f"ufw allow {cfg.ssh.port}/tcp\n"


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=lambda: list(meta.DEPENDS_ON))
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return cfg.overrides.ssh_keep_open.ensure_ufw_port

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return []

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return ["ufw"]

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return None


RULE: Rule = cast(Rule, _Rule())
```

- [ ] **Step 4: Run the rule tests (expect PASS)**

Run: `pytest tests/rules/test_ubuntu2404_ssh_keep_open.py -v`
Expected: all eight PASS.

- [ ] **Step 5: Write a failing test that the writer now produces a non-empty late-commands**

Append to `tests/test_writer.py`:

```python
def test_build_bundle_ubuntu2404_late_commands_includes_ufw_entry(tmp_path):
    yaml_text = textwrap.dedent(
        """\
        distro: ubuntu2404
        system: {hostname: u24-late}
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
    assert bundle.user_data is not None
    import yaml as _yaml

    doc = _yaml.safe_load(bundle.user_data)
    late = doc["autoinstall"]["late-commands"]
    assert len(late) == 1
    assert "ufw allow 22/tcp" in late[0]
    assert "# rule:ssh_keep_open" in late[0]
```

- [ ] **Step 6: Run the failing test**

Run: `pytest tests/test_writer.py::test_build_bundle_ubuntu2404_late_commands_includes_ufw_entry -v`
Expected: PASS — Task 3's wiring + Task 4's rule together make this work end-to-end. (If it FAILs, the rule isn't being loaded — check `pkgutil.iter_modules` discovery via `load_rules("ubuntu2404")`.)

- [ ] **Step 7: Run the full suite**

Run: `pytest -q`
Expected: all pass. Note: `test_build_bundle_ubuntu2404_tailoring_is_valid_xccdf_skeleton` still passes (no rule contributes tailoring ops). `test_build_bundle_ubuntu2404_returns_distro_tagged_bundle` still passes (still a valid Bundle, still has a non-None `user_data` / `meta_data`).

- [ ] **Step 8: Confirm alma9 goldens still byte-identical**

Run: `pytest tests/golden/ -v`
Expected: all 18 pass with zero snapshot updates.

- [ ] **Step 9: Commit**

```powershell
git add src\ks_gen\rules\ubuntu2404\ssh_keep_open.py tests\rules\test_ubuntu2404_ssh_keep_open.py tests\test_writer.py
git -c user.email="github.v5f9w@bitbucket.onl" `
    -c user.signingkey=BE707B220C995478 `
    commit -S -m "feat(rules/ubuntu2404): port ssh_keep_open (first late-command)

Single line: 'ufw allow {port}/tcp'. Gated by the new
cfg.overrides.ssh_keep_open.ensure_ufw_port field (defaults true).
emit_packages declares ufw. Distinct from alma9's semanage +
firewall-offline-cmd path; ubuntu's only firewall + MAC story is ufw +
AppArmor, and AppArmor doesn't gate ports.

emit_tailoring and exception_entry return empty pending the ubuntu STIG
rule-ID survey; a follow-up PR will tailor out the Ubuntu STIG rules
that would otherwise close the configured ssh port."
```

---

### Task 5: First ubuntu2404 golden snapshot

**Files:**
- Create: `tests/golden/ubuntu-minimal.host.yaml`
- Create: `tests/golden/test_ubuntu_minimal.py`
- Snapshot file created on first run: `tests/golden/__snapshots__/test_ubuntu_minimal.ambr`

**Goal:** Pin the end-state of phase 3.0 with a syrupy snapshot, mirroring the alma9 `test_minimal_dhcp.py` pattern. Future phase 3 PRs (more rule ports) update this snapshot deliberately.

- [ ] **Step 1: Create the golden YAML fixture**

Create `tests/golden/ubuntu-minimal.host.yaml`:

```yaml
distro: ubuntu2404
system:
  hostname: u24-min
user:
  admin:
    name: opsadmin
    authorized_keys:
      - "ssh-ed25519 AAAA a@b"
    sudo: nopasswd_yes
```

- [ ] **Step 2: Create the golden test file (will fail on first run because snapshots don't exist yet)**

Create `tests/golden/test_ubuntu_minimal.py`:

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


def test_ubuntu_minimal(snapshot):
    yaml_path = Path(__file__).parent / "ubuntu-minimal.host.yaml"
    cfg = load_host_config(yaml_path, sets=[])
    bundle = build_bundle(cfg)
    assert bundle.user_data is not None
    assert bundle.meta_data is not None
    assert _normalize(bundle.user_data) == snapshot(name="user-data")
    assert _normalize(bundle.meta_data) == snapshot(name="meta-data")
    assert _normalize(bundle.tailoring_xml) == snapshot(name="tailoring.xml")
    assert _normalize(bundle.exceptions_md) == snapshot(name="exceptions.md")
    assert _normalize(bundle.host_yaml) == snapshot(name="host.yaml")
```

- [ ] **Step 3: Generate the snapshot file**

Run: `pytest tests/golden/test_ubuntu_minimal.py --snapshot-update -v`
Expected: PASS with `5 snapshots generated` (one per artifact). The file `tests/golden/__snapshots__/test_ubuntu_minimal.ambr` now exists.

- [ ] **Step 4: Inspect the generated snapshot before committing**

Read the new snapshot file:

```powershell
Get-Content tests\golden\__snapshots__\test_ubuntu_minimal.ambr
```

Sanity-check that the output matches expectations:
- `user-data` snapshot starts with `#cloud-config`, contains an `identity:` block with `hostname: "u24-min"`, a `users:` block with one entry (`opsadmin`, `NOPASSWD`, the ed25519 key), and ONE `late-commands` entry whose body contains `# rule:ssh_keep_open` and `ufw allow 22/tcp`
- `meta-data` snapshot is two lines: `instance-id: "u24-min"` and `local-hostname: "u24-min"`
- `tailoring.xml` snapshot contains `<xccdf:Tailoring>` but NO `<xccdf:select>` (no rule contributes tailoring ops yet)
- `exceptions.md` snapshot lists the two applied rules (`admin_user_and_keys`, `ssh_keep_open`) under "Applied rules", reports `Tailored XCCDF rules: 0`, `Declared exceptions: 0`
- `host.yaml` snapshot is a round-trip of the input config plus pydantic defaults — `distro: ubuntu2404`, `ensure_ufw_port: true` should appear

If anything looks unexpected, STOP and report DONE_WITH_CONCERNS with the surprise. Otherwise proceed.

- [ ] **Step 5: Re-run without --snapshot-update to confirm the snapshot locks in**

Run: `pytest tests/golden/test_ubuntu_minimal.py -v`
Expected: PASS with `5 snapshots passed`.

- [ ] **Step 6: Full suite + alma9 goldens still byte-identical**

Run:
```powershell
pytest -q
pytest tests\golden\ -v
```
Expected: all pass. Specifically: the existing 18 alma9 golden tests pass with zero snapshot updates; the new `test_ubuntu_minimal` passes.

- [ ] **Step 7: Commit**

```powershell
git add tests\golden\ubuntu-minimal.host.yaml tests\golden\test_ubuntu_minimal.py tests\golden\__snapshots__\test_ubuntu_minimal.ambr
git -c user.email="github.v5f9w@bitbucket.onl" `
    -c user.signingkey=BE707B220C995478 `
    commit -S -m "test(golden): first ubuntu2404 golden snapshot

Pins the end-state of phase 3.0: user-data with identity + users + one
ufw late-command, meta-data with instance-id/local-hostname, empty
tailoring.xml skeleton, exceptions.md listing the two applied rules
without any tailored XCCDF rules, host.yaml round-trip.

Future phase 3 PRs that port more rules will update this snapshot
deliberately. The acceptance bar for those PRs is: snapshot diff
matches exactly what the new rule adds, nothing else."
```

---

### Task 6: Final verification + push + PR

**Goal:** Confirm the alma9 contract one more time, push the branch, open a PR against `main`.

- [ ] **Step 1: Confirm the current branch and commit count**

```powershell
git -C C:\Users\yizshachuck\source\ks-gen branch --show-current
git -C C:\Users\yizshachuck\source\ks-gen log --oneline main..HEAD
```
Expected: branch name like `feat/phase-3-late-commands-and-first-rules`; five new commits (one per Task 1–5 — plus the controller's initial plan-doc commit, which is fine).

- [ ] **Step 2: Final CI parity check**

```powershell
ruff check src tests
ruff format --check src tests
mypy
pytest -q
```
Expected: all green.

- [ ] **Step 3: Confirm alma9 goldens byte-identical one final time**

```powershell
pytest tests\golden\ -v
```
Expected: all 19 golden tests pass (18 alma9 + 1 new ubuntu), zero snapshot updates.

- [ ] **Step 4: Push the branch**

```powershell
git push -u origin HEAD
```

- [ ] **Step 5: Open the PR against `main`**

```powershell
gh pr create --base main --head $(git branch --show-current) --title "feat(rules/ubuntu2404): late-commands + admin_user_and_keys + ssh_keep_open (#81 phase 3.0)" --body "$(cat <<'EOF'
First PR of phase 3 of the Ubuntu 24.04 STIG autoinstall roadmap (#81). Builds on phase 2 (PR #92, squash `4304799`).

## Summary

- **`SshKeepOpenCfg` gains `ensure_ufw_port: bool = True`.** Specced in phase 1 §3.4 but deferred. Distinct from `ensure_firewalld_port` / `ensure_selinux_port`; defaults true.
- **`render_user_data(cfg, post_blocks)` replaces `render_user_data(cfg)`.** A new private `_format_late_commands` helper in `skeleton.py` assembles the YAML suffix for the `late-commands:` key. Per-entry shape: `- |\n    curtin in-target --target=/target -- bash -c <shlex-quoted body>`. Multi-line bash bodies survive via the YAML `|` literal block.
- **`_build_ubuntu2404_bundle` collects `PostBlock`s from rules** (mirroring the alma9 helper) and passes them to `render_user_data`.
- **`admin_user_and_keys` for ubuntu2404 ships skeleton-driven** per spec §6: `emit_post` returns empty; `user-data.j2` gains a top-level cloud-init `users:` block built from `cfg.user.admin` (name, sudo with `NOPASSWD:ALL` when `sudo == nopasswd_yes`, `shell: /bin/bash`, `ssh_authorized_keys`).
- **`ssh_keep_open` for ubuntu2404 ships as the first late-command:** single `ufw allow {port}/tcp` line, `emit_packages` declares `ufw`. Gated by `cfg.overrides.ssh_keep_open.ensure_ufw_port`.
- **First ubuntu2404 golden snapshot.** `tests/golden/ubuntu-minimal.host.yaml` + `tests/golden/__snapshots__/test_ubuntu_minimal.ambr`.

## What this PR does NOT do

- **No `emit_tailoring` / `exception_entry` for the two ubuntu rules.** Both return empty/None pending a survey of `ssg-ubuntu2404-ds.xml` rule IDs. Emitting placeholder XCCDF rule IDs would snapshot and ship — too dangerous. A follow-up PR closes the audit story.
- **No cross-distro post-validators on `SshKeepOpenCfg`.** Spec §3.3 says `ensure_selinux_port` / `ensure_firewalld_port` should reject on ubuntu and `ensure_ufw_port` should reject on alma9. Deferred to a follow-up so this PR stays focused.
- **No other rule ports.** 11 ubuntu2404 rules remain (banner_text, ssh_config_apply, dod_root_ca, time_servers, crypto_policy, faillock_safety, unattended_updates, kernel_module_blacklist, package_purge, usbguard, auditd_actions). Each gets its own PR per spec §11.

## Test plan

- [x] `ruff check src tests` clean
- [x] `ruff format --check src tests` clean
- [x] `mypy` clean
- [x] `pytest -q` green
- [x] All 18 alma9 golden snapshots byte-identical
- [x] New `test_ubuntu_minimal` golden passes; snapshot file checked in
- [x] New rule unit tests pass (six for admin_user_and_keys, eight for ssh_keep_open)
- [x] `load_rules("ubuntu2404")` discovers both rules
- [x] End-to-end: `build_bundle(ubuntu_cfg)` produces a `user-data` whose `late-commands` list has exactly one entry containing `# rule:ssh_keep_open` and `ufw allow 22/tcp`
EOF
)"
```

- [ ] **Step 6: Capture and report the PR URL**

The `gh pr create` output ends with the PR URL. Report it back along with task completion.

---

## Done criteria

- `SshKeepOpenCfg.ensure_ufw_port` exists with default `True`.
- `render_user_data(cfg, post_blocks)` produces valid YAML with identity + users + late-commands.
- `_build_ubuntu2404_bundle` collects rule post bodies; produces non-empty `late-commands` when ubuntu rules contribute.
- Two ubuntu2404 rules ship: `admin_user_and_keys` (skeleton-only) and `ssh_keep_open` (one ufw late-command).
- First ubuntu2404 golden snapshot pins the result; alma9 goldens unchanged.
- Five signed commits land on a feature branch; PR opened against `main`.

## What is NOT in this plan

- Other ubuntu2404 rule ports — phase 3.1 onward (one PR per rule per spec §11).
- `emit_tailoring` / `exception_entry` for `admin_user_and_keys` / `ssh_keep_open` — follow-up PR after ssg-ubuntu2404-ds.xml survey.
- Cross-distro post-validators on `SshKeepOpenCfg` — follow-up PR.
- Wizard distro prompt — belongs in the PR where the wizard first gains ubuntu2404 awareness.
- `verify/*` distro awareness — phase 4 per spec §11.
- `MANUAL.md` / `README.md` updates — premature; the bundle isn't operator-ready until more rules land.
