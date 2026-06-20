# audit-story PR B — alma8 divergence + alma9 SSG-drift sweep

**Parent:** #127 (cross-distro audit-story).
**Phase 1 (data):** shipped v0.27.0 via PR #128.
**PR A (ubuntu2404):** shipped v0.28.0 via PR #130.

## Goal

Close the final two pieces of #127:

1. **alma9 SSG-drift sweep** — three of the alma9 rules' `emit_tailoring`
   methods reference SSG rule IDs that no longer exist in current
   `ssg-almalinux9-ds.xml` (0.1.80). Drift surfaced by cross-referencing
   the alma9 rules' hardcoded IDs against `docs/audit-story/alma9-rule-ids.txt`
   from phase 1. Cleanup is non-functional (oscap warns-and-continues on
   unknown IDs at install time) but makes `exceptions.md` an accurate audit
   trail and stops generating warn-noise.
2. **alma8 crypto_policy divergence** — alma8's SSG has 2 sshd cipher
   checks (`sshd_use_approved_kex_ordered_stig`, `sshd_use_approved_macs`)
   that alma9's SSG dropped. With the alma8 re-export from #121 phase 2,
   alma8 currently only disables what alma9 disables — missing those 2.
   Replace the alma8 `crypto_policy` re-export with a real implementation
   that adds the 2 alma8-specific disables on top of alma9's cleaned-up
   set. First real exercise of the "re-export → divergent impl" pattern
   from #121 phase 2's spec.

After this PR, **#127 is complete** end-to-end.

## Drift findings (from phase 1 data)

For each alma9 SSG rule ID hardcoded in `emit_tailoring`, cross-referenced
against `docs/audit-story/{alma8,alma9}-rule-ids.txt`:

| Rule | SSG rule ID | in alma9 ds | in alma8 ds | Action |
|---|---|---|---|---|
| crypto_policy | `enable_fips_mode` | ✓ | ✓ | keep |
| crypto_policy | `sshd_use_approved_ciphers` | ✓ | ✓ | keep |
| crypto_policy | `sshd_use_approved_kex` | ✗ | ✗ (only `_ordered_stig`) | **drop alma9; add alma8 `_ordered_stig`** |
| crypto_policy | `sshd_use_approved_macs` | ✗ | ✓ | **drop alma9; add alma8** |
| crypto_policy | `sshd_use_approved_mac_ordered` | ✗ | ✗ | **drop entirely** |
| faillock_safety | `accounts_passwords_pam_faillock_even_deny_root` | ✗ | ✗ | **rename to `_deny_root`** (both ds have this) |
| dod_root_ca | `install_DoD_intermediate_certificates` | ✗ | ✗ | **drop entirely** |
| banner_text (×3) | all 3 IDs | ✓ | ✓ | no change |
| auditd_actions (×3 vars) | all 3 var IDs | ✓ | ✓ | no change |
| usbguard (×3) | all 3 IDs | ✓ | ✓ | no change |

## alma9 sweep — per-rule cleanup

### `src/ks_gen/rules/alma9/crypto_policy.py`

```python
_TAILORED_WHEN_NOT_STIG = [
    f"{_PREFIX}enable_fips_mode",
    f"{_PREFIX}sshd_use_approved_ciphers",
]
```

Drops 3 stale IDs. Net effect: `emit_tailoring` returns 2 disables when
`cfg.crypto.policy != STIG` (was 5). `exception_entry.stig_rules_disabled`
list shrinks to 2. `stig_rules_affected` mirrors.

### `src/ks_gen/rules/alma9/faillock_safety.py`

```python
_RULE_DENY_ROOT = f"{_PREFIX}rule_accounts_passwords_pam_faillock_deny_root"
```

Renames `_RULE_EVEN_DENY_ROOT` → `_RULE_DENY_ROOT` (dropping the `even_`
prefix). All references updated. The cfg field `cfg.overrides.faillock.even_deny_root`
keeps its name — it's the operator-facing API, not the SSG ID. The
internal constant + the SSG reference are the only things renamed.

### `src/ks_gen/rules/alma9/dod_root_ca.py`

```python
@dataclass(frozen=True)
class _Rule:
    ...
    stig_rules_affected: list[str] = field(default_factory=list)

    def applies(self, cfg: HostConfig) -> bool:
        return not cfg.overrides.dod_root_ca.install

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return []  # install_DoD_intermediate_certificates no longer in SSG

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        return ExceptionEntry(
            rule_id=meta.ID,
            summary=meta.EXCEPTION_SUMMARY,
            stig_rules_disabled=[],  # nothing to disable on current SSG
            reason=meta.EXCEPTION_REASON,
        )
```

Drops `_RULE_ID = "xccdf_org.ssgproject.content_rule_install_DoD_intermediate_certificates"`.
`emit_tailoring` returns `[]`. `exception_entry` still returns the
operator-facing record (mirror what ubuntu2404 does — record opt-out for
the audit trail even with no SSG rule to actually disable).

## alma8 crypto_policy divergence

