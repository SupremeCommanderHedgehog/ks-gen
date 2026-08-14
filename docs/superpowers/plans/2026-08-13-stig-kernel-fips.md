# STIG Kernel FIPS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `crypto.policy: STIG` put the AlmaLinux kernel in FIPS mode, so the three (AL10) / four (AL9) stig-selected FIPS rules pass instead of failing forever, and declare the one rule Ubuntu structurally cannot pass.

**Architecture:** `overrides.fips_mode` becomes a derived value (`HostConfig.kernel_fips`) instead of an input. The alma `crypto_policy` rule's shared `_emit_post` runs `fips-mode-setup --enable` plus `dracut -f --regenerate-all` before its existing `update-crypto-policies` call. Ubuntu's `crypto_policy` splits its disable set so `is_fips_mode_enabled` is disabled and declared under every policy.

**Tech Stack:** Python 3.14, pydantic v2 (frozen `StrictModel`), Jinja2 templates, pytest + syrupy snapshots, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-08-13-stig-kernel-fips-design.md`

---

## Background an engineer needs before starting

- **`ks-gen` generates AlmaLinux/Ubuntu kickstart bundles.** A `host.yaml` is
  loaded into a `HostConfig`, then "rules" under `src/ks_gen/rules/<distro>/`
  each contribute shell to `%post`, packages to `%packages`, and XCCDF
  tailoring ops.
- **XCCDF/oscap vocabulary.** The install runs `oscap xccdf eval --remediate`
  against a DISA STIG profile. A *tailoring* file can `disable` a rule
  (oscap then reports it `notselected`) or `set_value` an XCCDF variable.
  Every disabled rule must be declared in `exceptions.md` — enforced by
  `tests/test_invariants.py:77`.
- **`crypto.policy`** has three values: `STIG`, `MODERN` (default), `FUTURE`.
  It selects a system crypto-policy via `update-crypto-policies --set`.
- **The bug:** setting the crypto *policy* to FIPS does not put the *kernel*
  in FIPS mode. `/proc/sys/crypto/fips_enabled` stays `0`, so rules that read
  it fail forever with nothing in `exceptions.md` explaining why.
- **Distro rule modules share code by import**, not inheritance:
  `alma8/crypto_policy.py` and `alma10/crypto_policy.py` import `_emit_post`,
  `_emit_tailoring`, `_exception_entry` and `_FIPS_ONLY_COMMON` from
  `alma9/crypto_policy.py`. Editing the alma9 helper changes all three distros.
- **`StrictModel` is frozen and forbids extra keys.** Deleting a config field
  breaks every `host.yaml` that names it, which is why `overrides.fips_mode`
  is retained as a checked assertion rather than removed.

**Run the full CI chain before any commit that touches Python:**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

`ruff check` alone misses formatting drift; `ruff format --check` is a separate
gate that has bounced a PR before.

---

## File Structure

| File | Change | Responsibility after this plan |
|---|---|---|
| `src/ks_gen/config.py` | Modify | `Overrides.fips_mode: bool \| None`; new `_KERNEL_FIPS_DISTROS`; new `HostConfig.kernel_fips` property; `_crypto_fips_mutex` replaced by `_fips_mode_agrees_with_policy` |
| `src/ks_gen/loader.py` | Modify (~86) | Map the three fips_mode conflicts to `ExitCode.RULE_CONFLICT` |
| `src/ks_gen/templates/ks.cfg.j2` | Modify (31, 33) | Bootloader `fips=1` driven by `cfg.kernel_fips` |
| `src/ks_gen/rules/alma9/crypto_policy.py` | Modify (`_emit_post`) | Shared alma `%post`: enable kernel FIPS, then set the policy |
| `src/ks_gen/rules/alma8/crypto_policy.py` | Modify (`emit_packages`) | Add `dracut-fips` when the host reaches kernel FIPS |
| `src/ks_gen/rules/ubuntu2404/crypto_policy.py` | Modify | Always-disable + declare `is_fips_mode_enabled` |
| `tests/test_config_schema.py` | Modify | Combinatorial `kernel_fips` truth table + rejection cases |
| `tests/test_fips_dependent_rules.py` | Modify | New STIG-side invariant replacing `test_stig_policy_disables_no_fips_rule` |
| `tests/golden/ubuntu-stig.host.yaml` | Create | Golden fixture locking the new Ubuntu STIG exception |
| `tests/golden/test_ubuntu_stig.py` | Create | Snapshot test for the above |
| `tests/install-regression/smoke-check.sh` | Modify | FIPS-branch assertions on the installed host |
| `MANUAL.md` | Modify | Correct five places that describe behaviour that did not exist |

---

## Task 1: `kernel_fips` derived property and config validation

**Files:**
- Modify: `src/ks_gen/config.py:728-729` (`Overrides.fips_mode`), `:764` area (new constant), `:781-789` (`_crypto_fips_mutex`)
- Test: `tests/test_config_schema.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config_schema.py`. Note `_fips_cfg` re-validates from a
dump because `distro` drives a `mode="before"` validator that derives
`meta.scap_content` — `model_copy` would skip it.

```python
_FIPS_DISTROS = ["alma8", "alma9", "alma10"]
_ALL_DISTROS = [*_FIPS_DISTROS, "ubuntu2404"]


def _fips_cfg(minimal_cfg, distro, policy, fips_mode=None):
    base = minimal_cfg.model_dump(exclude={"meta", "install"})
    overrides = dict(base.get("overrides") or {})
    overrides["fips_mode"] = fips_mode
    return HostConfig.model_validate(
        {**base, "distro": distro, "crypto": {"policy": policy.value}, "overrides": overrides}
    )


@pytest.mark.parametrize("distro", _ALL_DISTROS)
@pytest.mark.parametrize("policy", list(CryptoPolicy))
def test_kernel_fips_truth_table(minimal_cfg, distro, policy):
    """kernel_fips is exactly 'STIG on the RHEL family' (#84)."""
    cfg = _fips_cfg(minimal_cfg, distro, policy)
    expected = policy is CryptoPolicy.STIG and distro in set(_FIPS_DISTROS)
    assert cfg.kernel_fips is expected


