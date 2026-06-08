# `ks-gen new` wizard — disk, network, override matrix — design

**Issue:** [#9 — ks-gen new wizard: add prompts for disk, network, and override matrix](https://github.com/SupremeCommanderHedgehog/ks-gen/issues/9)

**Status:** draft 2026-06-08

**Goal:** Extend the existing `ks-gen new` wizard so a first-time
operator can produce a complete `host.yaml` covering disk layout,
network configuration, and the ks-gen-owned override matrix without
ever hand-editing the YAML. Close the v0.1 limitation called out in
`MANUAL.md` §3.3.

## Background

`ks-gen new` today (88 lines of `src/ks_gen/wizard.py`) prompts only
for system / user / SSH / crypto. Anything past that — disk preset
choice, LUKS encryption, per-interface network, per-rule overrides —
requires the operator to hand-edit `host.yaml` and re-run
`ks-gen gen`. The wizard module has no test file (`tests/test_wizard.py`
does not exist); the original 4 prompts went out untested.

Three things changed since the issue was filed:
- LUKS presets shipped in v0.5.0 (`disk.luks.preset` + `partial`/`tang`),
  so the issue's "passthrough to LUKS preset (#7) once that lands"
  is now in scope.
- The `disk.layout` block shipped in v0.4.0 — full custom LVM is
  declarable in YAML; the wizard does **not** need to scaffold it.
- `iso.py` was promoted to a package in v0.6.0 (commit `85994fc`);
  this design follows that pattern for `wizard.py`.

## Goals

- Group-selector entry: a single questionary checkbox prompt opts
  the operator into any combination of the three new sections.
  Skipping a section accepts schema defaults, producing output
  byte-identical to today's wizard.
- Disk: preset (`stig_server` / `minimal`) + wipe + LUKS
  (`none` / `partial` only). The `partial` branch prompts for an
  inline passphrase (with mismatch retry) or a sidecar file path.
- Network: per-interface loop (device, bootproto, static fields,
  nameservers) with "add another?" continuation.
- Override matrix: two checkbox prompts driven by a small static
  mapping — default-on rules to disable, default-off rules to
  enable. Unchecked items remain at schema defaults.
- `--non-interactive` continues to work as today: skip all optional
  groups, apply existing defaults, emit the same YAML it does now.
- Close the missing-test gap: introduce `tests/test_wizard.py`
  covering both the new prompt groups and the existing four.

## Non-goals (deferred)

- `ks-gen edit` for amending an existing `host.yaml` in-place. Resume
  / pre-fill is out of scope; this PR errors on existing output dir.
- Bond / bridge / VLAN interface prompts. The Anaconda surface is
  large and the wizard would balloon; hand-edit the
  `network.interfaces` list when needed.
- Override matrix "customize" depth — no nested-field prompts (no
  `faillock.deny`, no `unattended_updates.nightly_security.on_calendar`,
  no `kernel_module_blacklist.modules` list editing). Hand-edit.
- LUKS `tang` preset prompts (URLs, thumbprints, threshold). Wizard
  refuses tang at the LUKS-preset choice and prints a hand-edit hint.
- Custom `disk.layout:` scaffolding. The wizard offers only the two
  existing presets; operators wanting a custom LVM layout hand-edit
  the YAML against the v0.4.0 `disk.layout` block.
- `overrides.fips_mode` toggle. Conflicts with default `MODERN`
  crypto policy (existing `_crypto_fips_mutex` validator); requires
  coordinated edits of `crypto.policy` to `STIG`. Hand-edit only.
- `auditd_actions`, `ssh_keep_open` overrides. Neither has a binary
  `enable` field in the schema; tuning them means setting action
  enums / ensure_* booleans. Hand-edit.
- `exceptions: list[ExceptionDecl]` prompts. Operator must declare
  specific STIG rule IDs with reasons; needs domain knowledge.

## Architecture

`src/ks_gen/wizard.py` promotes to a package, mirroring the v0.6.0
`iso/` promotion:

```
src/ks_gen/wizard/
├── __init__.py    # public API: run_wizard, write_initial, WizardError
├── _prompts.py    # questionary adapter + non-interactive fallbacks
├── _core.py       # system / user / ssh / crypto (the existing four)
├── _disk.py       # disk group
├── _network.py    # network group
└── _overrides.py  # override matrix + _OVERRIDE_TOGGLES mapping
```

`__init__.py` re-exports `run_wizard`, `write_initial`, and
`WizardError` so `cli.py`'s existing import line is unchanged.

`_prompts.py` is the only file that imports `questionary`. The
import line carries `# type: ignore[import-untyped]` (questionary
ships no stubs). The adapter's outward-facing functions
(`select_one`, `ask_text`, `ask_confirm`, `ask_password`,
`ask_checkbox`, `loop_until_blank`) are typed strictly. All other
wizard files import from `_prompts`, never directly from
`questionary`. This bounds the type-erasure to a single file.

Each `_disk` / `_network` / `_overrides` module exports one entry
point — `prompts() -> dict[str, Any]` — which returns a fragment to
be merged into the final `HostConfig` payload. These helpers are
interactive-only: they are reached only when the operator opted into
their group via the (interactive) group selector. Non-interactive
mode bypasses them entirely.

`_core.prompts(interactive: bool)` returns the four existing fragments
(`system`, `user`, `ssh`, `crypto`) — `_core` retains the param
because today's wizard supports both modes for the required prompts.
The flow inside `run_wizard`:

```python
payload = _core.prompts(interactive)
if interactive:
    selected = _ask_groups()  # checkbox: which optionals?
else:
    selected = set()  # non-interactive skips all optionals
if "disk" in selected:
    payload["disk"] = _disk.prompts()
if "network" in selected:
    payload["network"] = _network.prompts()
if "overrides" in selected:
    payload["overrides"] = _overrides.prompts()
cfg = HostConfig.model_validate(payload)
yaml_text = yaml.safe_dump(cfg.model_dump(mode="json"),
                            sort_keys=False, default_flow_style=False)
return cfg, yaml_text
```

## UX walkthrough

### Group selector

A single questionary checkbox prompt, optional groups only. The four
required groups (system / user / ssh / crypto) run unconditionally
before this prompt.

```
? Configure which optional sections? (Space to toggle, Enter to confirm)
    ◯ Disk layout (preset, LUKS)
    ◯ Network (interfaces)
    ◯ Override matrix (per-rule toggles)
```

Empty selection is valid — produces today's wizard YAML.

### Disk group

```
[Disk]
? Disk preset:                        [select]
  ❯ stig_server  — LVM with STIG-required mountpoints (recommended)
    minimal      — single root partition, no audit mount split

? Wipe disk on install? [Y/n]         [confirm, default true]

# preset = minimal: skip LUKS prompt (schema validator
# `_minimal_preset_rejects_luks` would reject luks != none).
# Print: "minimal preset has no LVM PV; skipping LUKS prompt."

? LUKS encryption:                    [select]
  ❯ none     — no encryption
    partial  — passphrase-unlocked LUKS on the LVM PV
   # tang not offered; hand-edit hint below the prompt:
   #   "tang requires URLs + thumbprints + threshold; hand-edit
   #    disk.luks if you need it."

# luks = none: done.
# luks = partial: ask passphrase source.

? Passphrase source:                  [select]
  ❯ inline  — type now (stored in plaintext in host.yaml)
    file    — path to sidecar file (read at bundle build)
   # NOTE printed once: "inline passphrase is stored in plaintext
   # in host.yaml — for production use the 'file' option."

? Passphrase:                         [password, hidden input]
? Confirm passphrase:                 [password, hidden input]
   # validate: both match, non-empty after strip; on mismatch
   # re-prompt up to 3 times, then WizardError.

? Passphrase file path:               [text, no FS check at wizard time]
   # resolve_passphrase() validates the path exists + non-empty
   # at bundle build, per disk_luks.py.
```

Skipped (hand-edit hint in the wizard's preamble): `disk.layout`,
`disk.bootloader_password`.

### Network group

```
[Network]
? Interface device: [link]              [text, default "link"]
   # "link" = first up link Anaconda finds at install time

? Bootproto:                            [select]
  ❯ dhcp
    static

? Bring up on boot? [Y/n]               [confirm, default true]

# bootproto = dhcp: done with this interface.
# bootproto = static: ask ip, netmask, gateway, nameservers.

? IPv4 address (e.g., 10.0.0.10):       [text, validate dotted-quad]
? Netmask (e.g., 255.255.255.0):        [text, validate dotted-quad]
? Gateway (e.g., 10.0.0.1):             [text, validate dotted-quad]
? Nameserver (blank to stop):           [text loop]
   # mirrors the existing _ask_keys pattern for SSH keys;
   # empty list is a valid result (pydantic default is []).
   ...

? Configure another interface? [y/N]    [confirm, default false]
   # loop back to "Interface device" if yes
```

Dotted-quad regex: `^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$`. Catches
typos before pydantic; not octet-range-aware. Pydantic's `Interface`
already enforces `static` requires `ip`/`netmask`/`gateway`, so the
wizard relies on the schema for that invariant.

Skipped (hand-edit): `network.dns_search`, `network.hostname_from_dhcp`.

### Override matrix

A small static mapping in `_overrides.py` drives the two checkbox
prompts:

```python
# wizard/_overrides.py
_OVERRIDE_TOGGLES: dict[str, tuple[str, bool, str]] = {
    # cfg-field-name        -> (toggle-attr, default, one-line label)
    "faillock":                ("enable",  True,  "account lockout policy"),
    "kernel_module_blacklist": ("enable",  True,  "blacklist USB-storage, cramfs, etc."),
    "package_purge":           ("enable",  True,  "remove telnet-server, rsh-server, etc."),
    "unattended_updates":      ("enable",  True,  "nightly + monthly + reboot timers"),
    "usbguard":                ("enable",  False, "USB device control daemon"),
    "dod_root_ca":             ("install", False, "install DoD root CA bundle"),
}
```

Partition by the default value:

```
[Override matrix]
? Default-on rules to DISABLE (Space to toggle):
    ◯ faillock                — account lockout policy
    ◯ kernel_module_blacklist — blacklist USB-storage, cramfs, etc.
    ◯ package_purge           — remove telnet-server, rsh-server, etc.
    ◯ unattended_updates      — nightly + monthly + reboot timers

? Default-off rules to ENABLE (Space to toggle):
    ◯ usbguard                — USB device control daemon
    ◯ dod_root_ca             — install DoD root CA bundle
```

**Payload build**: for each checked item, the wizard sets
`overrides.<cfg>.<toggle-attr> = not <default>`. Empty selections
on both prompts produce `{}` (i.e., the `overrides` key is omitted
from the payload, accepting `Overrides()`'s schema defaults).

**Auto-extension story**: a new override `Cfg` block requires adding
one line to `_OVERRIDE_TOGGLES`. The mapping is the cost of the
schema asymmetry (not every cfg has a uniform `enable` field). A
consistency test pins `_OVERRIDE_TOGGLES` keys against the
`Overrides.model_fields` keys it claims to handle, so a renamed or
removed cfg block fails the test loudly.

## Error handling

- `KeyboardInterrupt` (Ctrl-C in any questionary prompt) — caught at
  the top of `run_wizard()`, re-raised as
  `WizardError("aborted by user")`. CLI exits `USAGE`.
- `EOFError` (stdin closed) — `WizardError("unexpected EOF on stdin")`,
  exit `USAGE`. Matches today's behavior.
- Pydantic `ValidationError` from the final
  `HostConfig.model_validate(payload)` — propagates. CLI catches and
  exits `CONFIG_INVALID`. Wizard-side validation (dotted-quad,
  passphrase confirm) catches the common cases before the model build.
- Inline-passphrase confirm mismatch — re-prompt up to 3 times, then
  `WizardError("passphrase confirmation mismatch after 3 attempts")`.
- Dotted-quad regex failure — questionary's `validate=` callback
  re-prompts inline (built-in UX, no special handling needed).
- `--non-interactive` with no defaults available — already errors
  today via `_ask()`; the new helpers preserve this behavior.

## Testing strategy

New file `tests/test_wizard.py` covers both the existing four prompts
and the new groups. Three test layers:

1. **Structural** — `run_wizard(interactive=False)` end-to-end. Asserts
   payload byte-equals today's wizard YAML when no optional groups
   are selected (pins the acceptance criterion).
2. **Mocked prompts** — `monkeypatch` `questionary.select` / `text` /
   `confirm` / `checkbox` / `password` at the wizard's adapter
   module. Inject scripted return values via lists popped per call.
   One test per group helper covering main paths and branches.
3. **Pure-function** — `_OVERRIDE_TOGGLES` keys consistency vs
   `Overrides.model_fields`, dotted-quad regex positive + negative,
   passphrase mismatch retry counter, payload-build helpers.

Error-path tests: `KeyboardInterrupt`, `EOFError`, missing-required
in `--non-interactive`. Each maps to `WizardError` with the expected
message.

Coverage target: every public-ish function in `wizard/` has at least
one positive and one negative test (no line-percentage gate).
mypy --strict and ruff stay clean.

## Dependencies & mypy

- `pyproject.toml [project.dependencies]` adds `questionary` with a
  lower bound at the latest stable at implementation time, no upper
  bound (matches the repo's general approach to runtime deps).
- `questionary` ships no type stubs. Single-file scope: import only
  in `wizard/_prompts.py` with `# type: ignore[import-untyped]` on
  the import line. The adapter's outward-facing functions are typed.
  No project-wide mypy override.
- Transitive: `questionary` pulls `prompt_toolkit`. No expected
  conflict with current deps (typer/click pull `prompt_toolkit` only
  optionally — verify at implementation time, downgrade strategy if
  pin clash: pin `prompt_toolkit` in `pyproject.toml`).

## Docs to update in the same PR

- `MANUAL.md` §3.3 — replace the v0.1 limitation note ("wizard only
  prompts for system/user/SSH/crypto") with the new walkthrough.
  Cover the group selector, each new section, and the explicit
  "still hand-edit" list (`disk.layout`, `bootloader_password`,
  `tang`, `fips_mode`, `auditd_actions`, `ssh_keep_open`, nested
  cfg fields, `exceptions`).
- `README.md` — quickstart update if it currently directs operators
  to hand-edit `host.yaml` for disk/network. Check at implementation
  time.
- `CHANGELOG.md` — release-please generates from conventional
  commits; no manual edit.

## Acceptance criteria

1. Wizard with no optional groups selected produces YAML
   byte-identical to today's output. Golden test pins this.
2. Wizard with all three optional groups selected produces a
   `host.yaml` that round-trips through `ks-gen gen` with no
   errors and lints clean.
3. `--non-interactive` works for the four required groups, defaults
   to skipping all optional groups, and produces the same output as
   pre-PR `--non-interactive`.
4. `tests/test_wizard.py` exists; every public-ish function in
   `wizard/` has at least one positive and one negative test.
   mypy --strict + ruff stay clean.
5. `MANUAL.md` §3.3 no longer mentions the v0.1 wizard limitation.
6. `_OVERRIDE_TOGGLES` consistency test fails if a cfg block is
   renamed or removed from `Overrides`.
7. CI green on 3.11/3.12/3.13. Local CI parity chain
   (`ruff check && ruff format --check && mypy && pytest -q`) clean
   before commit.
