# alma8 phase 1 — schema + dispatch

**Parent:** #121 (AlmaLinux 8 support tracking issue).

## Goal

Enable `distro: alma8` as a valid value for `HostConfig.distro` and plumb it through bundle generation. After this phase:

- `host.yaml` files with `distro: alma8` parse without error.
- `meta.scap_content` auto-injects to `ssg-almalinux8-ds.xml` when not explicitly set.
- `build_bundle(cfg)` returns a `Bundle(distro="alma8", ...)` with `ks_cfg` populated (same payload shape as alma9) — empty Applied-rules section, but a real, parseable kickstart.
- `ks-gen iso` and `ks-gen verify` continue to work for alma9 / ubuntu2404 hosts without regression (alma8 versions of those flows are out of scope for phase 1).
- A new `tests/golden/alma8-minimal.host.yaml` fixture + golden test pin the end-state.

This is the same shape as #81 phase 1 for ubuntu2404 (distro discriminator + per-distro registry dispatch, PR #90 at v0.14.0), but lighter weight because alma8 reuses the alma9 installer language (kickstart), bundle shape, and writer code path.

## Open-question decisions (resolves #121's Q1–Q3; defers Q4–Q6)

1. **Schema shape (Q1) — extend the `distro:` enum.** From `Literal["alma9", "ubuntu2404"]` to `Literal["alma9", "alma8", "ubuntu2404"]`. Operator UX stays identical; no separate top-level config. Same decision as #81 phase 1.
2. **Rule porting strategy (Q2) — per-rule sibling files at `src/ks_gen/rules/alma8/<name>.py`.** Matches the established #81 phase 3.x pattern. Phase 1 ships an *empty* `src/ks_gen/rules/alma8/__init__.py`; phase 2 starts porting rules one PR at a time. Rejected: a shared `rules/_rhel_family/` base — the per-rule SSG ID differences will land in `emit_tailoring` and `exception_entry` anyway (deferred to audit-story workstream, same as ubuntu2404), so a shared base wouldn't reduce per-rule code by much and would complicate the per-rule review story.
3. **Golden test coverage (Q3) — one `alma8-minimal.host.yaml` fixture for phase 1.** Pin: distro round-trip, scap_content auto-injection, empty Applied-rules registry, ks.cfg + tailoring + exceptions all render without error. Additional fixtures (alma8 with disk layouts, LUKS, containers, etc.) ship per-rule in phase 2 if the rule warrants its own scenario.
4. **Per-rule meaningful divergences (Q4) — defer to phase 2.** Each rule's port PR surfaces its own alma8 vs alma9 deltas in that PR's spec. The expected list (`crypto_policy`, possibly `kernel_module_blacklist` defaults for AL8 4.18 kernel) is documented in #121 but doesn't drive phase 1 design.
5. **ISO builder bootloader rewriter (Q5) — defer to phase 3.** Phase 1 ships nothing for `ks-gen iso` on alma8; `src/ks_gen/iso/bootloader.py` needs verification against AL8 isolinux/grub paths before alma8 ISO builds work. Tracked as a phase 3 task on #121.
6. **`ks-gen verify` (Q6) — defer.** `verify/reconcile.py` is already distro-aware (works for both alma9 and ubuntu2404). The change for alma8 is additive — just ensuring the rule-ID set comes from the alma8 datastream — but it's exercised end-to-end only when an alma8 host actually exists. Defer.

## Architecture

### Files modified