@pytest.mark.parametrize("distro", _ALL_DISTROS)
@pytest.mark.parametrize("policy", list(CryptoPolicy))
def test_declared_fips_mode_matching_the_derived_value_is_accepted(
    minimal_cfg, distro, policy
):
    """An explicit fips_mode that agrees with the policy must still load."""
    derived = _fips_cfg(minimal_cfg, distro, policy).kernel_fips
    cfg = _fips_cfg(minimal_cfg, distro, policy, fips_mode=derived)
    assert cfg.kernel_fips is derived


@pytest.mark.parametrize("distro", _FIPS_DISTROS)
def test_stig_cannot_opt_out_of_kernel_fips(minimal_cfg, distro):
    with pytest.raises(ValidationError, match="cannot opt out"):
        _fips_cfg(minimal_cfg, distro, CryptoPolicy.STIG, fips_mode=False)


@pytest.mark.parametrize("distro", _ALL_DISTROS)
@pytest.mark.parametrize("policy", [CryptoPolicy.MODERN, CryptoPolicy.FUTURE])
def test_fips_mode_true_rejected_off_stig(minimal_cfg, distro, policy):
    with pytest.raises(ValidationError, match="MODERN/FUTURE"):
        _fips_cfg(minimal_cfg, distro, policy, fips_mode=True)


def test_fips_mode_true_rejected_on_ubuntu_stig(minimal_cfg):
    """Kernel FIPS on Ubuntu needs a Pro entitlement ks-gen does not manage."""
    with pytest.raises(ValidationError, match="fips-updates"):
        _fips_cfg(minimal_cfg, "ubuntu2404", CryptoPolicy.STIG, fips_mode=True)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
pytest tests/test_config_schema.py -k "kernel_fips or fips_mode" -q
```

Expected: FAIL — `AttributeError: 'HostConfig' object has no attribute 'kernel_fips'`.

- [ ] **Step 3: Add the distro constant**

In `src/ks_gen/config.py`, directly above `_DEFAULT_SCAP_CONTENT_BY_DISTRO`:

```python
# Distros where ks-gen can put the kernel in FIPS mode. Ubuntu needs an Ubuntu
# Pro `fips-updates` entitlement ks-gen does not manage (#84).
_KERNEL_FIPS_DISTROS = frozenset({"alma8", "alma9", "alma10"})
```

- [ ] **Step 4: Make `fips_mode` tri-state**

Replace `fips_mode: bool = False` in `class Overrides` with:

```python
    # None = derive from crypto.policy (HostConfig.kernel_fips). Kept as an
    # explicit assertion rather than deleted: StrictModel forbids extra keys,
    # so removing it would break every host.yaml naming it (#84).
    fips_mode: bool | None = None
```

- [ ] **Step 5: Add the derived property**

In `class HostConfig`, next to the other model validators:

```python
    @property
    def kernel_fips(self) -> bool:
        """Whether the installed host boots with fips=1 (#84).

        Derived, not configured: STIG means kernel FIPS on the RHEL family,
        MODERN/FUTURE never do, and Ubuntu cannot without a Pro entitlement.
        """
        return self.crypto.policy is CryptoPolicy.STIG and self.distro in _KERNEL_FIPS_DISTROS
```

- [ ] **Step 6: Replace the mutex validator**

Replace the whole `_crypto_fips_mutex` method (`config.py:781-789`) with:

```python
    @model_validator(mode="after")
    def _fips_mode_agrees_with_policy(self) -> HostConfig:
        declared = self.overrides.fips_mode
        if declared is None or declared == self.kernel_fips:
            return self
        if declared and self.crypto.policy in (CryptoPolicy.MODERN, CryptoPolicy.FUTURE):
            raise ValueError(
                "crypto.policy=MODERN/FUTURE conflicts with overrides.fips_mode=true: "
                "FIPS kernel mode blocks Curve25519/Ed25519 at the kernel layer."
            )
        if declared:
            raise ValueError(
                f"overrides.fips_mode=true is not supported for distro={self.distro}: "
                "kernel FIPS needs an Ubuntu Pro fips-updates entitlement ks-gen does "
                "not manage, so crypto.policy=STIG configures algorithms only."
            )
        raise ValueError(
            "crypto.policy=STIG enables FIPS kernel mode and overrides.fips_mode=false "
            "cannot opt out. Choose crypto.policy=MODERN or FUTURE, or drop "
            "overrides.fips_mode to accept the derived value."
        )
```

Every branch mentions both `crypto.policy` and `fips_mode` — Task 2's loader
mapping keys off that.

- [ ] **Step 7: Run the tests to verify they pass**

```bash
pytest tests/test_config_schema.py -k "kernel_fips or fips_mode" -q
```

Expected: PASS (24 truth-table cases + 12 agreement cases + the rejections).

- [ ] **Step 8: Run the full CI chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: the golden snapshot tests may still pass here — `stig-strict.host.yaml`
sets `fips_mode: true` on alma9 STIG, which agrees with the derived value. If
anything else fails, fix before committing.

- [ ] **Step 9: Commit**

```bash
git add src/ks_gen/config.py tests/test_config_schema.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
  commit -S -m "feat(config): derive kernel FIPS mode from crypto.policy (#84)"