Replace `src/ks_gen/rules/alma8/crypto_policy.py` from a 5-line re-export
to a real implementation. The alma8 set is alma9's cleaned-up 2 IDs PLUS
2 alma8-only IDs:

```python
"""alma8 crypto_policy — diverges from alma9 to disable additional
sshd cipher rules that exist in ssg-almalinux8 (0.1.74) but not in
ssg-almalinux9 (0.1.80).

First real exercise of the "re-export → divergent impl" pattern from
#121 phase 2's spec: when a rule needs to actually differ between alma9
and alma8, its alma8 file becomes a real implementation. Other rules
stay as re-exports until/unless their SSG mappings diverge similarly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

# Reuse the alma9 implementation's emit_post + emit_packages —
# they're functionally identical on AL8. Only emit_tailoring +
# exception_entry need per-distro divergence here.
from ks_gen.rules._meta import crypto_policy as meta
from ks_gen.rules._types import ExceptionEntry, Rule, TailoringOp
from ks_gen.rules.alma9.crypto_policy import _emit_post  # internal helper, reused

if TYPE_CHECKING:
    from ks_gen.config import HostConfig

_PREFIX = "xccdf_org.ssgproject.content_rule_"
_TAILORED_WHEN_NOT_STIG = [
    f"{_PREFIX}enable_fips_mode",
    f"{_PREFIX}sshd_use_approved_ciphers",
    f"{_PREFIX}sshd_use_approved_kex_ordered_stig",
    f"{_PREFIX}sshd_use_approved_macs",
]


@dataclass(frozen=True)
class _Rule:
    id: str = meta.ID
    summary: str = meta.SUMMARY
    depends_on: list[str] = field(default_factory=list)
    stig_rules_affected: list[str] = field(default_factory=lambda: list(_TAILORED_WHEN_NOT_STIG))

    def applies(self, cfg: HostConfig) -> bool:
        return True

    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        if cfg.crypto.policy.value == "STIG":
            return []
        return [TailoringOp(rule_id=r, action="disable") for r in _TAILORED_WHEN_NOT_STIG]

    def emit_post(self, cfg: HostConfig) -> str:
        return _emit_post(cfg)

    def emit_packages(self, cfg: HostConfig) -> list[str]:
        return []

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        if cfg.crypto.policy.value == "STIG":
            return None
        return ExceptionEntry(
            rule_id=meta.ID,
            summary=f"{cfg.crypto.policy.value} crypto policy",
            stig_rules_disabled=list(_TAILORED_WHEN_NOT_STIG),
            reason=(
                f"{cfg.crypto.policy.value} accepts loss of FIPS 140-3 certification "
                "in exchange for Curve25519 / Ed25519 / ChaCha20-Poly1305 support."
            ),
        )


RULE: Rule = cast(Rule, _Rule())
```

The `_emit_post` helper in `alma9/crypto_policy.py` needs to be extracted
from the current module-level body into a named function (it's currently
inline in the `_Rule.emit_post` method). Small refactor.

After this divergence, `load_rules("alma8")` for `crypto_policy` returns
a different `RULE` singleton from `load_rules("alma9")` — the
`test_registry_alma8_re_exports_same_rule_instances_as_alma9` test from
#121 phase 2 needs updating to skip `crypto_policy` (or to check
"either same instance OR rule emits equivalent operations").

## Files touched

- **Modify:** `src/ks_gen/rules/alma9/crypto_policy.py` — drop 3 stale IDs; extract `_emit_post` to module level so alma8 can reuse.
- **Modify:** `src/ks_gen/rules/alma9/faillock_safety.py` — rename `_RULE_EVEN_DENY_ROOT` → `_RULE_DENY_ROOT`.
- **Modify:** `src/ks_gen/rules/alma9/dod_root_ca.py` — drop `_RULE_ID`; `emit_tailoring → []`; `exception_entry` keeps returning but with empty `stig_rules_disabled`.
- **Modify:** `src/ks_gen/rules/alma8/crypto_policy.py` — re-export → real implementation (adds 2 alma8-only IDs).
- **Modify:** corresponding test files (3 alma9 + 1 alma8) — assert the new ID sets.
- **Modify:** `tests/test_registry.py` — `test_registry_alma8_re_exports_same_rule_instances_as_alma9` carves out `crypto_policy` (alma8 now has its own implementation).
- **Modify (snapshots):** all alma9 golden snapshots that reference any of the changed exception text. Identified by grepping for the stale IDs in `tests/golden/__snapshots__/`:
  - `test_bare_metal_usbguard.ambr`
  - `test_container_host.ambr`
  - `test_container_host_lean.ambr`
  - `test_data_disks_mixed.ambr`
  - `test_data_disks_preserve_label.ambr`
  - (plus possibly more — full list verified at regen time)
  - `test_alma8_minimal.ambr` — alma8 also affected because re-exports inherit alma9's cleaned-up IDs, AND because crypto_policy now has different (larger) ops on alma8