- `src/ks_gen/config.py`:
  - Add `"alma8": "ssg-almalinux8-ds.xml"` to `_DEFAULT_SCAP_CONTENT_BY_DISTRO`.
  - Extend `HostConfig.distro` Literal to `"alma9" | "alma8" | "ubuntu2404"`.
  - `_scap_content_matches_distro_before` validator is already generic — uses `_DEFAULT_SCAP_CONTENT_BY_DISTRO[distro]` for the expected value and only special-cases `alma9` as the auto-inject *exemption* (alma9 is the default, doesn't need injection). alma8 falls into the "not alma9" branch and gets auto-injection. No edit needed.

- `src/ks_gen/writer.py`:
  - Extend `Bundle.distro` Literal to `"alma9" | "alma8" | "ubuntu2404"`.
  - `Bundle.__post_init__`: add an `alma8` branch that mirrors the `alma9` shape (requires `ks_cfg`, must not set `user_data` / `meta_data`). Reuses alma9's error messages with the appropriate distro substring.
  - `build_bundle`: add `alma8` dispatch branch.
  - Decision: **dispatch alma8 to a shared kickstart-family helper.** Refactor `_build_alma9_bundle` to `_build_rhel_family_bundle(cfg, distro)` taking the distro string as a parameter; both `alma9` and `alma8` call into it. The bundle's `distro=` field is set from the parameter. This avoids the near-duplicate `_build_alma8_bundle` that would otherwise just be a copy of `_build_alma9_bundle` with one line changed.
  - `write_bundle`: add `alma8` branch (writes `ks.cfg` + `tailoring.xml` + `host.yaml` + `exceptions.md`, same as alma9).

- `src/ks_gen/cli.py`:
  - `gen_cmd` and `bundle_cmd` (or wherever `lint_kickstart` is invoked): the `if bundle.distro == "alma9":` guard becomes `if bundle.distro in ("alma9", "alma8"):` — alma8 produces a ks.cfg and needs the same lint invariants applied. The skip-for-ubuntu rationale remains valid.
  - `rules` command's `--distro` option default stays `"alma9"`; help text could mention alma8 as a valid value, but the click/typer Literal handling already enforces it.

### Files created

- `src/ks_gen/rules/alma8/__init__.py` — **empty** marker file. `load_rules("alma8")` returns `[]` until phase 2 starts populating rules.
- `tests/golden/alma8-minimal.host.yaml` — minimal fixture, identical to `alma9` minimal but with `distro: alma8`.
- `tests/golden/test_alma8_minimal.py` — golden test asserting the alma8 bundle renders.

### Unchanged

- `src/ks_gen/registry.py` — already distro-agnostic (`load_rules(distro)` parameterized; returns `[]` cleanly on `ModuleNotFoundError`).
- `src/ks_gen/skeleton.py` — kickstart template renders for alma8 same as alma9; the scap_content comes from `cfg.meta.scap_content` which is set via the config validator.
- `src/ks_gen/templates/ks.cfg.j2` and partials — distro-agnostic.
- `src/ks_gen/tailoring.py` — distro-agnostic; embeds `cfg.meta.scap_content` in the `<xccdf:Benchmark href=...>` attribute.

## Tests (phase 1 only)

### Schema-level

1. `test_distro_alma8_parses` — `HostConfig(distro="alma8", ...)` constructs without error.
2. `test_distro_alma8_auto_injects_scap_content` — when `meta` is omitted, `cfg.meta.scap_content == "ssg-almalinux8-ds.xml"`.
3. `test_distro_alma8_rejects_mismatched_scap_content` — explicit `meta.scap_content="ssg-almalinux9-ds.xml"` with `distro: alma8` raises ValueError mentioning both.
4. `test_distro_alma8_accepts_explicit_scap_content` — explicit `meta.scap_content="ssg-almalinux8-ds.xml"` works.

### Bundle-level

5. `test_alma8_bundle_has_ks_cfg_and_not_user_data` — `Bundle.__post_init__` enforces same shape as alma9.
6. `test_alma8_bundle_rejects_user_data` — setting `user_data` on an alma8 bundle raises.
7. `test_alma8_bundle_rejects_missing_ks_cfg` — missing `ks_cfg` on alma8 bundle raises.

### End-to-end (golden)

8. `test_alma8_minimal` (in `tests/golden/test_alma8_minimal.py`) — load `alma8-minimal.host.yaml`, call `build_bundle`, syrupy-snapshot the rendered `ks.cfg`, `host.yaml`, `tailoring.xml`, and `exceptions.md`. Expected:
   - `distro: alma8` in `host.yaml`
   - `meta.scap_content: ssg-almalinux8-ds.xml` in `host.yaml`
   - `Applied rules: 0` in `exceptions.md` (registry is empty for alma8)
   - Empty `<Profile>` in `tailoring.xml` (no tailoring ops contributed)
   - `ks.cfg` renders without error and contains `ssg-almalinux8-ds.xml` in the oscap command

### Registry-level

9. `test_load_rules_alma8_returns_empty` — `load_rules("alma8") == []` (phase 1 — populated in phase 2).

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Kickstart template has implicit alma9 assumptions (specific package names, comps groups, etc.) | The template uses `cfg.meta.scap_content` for the oscap call, and the `Packages.required` defaults (`scap-security-guide`, `openscap-scanner`, etc.) exist on both AL8 and AL9. Golden test catches any divergence by rendering an alma8 bundle. |
| `Packages.required` includes packages that exist on AL9 but not AL8 | Verified: all defaults (`scap-security-guide`, `openscap-scanner`, `aide`, `audit`, `rsyslog`, `chrony`, `firewalld`, `sudo`, `policycoreutils-python-utils`, `dnf-automatic`, `dnf-utils`) exist on RHEL 8.x and its rebuilds. Will be confirmed on first real install (phase 3 ISO+install validation). |
| Empty alma8 rules registry produces a kickstart that runs no `%post` overrides | Expected for phase 1. The oscap remediation in `%post` still runs (driven by the alma8 datastream's STIG rule set); operators just don't yet get the remote-safe exception layer until phase 2 ports rules. Documented in the spec; not blocking phase 1. |
| Bundle `__post_init__` regression on alma9 / ubuntu2404 | Add explicit test for each distro shape (already exists for alma9 / ubuntu2404). Run the full pytest suite as part of CI parity check. |
| `_scap_content_matches_distro_before` validator's hardcoded `if distro != "alma9":` falls through for alma8 cleanly because alma8 != alma9, but the literal might confuse a future reader | Comment update: clarify that the `alma9` branch is the *default-injection-exemption* (alma9 is the schema default), not a per-distro guard. Out of scope for this PR; could file a follow-up cleanup if it bites someone later. |

## CI parity check before push

Per `CLAUDE.md`:

```bash
ruff check src tests \
  && ruff format --check src tests \
  && mypy \
  && pytest -q
```

Expected new test count: `920 + ~9 = ~929`.

## Out of scope (per phase 1)

- Any rule under `src/ks_gen/rules/alma8/<name>.py` (phase 2).
- `ks-gen iso` for alma8 — bootloader rewriter version compatibility check (phase 3, #121 Q5).
- `ks-gen verify` end-to-end against an alma8 host (deferred, #121 Q6).
- Audit-story PR for alma8 SSG rule IDs (long-term, coordinates with ubuntu2404 audit-story).

## Plan note

This spec is the plan. Phase 1 is small enough (~50 LOC) that a separate plan document would be ceremonial. The implementation order:

1. config.py edits (schema + scap_content mapping) → schema-level tests pass
2. writer.py edits (Bundle Literal + dispatch + helper rename) → bundle-level tests pass
3. cli.py edit (lint dispatch) — small; no new tests strictly required but the existing lint tests should stay green
4. Empty `src/ks_gen/rules/alma8/__init__.py` → registry-level test passes
5. Golden fixture + test → end-to-end test passes
6. Local CI parity → push → PR → squash-merge after CI green