```

---

## Task 2: Loader exit code for the new conflicts

**Files:**
- Modify: `src/ks_gen/loader.py:82-89`
- Test: `tests/test_loader.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_loader.py`:

```python
def test_stig_with_fips_mode_false_is_a_rule_conflict(tmp_path):
    """#84: opting out of kernel FIPS under STIG is a conflict, not bad syntax."""
    p = tmp_path / "host.yaml"
    p.write_text(
        "system: {hostname: h.example.com}\n"
        "crypto: {policy: STIG}\n"
        "overrides: {fips_mode: false}\n"
        "user:\n"
        "  admin:\n"
        "    name: ops\n"
        "    authorized_keys: [\"ssh-rsa AAAA a@b\"]\n"
        "    sudo: nopasswd_yes\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as e:
        load_host_config(p, sets=[])
    assert e.value.code == ExitCode.RULE_CONFLICT
```

Add any missing imports (`pytest`, `ConfigError`, `ExitCode`, `load_host_config`)
by matching what the file already imports.

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/test_loader.py -k stig_with_fips_mode_false -q
```

Expected: FAIL — code is `CONFIG_INVALID` (2 in the enum), not `RULE_CONFLICT`.

- [ ] **Step 3: Widen the mapping**

In `src/ks_gen/loader.py`, replace the condition:

```python
        code = (
            ExitCode.RULE_CONFLICT
            if ("crypto.policy" in msg and "fips_mode" in msg)
            else ExitCode.CONFIG_INVALID
        )
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
pytest tests/test_loader.py -q
```

Expected: PASS, including the pre-existing MODERN conflict test.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/loader.py tests/test_loader.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
  commit -S -m "fix(loader): map every fips_mode/crypto.policy conflict to RULE_CONFLICT (#84)"
```

---

## Task 3: Bootloader reads the derived value

**Files:**
- Modify: `src/ks_gen/templates/ks.cfg.j2:31,33`
- Test: `tests/test_bootloader.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_bootloader.py`. Add `HostConfig` and `build_bundle` to
that file's imports if they are not already there — check the top of the file
first and match its existing style.

```python
def test_stig_puts_fips_1_on_the_bootloader_without_an_explicit_override(minimal_cfg):
    """#84: STIG alone implies fips=1; no overrides.fips_mode needed."""
    base = minimal_cfg.model_dump(exclude={"meta", "install"})
    cfg = HostConfig.model_validate({**base, "crypto": {"policy": "STIG"}})
    line = next(ln for ln in build_bundle(cfg).ks_cfg.splitlines() if ln.startswith("bootloader"))
    assert "fips=1" in line


@pytest.mark.parametrize("policy", ["MODERN", "FUTURE"])
def test_non_stig_bootloader_has_no_fips_arg(minimal_cfg, policy):
    base = minimal_cfg.model_dump(exclude={"meta", "install"})
    cfg = HostConfig.model_validate({**base, "crypto": {"policy": policy}})
    line = next(ln for ln in build_bundle(cfg).ks_cfg.splitlines() if ln.startswith("bootloader"))
    assert "fips=1" not in line
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/test_bootloader.py -k fips -q
```

Expected: FAIL on the first test — the bootloader line has no `fips=1`, because
the template still reads `cfg.overrides.fips_mode`, which is now `None`.

- [ ] **Step 3: Point the template at the derived value**

In `src/ks_gen/templates/ks.cfg.j2`, on **both** line 31 and line 33, replace
`{% if cfg.overrides.fips_mode %}` with `{% if cfg.kernel_fips %}`. Leave the
rest of each line untouched.

- [ ] **Step 4: Run the test to verify it passes**

```bash
pytest tests/test_bootloader.py -k fips -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ks_gen/templates/ks.cfg.j2 tests/test_bootloader.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
  commit -S -m "feat(kickstart): drive the fips=1 boot arg from kernel_fips (#84)"
```

---

## Task 4: Enable kernel FIPS in the alma `%post`

**Files:**
- Modify: `src/ks_gen/rules/alma9/crypto_policy.py` (`_emit_post`, ~line 116-170)
- Test: `tests/rules/` — create `tests/rules/test_crypto_policy_fips.py`

Check first whether `tests/rules/` already has a crypto_policy test file
(`ls tests/rules/`); if one exists, append there instead of creating a new file.

- [ ] **Step 1: Write the failing test**

```python
"""#84: STIG must put the kernel in FIPS mode, not just the crypto policy."""

from __future__ import annotations

import pytest

from ks_gen.config import HostConfig
from ks_gen.registry import load_rules

_ALMA = ["alma8", "alma9", "alma10"]


def _post(minimal_cfg, distro: str, policy: str) -> str:
    base = minimal_cfg.model_dump(exclude={"meta", "install"})
    cfg = HostConfig.model_validate({**base, "distro": distro, "crypto": {"policy": policy}})
    rule = next(r for r in load_rules(distro) if r.id == "crypto_policy")
    return rule.emit_post(cfg)


@pytest.mark.parametrize("distro", _ALMA)
def test_stig_enables_kernel_fips(minimal_cfg, distro):
    body = _post(minimal_cfg, distro, "STIG")
    assert "fips-mode-setup --enable" in body
    assert "dracut -f --regenerate-all" in body


@pytest.mark.parametrize("distro", _ALMA)
def test_fips_enablement_precedes_the_policy_set(minimal_cfg, distro):
    """fips-mode-setup resets the policy to plain FIPS, so it must run first (#66)."""
    body = _post(minimal_cfg, distro, "STIG")
    assert body.index("fips-mode-setup --enable") < body.index("update-crypto-policies --set")


@pytest.mark.parametrize("distro", _ALMA)
def test_fips_enablement_failure_aborts_the_install(minimal_cfg, distro):
    """A silent fallback would re-create #84: a host claiming FIPS without it."""
    body = _post(minimal_cfg, distro, "STIG")
    assert "fips-mode-setup --enable || true" not in body
    assert "exit 1" in body


@pytest.mark.parametrize("distro", _ALMA)
@pytest.mark.parametrize("policy", ["MODERN", "FUTURE"])
def test_non_stig_never_touches_fips(minimal_cfg, distro, policy):
    body = _post(minimal_cfg, distro, policy)
    assert "fips-mode-setup" not in body
    assert "dracut" not in body


@pytest.mark.parametrize("distro", _ALMA)
@pytest.mark.parametrize("policy", ["STIG", "MODERN", "FUTURE"])
def test_policy_header_line_stays_first(minimal_cfg, distro, policy):
    """run.sh parses this line to learn the expected policy — keep it line 1."""
    body = _post(minimal_cfg, distro, policy)
    assert body.splitlines()[0].startswith("# Apply system-wide crypto policy:")
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/rules/test_crypto_policy_fips.py -q
```

Expected: FAIL — `fips-mode-setup --enable` is not in the emitted body.

- [ ] **Step 3: Emit the FIPS block**

In `src/ks_gen/rules/alma9/crypto_policy.py`, inside `_emit_post`, immediately
after the `lines = [f"# Apply system-wide crypto policy: {policy} ({target})"]`
assignment and **before** the `base, _, submodule = target.partition(":")` line:

```python
    if policy == "STIG":
        # fips-mode-setup resets the policy to plain FIPS, so it must run
        # before the update-crypto-policies call below (#66). Its own
        # `dracut -f` targets `uname -r` — the *installer's* kernel inside
        # anaconda's chroot — so regenerate every installed initramfs after.
        # No `|| true`: a host that claims FIPS without being in FIPS is #84.
        lines += [
            "# Kernel FIPS mode: dracut module + fips=1; takes effect at first boot",
            "fips-mode-setup --enable || {",
            "  echo 'ks-gen: fips-mode-setup --enable failed; refusing to ship a host"
            " that claims FIPS but is not in FIPS mode (#84)' >&2",
            "  exit 1",
            "}",
            "dracut -f --regenerate-all",
        ]
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
pytest tests/rules/test_crypto_policy_fips.py -q
```

Expected: PASS (all parametrizations across alma8/9/10).

- [ ] **Step 5: Confirm the emitted shell is valid**

```bash
pytest tests/test_lint.py -q
```

Expected: PASS. If a shell linter flags the multi-line `|| { ... }`, keep the
structure and fix quoting only — the abort behaviour is required.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/rules/alma9/crypto_policy.py tests/rules/test_crypto_policy_fips.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
  commit -S -m "feat(crypto): enable kernel FIPS mode under crypto.policy=STIG (#84)"
```

---

## Task 5: `dracut-fips` package on AlmaLinux 8

RHEL 9 folded the dracut FIPS module into `dracut` itself; RHEL 8 keeps it in a
separate `dracut-fips` package that `fips-mode-setup --enable` needs.

**Files:**
- Modify: `src/ks_gen/rules/alma8/crypto_policy.py:74-75` (`emit_packages`)
- Test: `tests/rules/test_crypto_policy_fips.py`

- [ ] **Step 1: Verify the premise before writing code**

```bash
PRIMARY=$(curl -s https://repo.almalinux.org/almalinux/8/BaseOS/x86_64/os/repodata/repomd.xml \
  | grep -o 'repodata/[a-f0-9]*-primary\.xml\.gz' | head -1)
curl -s "https://repo.almalinux.org/almalinux/8/BaseOS/x86_64/os/$PRIMARY" \
  | gunzip | grep -o '<name>dracut-fips</name>' | head -1
```

Expected: `<name>dracut-fips</name>`.

If there is no network, check the DVD ISO already in the repo root instead —
that is the medium an AL8 install actually reads from:

```bash
osirrox -indev AlmaLinux-8.10-x86_64-dvd.iso -find /AppStream/Packages -name 'dracut-fips*'
```

Expected: at least one `dracut-fips-*.rpm` path.

**If the package exists in neither, stop and skip this entire task** — it would add an uninstallable package name to `%packages` and break
every AL8 STIG install. Record the finding in the PR body and move to Task 6.

- [ ] **Step 2: Write the failing test**

Append to `tests/rules/test_crypto_policy_fips.py`:

```python
def _packages(minimal_cfg, distro: str, policy: str) -> list[str]:
    base = minimal_cfg.model_dump(exclude={"meta", "install"})
    cfg = HostConfig.model_validate({**base, "distro": distro, "crypto": {"policy": policy}})
    rule = next(r for r in load_rules(distro) if r.id == "crypto_policy")
    return rule.emit_packages(cfg)


def test_alma8_stig_pulls_dracut_fips(minimal_cfg):
    """RHEL 8 keeps the dracut FIPS module in its own package (#84)."""
    assert "dracut-fips" in _packages(minimal_cfg, "alma8", "STIG")


@pytest.mark.parametrize("policy", ["MODERN", "FUTURE"])
def test_alma8_non_stig_does_not_pull_dracut_fips(minimal_cfg, policy):
    assert _packages(minimal_cfg, "alma8", policy) == []


@pytest.mark.parametrize("distro", ["alma9", "alma10"])
def test_alma9_and_10_ship_the_fips_module_inside_dracut(minimal_cfg, distro):
    assert _packages(minimal_cfg, distro, "STIG") == []
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
pytest tests/rules/test_crypto_policy_fips.py -k dracut -q
```

Expected: FAIL — `emit_packages` returns `[]` for alma8 STIG.

- [ ] **Step 4: Implement**

In `src/ks_gen/rules/alma8/crypto_policy.py`, replace the body of
`emit_packages`:

```python
    def emit_packages(self, cfg: HostConfig) -> list[str]:
        # RHEL 8 keeps the dracut FIPS module in its own package and
        # fips-mode-setup --enable needs it; RHEL 9+ ships it inside dracut (#84).
        return ["dracut-fips"] if cfg.kernel_fips else []
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
pytest tests/rules/test_crypto_policy_fips.py -k dracut -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ks_gen/rules/alma8/crypto_policy.py tests/rules/test_crypto_policy_fips.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
  commit -S -m "feat(crypto): install dracut-fips on AlmaLinux 8 STIG hosts (#84)"
```

---

## Task 6: Declare the rule Ubuntu cannot pass

`is_fips_mode_enabled` reads `/proc/sys/crypto/fips_enabled`. No Ubuntu policy
can make it pass without an Ubuntu Pro `fips-updates` entitlement, so today it
fails on every Ubuntu STIG host with no `exceptions.md` line — the same defect
as #84 on Alma, and oscap keeps remediating toward a FIPS it cannot reach.

**Files:**
- Modify: `src/ks_gen/rules/ubuntu2404/crypto_policy.py:60-68` (rule lists) and the `_Rule` methods
- Test: `tests/rules/test_crypto_policy_fips.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/rules/test_crypto_policy_fips.py`:

```python
_IS_FIPS = "xccdf_org.ssgproject.content_rule_is_fips_mode_enabled"


def _rule(distro: str):
    return next(r for r in load_rules(distro) if r.id == "crypto_policy")


def _ubuntu_cfg(minimal_cfg, policy: str) -> HostConfig:
    base = minimal_cfg.model_dump(exclude={"meta", "install"})
    return HostConfig.model_validate(
        {**base, "distro": "ubuntu2404", "crypto": {"policy": policy}}
    )


@pytest.mark.parametrize("policy", ["STIG", "MODERN", "FUTURE"])
def test_ubuntu_always_disables_is_fips_mode_enabled(minimal_cfg, policy):
    cfg = _ubuntu_cfg(minimal_cfg, policy)
    disabled = {op.rule_id for op in _rule("ubuntu2404").emit_tailoring(cfg) if op.action == "disable"}
    assert _IS_FIPS in disabled


@pytest.mark.parametrize("policy", ["STIG", "MODERN", "FUTURE"])
def test_ubuntu_declares_every_rule_it_disables(minimal_cfg, policy):
    cfg = _ubuntu_cfg(minimal_cfg, policy)
    rule = _rule("ubuntu2404")
    disabled = {op.rule_id for op in rule.emit_tailoring(cfg) if op.action == "disable"}
    entry = rule.exception_entry(cfg)
    assert entry is not None
    assert disabled <= set(entry.stig_rules_disabled)


def test_ubuntu_stig_exception_names_the_pro_entitlement(minimal_cfg):
    """The reason must say why it cannot pass, not just that it is disabled."""
    entry = _rule("ubuntu2404").exception_entry(_ubuntu_cfg(minimal_cfg, "STIG"))
    assert entry is not None
    assert "fips-updates" in entry.reason


def test_ubuntu_stig_keeps_the_sshd_algorithm_rules_enabled(minimal_cfg):
    """STIG writes exactly those algorithm lists, so those rules must evaluate."""
    cfg = _ubuntu_cfg(minimal_cfg, "STIG")
    disabled = {op.rule_id for op in _rule("ubuntu2404").emit_tailoring(cfg) if op.action == "disable"}
    assert disabled == {_IS_FIPS}
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/rules/test_crypto_policy_fips.py -k ubuntu -q
```

Expected: FAIL — under STIG `emit_tailoring` returns `[]` and `exception_entry`
returns `None`.

- [ ] **Step 3: Split the disable set**

In `src/ks_gen/rules/ubuntu2404/crypto_policy.py`, replace the
`_TAILORED_WHEN_NOT_STIG` block (lines 60-68, keeping the existing `_PREFIX`
line and the comment above it) with:

```python
_PREFIX = "xccdf_org.ssgproject.content_rule_"

# No Ubuntu policy can pass this: kernel FIPS needs an Ubuntu Pro fips-updates
# entitlement ks-gen does not manage. Left enabled it fails on every host with
# nothing in exceptions.md, and oscap remediates toward a FIPS it cannot
# reach (#84).
_ALWAYS_DISABLED = [f"{_PREFIX}is_fips_mode_enabled"]

_TAILORED_WHEN_NOT_STIG = [
    f"{_PREFIX}sshd_use_approved_ciphers_ordered_stig",
    f"{_PREFIX}sshd_use_approved_kex_ordered_stig",
    f"{_PREFIX}sshd_use_approved_macs_ordered_stig",
]


def _disabled_for(cfg: HostConfig) -> list[str]:
    if cfg.crypto.policy.value == "STIG":
        return list(_ALWAYS_DISABLED)
    return [*_ALWAYS_DISABLED, *_TAILORED_WHEN_NOT_STIG]
```

The non-STIG order is unchanged from today's list (`is_fips_mode_enabled`
first), so existing Ubuntu snapshots do not move.