- **No change:** ubuntu2404 implementations or snapshots (PR A's IDs are Ubuntu-specific and not affected by this sweep).

## Tests

### `tests/rules/test_crypto_policy.py` (alma9)

- Update tests asserting the 5-ID list → assert 2-ID list.
- Update tests asserting `stig_rules_disabled` length.

### `tests/rules/test_faillock_safety.py` (alma9)

- Update tests referencing `_even_deny_root` → `_deny_root` (in assertions only — cfg field name stays).

### `tests/rules/test_dod_root_ca.py` (alma9)

- Update test that asserted `[_RULE_ID]` in `stig_rules_disabled` → assert `[]`.
- Test that `emit_tailoring` returns `[]`.

### `tests/rules/test_alma8_crypto_policy.py` (NEW)

- Mirror the alma9 test structure with alma8-specific IDs.
- Assert `_TAILORED_WHEN_NOT_STIG` contains 4 IDs (alma9's 2 + alma8-only 2).
- Confirm same `cfg.crypto.policy` gating semantics.

### `tests/test_registry.py`

```python
def test_registry_alma8_re_exports_same_rule_instances_as_alma9():
    """alma8 rules that don't diverge from alma9 are re-exports.

    After PR B (#127), `crypto_policy` is alma8's first real divergent
    implementation (adds 2 sshd cipher disables that alma8 SSG has and
    alma9 SSG doesn't). All OTHER 14 rules remain re-exports.
    """
    alma9_rules = {r.id: r for r in load_rules("alma9")}
    alma8_rules = {r.id: r for r in load_rules("alma8")}
    _DIVERGENT = {"crypto_policy"}
    for rid, alma8_rule in alma8_rules.items():
        if rid in _DIVERGENT:
            assert alma8_rule is not alma9_rules[rid], (
                f"{rid} should NOT re-export the alma9 instance — it has a "
                "real alma8 implementation per audit-story PR B"
            )
        else:
            assert alma8_rule is alma9_rules[rid], (
                f"{rid} should still re-export the alma9 instance; if it "
                "diverged intentionally, update _DIVERGENT"
            )
```

## Snapshot regen plan

Run `pytest tests/golden/ --snapshot-update` and inspect each diff.
Expected changes ONLY:

1. **All alma9 fixture snapshots** (and `test_alma8_minimal.ambr`):
   - `Tailored XCCDF rules: 9 → 5` (or wherever the count lands — fewer crypto + zero dod entries)
   - The Tailored XCCDF table loses entries for the 3 crypto IDs + the dod ID; faillock entry renames from `_even_deny_root` → `_deny_root`.
   - The `crypto_policy` exception details `Disabled XCCDF rules:` list shrinks from 5 to 2.
   - The `dod_root_ca` exception details no longer lists any `Disabled XCCDF rules:` (empty list).
   - The `faillock_safety` exception details rename the one rule entry.

2. **`test_alma8_minimal.ambr` additionally**:
   - `crypto_policy` exception details list shows 4 IDs (alma8's divergent set) instead of inheriting alma9's 2.
   - The Tailored XCCDF table gains 2 entries (the alma8-specific cipher disables).

3. **No ubuntu_minimal change** (ubuntu's own IDs are unaffected).

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Cleanup might surprise an operator who reviewed `exceptions.md` and expected specific IDs to be there | This is exactly what the audit-story PR is for — accuracy over historical reference. Spec calls it out. |
| Extracting `_emit_post` from alma9/crypto_policy as a module-level helper might break the alma9 test for that rule | The refactor is mechanical (move body of `emit_post` method into a function, keep method as a 1-line caller). All existing alma9 crypto_policy tests should pass unchanged. Verify via local run. |
| `test_registry_alma8_re_exports_same_rule_instances_as_alma9` is a load-bearing pin from PR #124. Changing its semantics means the test no longer guarantees ALL alma8 rules re-export — it's now "all except DIVERGENT". | Documented. The `_DIVERGENT` set grows when more rules need divergent implementations (audit-story phase + future drift events). |
| Snapshot diff is large (many alma9 fixtures change) | All changes are predictable (per the per-rule deltas above). Inspect diffs at regen time; reject any unexpected lines. |
| Future SSG bump could re-introduce drift | Phase 1's `scripts/audit_story/extract_ssg_rule_ids.py` makes re-running the diff cheap. On a bump, re-extract, re-audit, fix any new drift. |

## CI parity

```bash
ruff check src tests scripts \
  && ruff format --check src tests scripts \
  && mypy \
  && pytest -q
```

Expected test count: roughly unchanged (a few existing tests change assertions; a few new ones added; rough net +5).

## Out of scope (PR B only)

- New SSG IDs that don't have an alma9 counterpart but could be mooted by ks-gen rules (would expand scope).
- Datastream version bumping (out of scope until SSG ships a new release we care about).
- Ubuntu2404 implementations (PR A already wired those).
- Schema changes to `TailoringOp` or `ExceptionEntry`.
- Refactor to make `_DIVERGENT` set self-discovering — manual maintenance is acceptable for now.

## After PR B

**#127 is complete.** Subsequent work would be SSG-version-bump maintenance (re-run phase 1 extractor, sweep again) or new ks-gen rules added under the same audit-story scaffolding.
