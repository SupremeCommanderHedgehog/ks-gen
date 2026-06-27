# alma8 phase 2 — rule re-exports

**Parent:** #121 (AlmaLinux 8 support tracking issue).
**Previous phase:** alma8 phase 1 (schema + dispatch) shipped in v0.25.0.

## Goal

Populate `src/ks_gen/rules/alma8/` with siblings for all 15 alma9 rules. Each alma8 rule file is a **re-export** of the alma9 implementation:

```python
"""alma8 <rule_name> — re-exports the alma9 implementation."""
from __future__ import annotations
from ks_gen.rules.alma9.<rule_name> import RULE
__all__ = ["RULE"]
```

After this phase:
- `load_rules("alma8")` returns the same 15 `RULE` objects as `load_rules("alma9")` — same Python object identity per rule.
- An alma8 bundle has the same Applied-rules count + listing as an alma9 bundle from the same `host.yaml` (modulo distro discriminator).
- The `tests/golden/alma8-minimal.host.yaml` golden snapshot regenerates from `Applied rules: 0` to whatever count of rules has `applies(cfg)=True` on a minimal alma8 cfg (expected ~13: everything except `data_disks_preserve` and `container_host`, which need explicit cfg).

## Why re-exports

**Forward-compatible**: when a rule needs to actually diverge between alma9 and alma8 (the most likely candidate is `crypto_policy` for the audit-story PR), its alma8 file gets a real implementation instead of the re-export. The transition is a one-file edit; the registry discovery doesn't change.

**Minimal-code**: re-export files are 5-line Python modules. Reviewing 15 of them is reading the same pattern 15 times — easy to spot-check that the import path is correct, the docstring covers any per-rule AL8 ↔ AL9 considerations, and the `__all__` declaration is in place.

**Same Python object identity**: since `from ks_gen.rules.alma9.foo import RULE` imports the *exact same `RULE` instance* that the alma9 registry walk discovers, both registries return the same singleton. If a future test asserts `RULE` identity across distros, it still holds. If a future audit-story PR wires up `emit_tailoring` against per-distro SSG rule IDs by inspecting `cfg.distro`, the same RULE object handles both.

**Rejected alternative**: copy-paste the alma9 rule body into each alma8 file. Doubles the LOC, doubles the per-rule test surface, and makes "fix this bug in both distros" a two-file edit. The re-export keeps the rules in lockstep until they actually need to diverge.

## Per-rule re-exports

Each file's docstring captures the alma9 → alma8 rationale (verbatim portability + any audit-story coupling notes):

| Rule | alma9 → alma8 rationale (short) |
|---|---|
| `admin_user_and_keys` | useradd / sudoers.d / SELinux semantics universal across RHEL family |
| `auditd_actions` | /etc/audit/auditd.conf field names + auditd base-install presence universal |
| `banner_text` | /etc/issue + sshd Banner directive universal |
| `container_host` | podman/crun/containers-common available in AL8 AppStream; storage.conf format unchanged |
| `crypto_policy` | `update-crypto-policies` shipped in RHEL 8.0 — same operator-visible effect on AL8 and AL9 (openssl 1.1.1 vs 3.0 difference is below the rule layer) |
| `data_disks_preserve` | /etc/fstab + mkdir + mount + restorecon universal |
| `dod_root_ca` | scaffolding-only; meaningful work is deferred to audit-story PR (same as alma9) |
| `faillock_safety` | /etc/security/faillock.conf shipped in RHEL 8.0; pam_faillock universal |
| `kernel_module_blacklist` | /etc/modprobe.d/ install-trick universal; default module names are AL-kernel-safe |
| `package_purge` | `dnf -y remove` identical syntax |
| `ssh_config_apply` | /etc/ssh/sshd_config.d/ drop-in support via RHEL 8.2+ OpenSSH backport |
| `ssh_keep_open` | firewalld + semanage port syntax unchanged |
| `time_servers` | chrony + /etc/chrony.conf format universal |
| `unattended_updates` | dnf-automatic timer + conf format universal |
| `usbguard` | scaffolding-only (same as alma9); EPEL-shipped on both releases |

**No per-rule code differences from alma9.** Any future divergence is a future PR (e.g., the audit-story PR that wires `emit_tailoring` against per-distro SSG rule IDs).

## Files touched