- [ ] **Step 4: Rewrite the two `_Rule` methods**

Replace `emit_tailoring` and `exception_entry` in that file's `_Rule`:

```python
    def emit_tailoring(self, cfg: HostConfig) -> list[TailoringOp]:
        return [TailoringOp(rule_id=r, action="disable") for r in _disabled_for(cfg)]

    def exception_entry(self, cfg: HostConfig) -> ExceptionEntry | None:
        policy = cfg.crypto.policy.value
        if policy == "STIG":
            return ExceptionEntry(
                rule_id=meta.ID,
                summary="STIG algorithms without FIPS kernel mode",
                stig_rules_disabled=list(_ALWAYS_DISABLED),
                reason=(
                    "Ubuntu 24.04 cannot enter FIPS kernel mode without an Ubuntu Pro "
                    "fips-updates entitlement, which ks-gen does not manage. "
                    "crypto.policy=STIG pins STIG-aligned algorithms across sshd, "
                    "OpenSSL and GnuTLS, but the host is not FIPS 140-3 validated."
                ),
            )
        return ExceptionEntry(
            rule_id=meta.ID,
            summary=f"{policy} crypto policy",
            stig_rules_disabled=_disabled_for(cfg),
            reason=(
                f"{policy} accepts loss of FIPS 140-3 certification "
                "in exchange for Curve25519 / Ed25519 / ChaCha20-Poly1305 support."
            ),
        )
```

