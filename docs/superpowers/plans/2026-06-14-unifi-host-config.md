# `unifi` host config — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Author `build/unifi/unifi.yaml` per the approved spec
(`docs/superpowers/specs/2026-06-14-unifi-host-config-design.md`) and
validate it by generating a kickstart bundle with `ks-gen gen`.

**Architecture:** This is a consumer artifact, not a ks-gen code change.
The "test" is that the application — whose pydantic schema and
post-validators in `src/ks_gen/config.py` are the contract for any
config it accepts — successfully produces a bundle from this file. No
new tests, no production code edits.

**Tech Stack:** Plain YAML; ks-gen 0.12.2 CLI from the project's
Windows `.venv` (`C:\Users\yizshachuck\source\ks-gen\.venv\Scripts\ks-gen.exe`).

---

## File Structure

- Create: `build/unifi/unifi.yaml` — the consumer config. Lives next to
  the existing `build/unifi/UNIFI_INSTALL.md`. `build/` is gitignored,
  so this file stays machine-local and is **not** committed.
- Generated (not authored): `build/unifi/bundle/{ks.cfg,tailoring.xml,exceptions.md,host.yaml}`
  — produced by `ks-gen gen`, also gitignored.

No source-code files are modified.

---

### Task 1: Write `build/unifi/unifi.yaml`

**Files:**
- Create: `C:\Users\yizshachuck\source\ks-gen\build\unifi\unifi.yaml`

- [x] **Step 1: Write the config file**

Content (exact — copy verbatim):

```yaml
# UniFi OS Server host (see build/unifi/UNIFI_INSTALL.md for post-install recipe)
#
# Lean STIG-hardened AlmaLinux 9. UniFi's installer brings podman and writes
# its own per-user storage.conf, so we do NOT enable the container_host rule
# (its /srv/containers/$USER/storage pin gets overridden by UniFi anyway —
# see reference_unifi_install_on_stig_host.md).

system:
  hostname: unifi

network:
  interfaces:
    - device: eth0
      bootproto: dhcp
      onboot: true

user:
  admin:
    name: yizshachuck-admin
    gecos: "yizshachuck-admin"
    authorized_keys:
      - "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIE4lYlqPDyt+c2YsS54ML0gS0eADwa/AswXmszzTUbdv pat@krypte.me"
    sudo: nopasswd_yes

packages:
  preset: lean
```

- [x] **Step 2: Verify the file exists**

PowerShell:
```powershell
Test-Path C:\Users\yizshachuck\source\ks-gen\build\unifi\unifi.yaml
```
Expected: `True`

- [x] **Step 3: Do NOT commit**

`build/` is in `.gitignore`. Skip `git add`. Confirm with:

```powershell
git -C C:\Users\yizshachuck\source\ks-gen check-ignore -v build\unifi\unifi.yaml
```
Expected: a line like `.gitignore:<n>:build/    build/unifi/unifi.yaml`.

---

### Task 2: Validate the config by generating a bundle

**Files:**
- Read: `build/unifi/unifi.yaml`
- Generated: `build/unifi/bundle/ks.cfg`, `tailoring.xml`, `exceptions.md`, `host.yaml`

- [x] **Step 1: Run `ks-gen gen`**

PowerShell:
```powershell
C:\Users\yizshachuck\source\ks-gen\.venv\Scripts\ks-gen.exe gen `
  --config C:\Users\yizshachuck\source\ks-gen\build\unifi\unifi.yaml `
  --out    C:\Users\yizshachuck\source\ks-gen\build\unifi\bundle
```

Expected on success: exit code 0, last line `Wrote bundle to C:\...\build\unifi\bundle`.

If exit code is non-zero, the failure is either (a) a pydantic
`ConfigError` printed to stderr — fix the YAML to match
`src/ks_gen/config.py:HostConfig`, or (b) a `lint FAIL: ...` line —
fix whichever field that lint reports.

- [x] **Step 2: List the produced bundle**

PowerShell:
```powershell
ls C:\Users\yizshachuck\source\ks-gen\build\unifi\bundle
```
Expected: four files — `ks.cfg`, `tailoring.xml`, `exceptions.md`,
`host.yaml`.

- [x] **Step 3: Spot-check the rendered hostname and admin user**

PowerShell:
```powershell
Select-String -Path C:\Users\yizshachuck\source\ks-gen\build\unifi\bundle\ks.cfg -Pattern '^(network --hostname|user --name|rootpw|sshkey)' | Select-Object -First 10
```

Expected (order may vary): a `network --hostname=unifi ...` line, a
`user --name=yizshachuck-admin ...` line (groups including `wheel`),
and an `sshkey --username=yizshachuck-admin "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5...pat@krypte.me"`
line. The `rootpw` line should have `--lock` (root is locked by the
STIG profile).

- [x] **Step 4: Spot-check the lean package preset took effect**

PowerShell:
```powershell
Select-String -Path C:\Users\yizshachuck\source\ks-gen\build\unifi\bundle\ks.cfg -Pattern '^@standard$|^logrotate$|^postfix$|^cronie$|^crontabs$|^parted$'
```

Expected: no `@standard` line, but `logrotate`, `postfix`, `cronie`,
`crontabs`, and `parted` are all present in the `%packages` block.

- [x] **Step 5: No commit**

The bundle is also under `build/` and is gitignored. Nothing to commit.

---

## Done criteria

- `build/unifi/unifi.yaml` exists and is readable.
- `ks-gen gen` exits 0 against it.
- The rendered `ks.cfg` shows hostname=`unifi`, admin user
  `yizshachuck-admin`, the embedded ed25519 key, and the lean package
  shape (no `@standard`, plus the five lean-extras).

## What is NOT in this plan

- Building the ISO (`ks-gen iso`). The memory says `xorriso` only lives
  in WSL Ubuntu on this machine, so an ISO build would require running
  ks-gen from `~/.venvs/ks-gen/bin/ks-gen` under WSL against a
  `/mnt/c/...`-translated path. Defer to a follow-up once the user
  decides whether they want an ISO or HTTP-served bundle.
- Actually installing AlmaLinux on the `unifi` host or invoking the
  UniFi installer — that's the recipe in `build/unifi/UNIFI_INSTALL.md`,
  which runs on the target machine post-boot.