- **Create (15):** `src/ks_gen/rules/alma8/<rule_name>.py` — one per alma9 rule.
- **Modify:** `tests/test_registry.py` — replace `test_registry_alma8_returns_empty_for_phase_1` with a registry parity test asserting alma8 rule IDs are a superset of (or equal to) alma9 rule IDs. Also add a phase-2 marker test that `load_rules("alma8")` returns ≥15 rules.
- **Modify:** `tests/golden/__snapshots__/test_alma8_minimal.ambr` — snapshot regen. Applied rules count and listing populate; the kickstart's `%post` section gains rule contributions where rules' `emit_post(cfg)` is non-empty on the minimal cfg.

## Tests

### Registry-level

1. **Replace** `test_registry_alma8_returns_empty_for_phase_1` (which was correct for phase 1 but wrong now) with `test_registry_alma8_returns_same_rule_ids_as_alma9` — asserts `set(r.id for r in load_rules("alma8")) == set(r.id for r in load_rules("alma9"))`.
2. **Add** `test_registry_alma8_returns_same_rule_instances_as_alma9` — asserts `load_rules("alma8")[i] is load_rules("alma9")[i]` (after sorting by id) — pins the re-export semantics (same Python object identity, not just same id).
3. **Keep** `test_registry_alma8_package_exists` (unchanged from phase 1).

### Snapshot-level

4. `tests/golden/__snapshots__/test_alma8_minimal.ambr` regenerates. Expected diff:
   - `Applied rules: 0` → `Applied rules: ~13` (the exact count depends on which rules' `applies(cfg)` returns True on the minimal cfg — observed at regen time and validated by inspection).
   - The Applied-rules listing populates alphabetically.
   - The `%post` section in ks.cfg gains rule contributions from rules whose `emit_post(cfg)` is non-empty.
   - Tailoring + exceptions sections — no change expected (`emit_tailoring` and `exception_entry` are deferred to audit-story PR for almost every rule; only a few alma9 rules emit ops today).

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Re-export discovers the alma9 module but the registry's `getattr(module, "RULE", None)` doesn't see it because `RULE` is shadowed somewhere | Empirically verified: phase 2 validation (single-rule re-export) showed `load_rules("alma8")` correctly returns the imported RULE. The `from X import RULE` statement places RULE in the alma8 module's namespace; pkgutil + getattr find it. |
| `__all__ = ["RULE"]` is technically optional but documents intent | Including it makes the re-export's purpose self-evident to readers and to any future tooling (e.g., dead-code analysis). |
| Multiple alma8 fixtures (beyond `alma8-minimal`) need snapshot regen | Currently there is only one alma8 golden fixture. If more land, this PR's scope expands. None in main today. |
| `crypto_policy` (or another rule) silently does the wrong thing on a real AL8 install | The unit tests don't exercise install-time behavior; that's what the install-regression harness is for. Recommended (per CLAUDE.md): run the AL8 variant of the install-regression harness once phase 3 ISO support lands. Phase 2 is not a high-risk install-pipeline change — the kickstart's content is unchanged from alma9 byte-for-byte for the rule overrides. |
| A rule's alma9 implementation imports something that's RHEL-9-only at import time | None observed: the alma9 rule modules import from `ks_gen.rules._meta`, `ks_gen.rules._types`, `ks_gen.config`, `importlib.resources.files` — all distro-neutral. The alma9 helper script asset (`create-rootless-user.sh`) is loaded at import time but its **content** is shell that runs on the target — it doesn't need to import anything Python-level. The same asset works on AL8 since semanage / restorecon / loginctl all exist there. |

## CI parity check before push

```bash
ruff check src tests \
  && ruff format --check src tests \
  && mypy \
  && pytest -q
```

Expected new test count: `928 + 1-2 = ~930` (the parity test pair replaces the empty-marker test). The phase-1 empty-marker test is removed, so net +1 (rule-parity) + the snapshot regen.

## Out of scope (phase 2 only)

- Any rule's alma8 implementation **diverging** from alma9 (e.g., crypto_policy openssl 1.1.1 ↔ 3.0 specifics). When the audit-story PR or a per-rule bug requires divergence, the affected rule's alma8 file changes from a re-export to a real implementation; that's a separate PR.
- `ks-gen iso` for alma8 — phase 3.
- `ks-gen verify` against an alma8 host — phase 4.
- Audit-story PR for alma8 SSG rule IDs — coordinated with the ubuntu2404 audit-story PR.