Also update the dataclass field so `ks-gen rules` reports the full set:

```python
    stig_rules_affected: list[str] = field(
        default_factory=lambda: [*_ALWAYS_DISABLED, *_TAILORED_WHEN_NOT_STIG]
    )
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
pytest tests/rules/test_crypto_policy_fips.py -k ubuntu -q
```

Expected: PASS.

- [ ] **Step 6: Confirm the declared IDs are still stig-selected**

```bash
pytest tests/test_rule_ids_selected_by_stig.py tests/test_rule_ids_exist_in_datastream.py tests/test_invariants.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/ks_gen/rules/ubuntu2404/crypto_policy.py tests/rules/test_crypto_policy_fips.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
  commit -S -m "fix(crypto): declare the FIPS rule Ubuntu cannot pass under STIG (#84)"
```

---

## Task 7: STIG-side invariant guard

`tests/test_fips_dependent_rules.py` asserts that on MODERN/FUTURE hosts, every
FIPS-dependent stig-selected rule is disabled or classified (#67). It never
asserted the STIG direction — which is the hole #84 fell through. This task
closes it.

**Files:**
- Modify: `tests/test_fips_dependent_rules.py:104-118` (helpers) and `:165-169` (the STIG test)

- [ ] **Step 1: Add a `_cfg` helper and reuse it**

Replace the existing `_disabled` helper with:

```python
def _cfg(minimal_cfg, distro: str, policy: CryptoPolicy) -> HostConfig:
    """Re-validated rather than model_copy'd: `distro` drives a mode="before"
    validator that derives meta.scap_content."""
    base = minimal_cfg.model_dump(exclude={"meta", "install"})
    return HostConfig.model_validate(
        {**base, "distro": distro, "crypto": {"policy": policy.value}}
    )


def _disabled(minimal_cfg, distro: str, policy: CryptoPolicy) -> set[str]:
    """Every SSG rule the distro's rules disable under the given crypto policy."""
    cfg = _cfg(minimal_cfg, distro, policy)
    return {
        op.rule_id
        for rule in load_rules(distro)
        if rule.applies(cfg)
        for op in rule.emit_tailoring(cfg)
        if op.action == "disable"
    }


def _declared(minimal_cfg, distro: str, policy: CryptoPolicy) -> set[str]:
    """Every SSG rule named in some rule's exception entry."""
    cfg = _cfg(minimal_cfg, distro, policy)
    out: set[str] = set()
    for rule in load_rules(distro):
        if not rule.applies(cfg):
            continue
        entry = rule.exception_entry(cfg)
        if entry is not None:
            out.update(entry.stig_rules_disabled)
    return out
```

- [ ] **Step 2: Replace `test_stig_policy_disables_no_fips_rule`**

Delete that test (lines 165-169) and put this in its place:

```python
@pytest.mark.parametrize("distro", _DISTROS)
def test_stig_fips_candidates_are_reachable_or_declared(distro, minimal_cfg):
    """#84: on a STIG host, no FIPS rule may fail without an explanation.

    Where the host really reaches kernel FIPS (the RHEL family), the rules must
    stay enabled and are expected to pass — suppressing them would hide a real
    regression. Where it cannot (ubuntu2404 needs an Ubuntu Pro entitlement),
    each candidate must be disabled AND named in an exception entry, or
    classified in _PASSES_ANYWAY with a reason.
    """
    cfg = _cfg(minimal_cfg, distro, CryptoPolicy.STIG)
    candidates = _candidates(distro)
    disabled = _disabled(minimal_cfg, distro, CryptoPolicy.STIG)

    if cfg.kernel_fips:
        suppressed = candidates & disabled
        assert not suppressed, (
            f"{distro}/STIG reaches kernel FIPS, so {sorted(suppressed)} must stay "
            f"enabled and pass. Disabling them hides real regressions behind an "
            f"exception the host does not need."
        )
        return

    unexplained = candidates - disabled - _allow_listed(distro)
    assert not unexplained, (
        f"{distro}/STIG cannot reach kernel FIPS, so {sorted(unexplained)} fail on "
        f"every host with nothing in exceptions.md to explain them — the #84 defect. "
        f"Disable each one and name it in an exception entry, or classify it in "
        f"_PASSES_ANYWAY with the reason it passes anyway."
    )
    undeclared = (candidates & disabled) - _declared(minimal_cfg, distro, CryptoPolicy.STIG)
    assert not undeclared, (
        f"{distro}/STIG disables {sorted(undeclared)} without naming them in any "
        f"exception entry — exceptions.md would not mention them at all."
    )
```

- [ ] **Step 3: Run the test**

```bash
pytest tests/test_fips_dependent_rules.py -q
```

Expected: PASS for all four distros. If `alma8`/`alma9`/`alma10` fail on the
`suppressed` branch, a FIPS candidate is being disabled under STIG somewhere —
find the rule and remove that disable rather than weakening the assertion.

- [ ] **Step 4: Prove the guard actually catches #84**

Temporarily revert Task 6 by making `_disabled_for` in
`src/ks_gen/rules/ubuntu2404/crypto_policy.py` return `[]` under STIG, then:

```bash
pytest tests/test_fips_dependent_rules.py -k stig_fips_candidates -q
```

Expected: FAIL on `ubuntu2404` naming `is_fips_mode_enabled`. Restore the code
and re-run to confirm PASS. A guard that cannot fail is not a guard.

- [ ] **Step 5: Commit**

```bash
git add tests/test_fips_dependent_rules.py
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
  commit -S -m "test(crypto): assert STIG hosts have no unexplained FIPS failures (#84)"
```

---

## Task 8: Golden snapshots

**Files:**
- Create: `tests/golden/ubuntu-stig.host.yaml`, `tests/golden/test_ubuntu_stig.py`
- Regenerate: `tests/golden/__snapshots__/test_stig_strict.ambr`

- [ ] **Step 1: Add a Ubuntu STIG golden fixture**

`tests/golden/ubuntu-stig.host.yaml` — the new Ubuntu STIG exception is
user-visible output with no snapshot coverage today:

```yaml
distro: ubuntu2404
system:
  hostname: u2404-stig.example.com
user:
  admin:
    name: stigops
    authorized_keys:
      - "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABTESTKEYubuntustig ops@bastion"
    sudo: nopasswd_yes
crypto:
  policy: STIG
```

- [ ] **Step 2: Add its snapshot test**

`tests/golden/test_ubuntu_stig.py` — copy the normalizer from
`tests/golden/test_ubuntu_minimal.py` so the two files agree on what is
normalized, and assert the same bundle members that file asserts:

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


def test_ubuntu_stig(snapshot):
    yaml_path = Path(__file__).parent / "ubuntu-stig.host.yaml"
    cfg = load_host_config(yaml_path, sets=[])
    bundle = build_bundle(cfg)
    assert _normalize(bundle.tailoring_xml) == snapshot(name="tailoring.xml")
    assert _normalize(bundle.exceptions_md) == snapshot(name="exceptions.md")
```

If `test_ubuntu_minimal.py` asserts a different set of bundle members (e.g.
`user_data` rather than `ks_cfg`), match it — Ubuntu does not render `ks.cfg`.

- [ ] **Step 3: Regenerate the snapshots**

```bash
pytest tests/golden/ --snapshot-update -q
```

- [ ] **Step 4: Inspect the diff before committing**

```bash
git diff --stat tests/golden/__snapshots__/
git diff tests/golden/__snapshots__/test_stig_strict.ambr
```

Expected, and nothing else:
- `test_stig_strict.ambr` — the `%post` crypto block gains the
  `fips-mode-setup --enable` / `dracut -f --regenerate-all` lines. The
  `bootloader` line must be **unchanged** (that fixture already set
  `fips_mode: true`, so it already had `fips=1`).
- `test_ubuntu_stig.ambr` — new file.

If any other `.ambr` moved, stop and find out why: a MODERN/FUTURE host must
not change at all in this work.

- [ ] **Step 5: Run the full suite**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/golden/
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
  commit -S -m "test(golden): cover STIG kernel FIPS and the Ubuntu STIG exception (#84)"
```

---

## Task 9: Correct MANUAL.md

MANUAL.md already documents behaviour that did not exist. Five places:

**Files:**
- Modify: `MANUAL.md` at ~213-224, ~750, ~885, ~1016, ~2023

- [ ] **Step 1: §3.5 crypto policy table (~line 216)**

The table's `fips=1` claim becomes true for Alma. Add the Ubuntu carve-out
directly under the table:

```markdown
On `distro: ubuntu2404`, `crypto.policy: STIG` pins STIG-aligned algorithms
but does **not** enable FIPS kernel mode — that needs an Ubuntu Pro
`fips-updates` entitlement ks-gen does not manage. `is_fips_mode_enabled` is
disabled and declared in `exceptions.md` for that reason.
```

- [ ] **Step 2: §3.5 hard constraint (~line 223)**

Replace the `overrides.fips_mode` paragraph with:

```markdown
**Hard constraint:** `overrides.fips_mode` is derived, not chosen.
`crypto.policy: STIG` on AlmaLinux enables FIPS kernel mode; MODERN and
FUTURE never do; Ubuntu cannot. Omit the key and ks-gen derives it. Setting
it to a value that contradicts `crypto.policy` is rejected at config load
(exit code 3, rule conflict) rather than silently ignored.
```

- [ ] **Step 3: The annotated config sample (~line 750)**

Replace `fips_mode: false                 # bool; mutex with crypto.policy != STIG`
with:

```yaml
  fips_mode: null                  # derived from crypto.policy; omit it
```

- [ ] **Step 4: The wizard `--set` example (~line 885)**

That example sets `overrides.fips_mode=true`, which is now redundant at best
and a load error at worst. Replace the `--set overrides.fips_mode=true \` line
with `--set crypto.policy=STIG \` and rename the output directory in that
example from `build/web01-fips` to `build/web01-stig` if it reads oddly.

- [ ] **Step 5: The `crypto_policy` rule description (~line 1016)**

Append to that table cell, before the closing `|`:

```
Under STIG on AlmaLinux, `%post` also runs `fips-mode-setup --enable` and `dracut -f --regenerate-all`, so the installed host boots with `fips=1` and the FIPS-only rules pass instead of failing forever (#84).
```

- [ ] **Step 6: The black-screen troubleshooting entry (~line 2023)**

Replace that section's body with:

```markdown
`fips=1` on the bootloader requires the dracut FIPS module in the
initramfs. Under `crypto.policy: STIG` the `crypto_policy` rule runs
`fips-mode-setup --enable` followed by `dracut -f --regenerate-all` in
`%post`, so this should not happen — `--regenerate-all` is used because
`uname -r` inside anaconda's chroot is the *installer's* kernel, not the
installed one.

If it does happen, check `/mnt/sysimage/root/ks-post.log` for the
`fips-mode-setup` line. A failure there aborts the install rather than
shipping a host that claims FIPS without being in FIPS mode, so a
black screen points at the initramfs rather than at ks-gen's `%post`.
```

- [ ] **Step 7: Check for any remaining stale claims**

```bash
grep -n "fips_mode" MANUAL.md README.md
```

Expected: only the corrected lines above. Fix any straggler.

- [ ] **Step 8: Commit**

```bash
git add MANUAL.md
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
  commit -S -m "docs(manual): describe the FIPS behaviour ks-gen actually has (#84)"
```

---

## Task 10: Install-regression FIPS assertions

`smoke-check.sh` already has a `case` on `EXPECTED_CRYPTO_POLICY` whose
non-FIPS branch asserts the host was *not* remediated into FIPS (#67). This
adds the mirror branch. These run on the installed VM over SSH, after reboot —
which is the only place `fips_enabled=1` can be observed.

**Files:**
- Modify: `tests/install-regression/smoke-check.sh` (the `case "${EXPECTED_CRYPTO_POLICY:-}"` block, ~line 113)

- [ ] **Step 1: Add the FIPS branch**

Change the case arm `FIPS* | "") ;;` to `"") ;;` and insert a new `FIPS*` arm
before it:

```bash
  FIPS*)
    # --- #84: a STIG host must really be in FIPS mode, not merely running the
    # FIPS crypto policy. Everything here needs the post-install reboot, so it
    # cannot be read from the ARF (written mid-install, pre-reboot).
    grep -qw 'fips=1' /proc/cmdline \
      || fail "kernel command line has no fips=1 on a ${EXPECTED_CRYPTO_POLICY} host (#84): $(cat /proc/cmdline)"
    ok "kernel booted with fips=1"

    # ks-gen always creates a separate /boot, so dracut needs boot= to find it.
    grep -qw 'boot=UUID=[^ ]*' /proc/cmdline \
      || fail "kernel command line has fips=1 but no boot=UUID= — separate /boot will not be found (#84)"
    ok "kernel command line carries boot=UUID="

    fips_enabled=$(cat /proc/sys/crypto/fips_enabled 2>/dev/null || echo 0)
    [[ "$fips_enabled" == "1" ]] \
      || fail "/proc/sys/crypto/fips_enabled is ${fips_enabled} on a ${EXPECTED_CRYPTO_POLICY} host (#84)"
    ok "/proc/sys/crypto/fips_enabled is 1"

    [[ -e /etc/dracut.conf.d/40-fips.conf ]] \
      || fail "/etc/dracut.conf.d/40-fips.conf missing — fips-mode-setup did not run (#84)"
    ok "/etc/dracut.conf.d/40-fips.conf present"

    # Live re-scan, not the ARF: the ARF is written pre-reboot, when
    # fips_enabled is still 0 and every one of these legitimately fails.
    # Absent is legitimate — each distro's stig profile selects a different
    # subset, and a rule its datastream does not ship has no result.
    for rid in enable_fips_mode sysctl_crypto_fips_enabled fips_crypto_subpolicy \
               system_booted_in_fips_mode enable_dracut_fips_module; do
      live=$(oscap xccdf eval --profile xccdf_ks-gen_profile_tailored \
        --tailoring-file /root/tailoring.xml \
        --rule "xccdf_org.ssgproject.content_rule_${rid}" "$ds" 2>/dev/null \
        | awk '/^Result/{print $2; exit}' || true)
      case "$live" in
        pass | "" | notselected | notapplicable)
          ok "${rid}: ${live:-absent from this datastream}" ;;
        *)
          fail "${rid} is '${live}' on a ${EXPECTED_CRYPTO_POLICY} host — the kernel is not in FIPS mode (#84)" ;;
      esac
    done
    ;;
```

`$ds` is already set earlier in the script (the datastream discovered for the
`configure_crypto_policy` re-scan) and is in scope here.

- [ ] **Step 2: Syntax-check the script**

```bash
bash -n tests/install-regression/smoke-check.sh
```

Expected: no output.

- [ ] **Step 3: Confirm the AL9 fixture is STIG**

```bash
grep -A2 '^crypto:' tests/install-regression/fixtures/al9-stig-crypto.host.yaml.tmpl
```

Expected: `policy: STIG`. Both fixtures needed for validation already exist
(`al9-stig-crypto` and `al10-stig-crypto`); neither needs editing, because
`fips_mode` is derived now.

- [ ] **Step 4: Commit**

```bash
git add tests/install-regression/smoke-check.sh
git -c user.email="github.v5f9w@bitbucket.onl" -c user.signingkey=BE707B220C995478 \
  commit -S -m "test(install-regression): assert STIG hosts really boot in FIPS mode (#84)"
```

---

## Task 11: Ship

- [ ] **Step 1: Full CI parity chain**

```bash
ruff check src tests && ruff format --check src tests && mypy && pytest -q
```

Expected: all four green. If `ruff format --check` fails, run
`ruff format src tests`, re-check, and commit as `style:`.

- [ ] **Step 2: Read the whole diff**

```bash
git diff main --stat
git diff main
```

Confirm no MODERN/FUTURE output changed and no debug edits to
`src/ks_gen/iso/_menu.py` are riding along.

- [ ] **Step 3: Recommend a code review, then wait**

Per `CLAUDE.md`, recommend `/code-review high` and let the user decide — do not
launch it. High is the right tier here: this can brick a boot and the failure is
silent until reboot. Address or consciously dismiss each finding before pushing.

- [ ] **Step 4: Push and open the PR**

The final commit (or the PR title) must carry the breaking-change marker —
existing STIG `host.yaml` files gain kernel FIPS on their next build:

```
feat(crypto)!: crypto.policy=STIG now enables FIPS kernel mode

BREAKING CHANGE: hosts built with crypto.policy=STIG on AlmaLinux now boot
with fips=1. overrides.fips_mode is derived from crypto.policy; setting it to
a contradicting value is rejected at config load.
```

Merge with `gh pr merge --squash` — the ruleset allows squash only.

- [ ] **Step 5: Recommend the install-regression runs**

These gate the merge. Recommend them to the user and let them run it — never
launch it from the agent session:

```bash
FIXTURE_TEMPLATE=tests/install-regression/fixtures/al9-stig-crypto.host.yaml.tmpl \
  tests/install-regression/run.sh
FIXTURE_TEMPLATE=tests/install-regression/fixtures/al10-stig-crypto.host.yaml.tmpl \
  tests/install-regression/run.sh
```

Traps, both of which have burned this repo before: never background the run (a
detached shell SIGHUPs QEMU) and never pipe it through `tail` (the pipeline's
exit status becomes `tail`'s, so a failed run reports success). Run it in the
foreground and let the tool auto-background it on timeout. `qemu-img info
$BUILD/disk.qcow2` showing ~196 KiB means nothing installed, whatever the
console said.

- [ ] **Step 6: Close out issue #84**

Comment on the issue recording:
- AL8 was **not** install-verified. `alma8/crypto_policy.py:54` documents that
  its SSG remediation already runs `fips-mode-setup --enable`, so AL8 STIG hosts
  were very likely already in FIPS and this change makes that explicit and
  idempotent. Reasoned, not observed — which answers the "likely distro split"
  question the issue left open.
- AL9 had a **fourth** failing rule the issue did not list:
  `enable_dracut_fips_module`, stig-selected on AL9 with no remediation shipped.
  Record whether the AL9 regression run showed it passing.

---

## Notes on what is deliberately NOT in this plan

- **No installer-side `fips=1`.** Adding it to the ISO's own boot line would be
  RHEL's preferred route, but `build_iso` takes only the rendered `ks.cfg`
  (`iso/builder.py:25`) and it would leave `ks-gen gen` users on a stock ISO
  with no FIPS. Rejected in the spec.
- **No new `fips:` config knob.** `overrides.fips_mode` already existed; the
  work is to make it derived, not to add a sibling.
- **No AL8 install-regression run** — see Task 11 Step 6.
