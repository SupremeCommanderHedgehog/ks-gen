# Container-Host Preset Design

> **Status:** Approved design for #66 (under tracker #67). The lean package baseline (#65) is the recommended pairing for container hosts but is NOT a hard dependency — this work can land before, with, or after #65. If it lands first, the recommended-pairing wording in MANUAL.md gets added when #65 lands.

## Goal

Add an opt-in container-host preset to ks-gen that provisions a STIG-hardened AlmaLinux 9 host ready for rootless podman workloads out of the box: a dedicated XFS volume for container storage, podman tooling, SELinux setup, and per-user rootless service accounts. The same provisioning logic must work for kickstart-time user creation AND post-install user creation by the operator — one script, two callers.

## Motivation

Hosts built from ks-gen are increasingly deployed as container hosts running rootless podman workloads. Today an operator has to do all of this by hand after the install: install podman, carve a dedicated XFS volume, point the rootless graphroot at it, label the storage correctly for SELinux, create service users with subordinate UID/GID ranges, enable lingering, and drop authorized_keys. The kickstart pipeline exists to do exactly this kind of unattended setup.

## Locked decisions (from brainstorming)

| Decision | Choice | Reason |
| -------- | ------ | ------ |
| Activation surface | New top-level `containers:` block | Cleanest layer boundaries; composes orthogonally with `packages.preset` from #65. |
| Disk integration | Auto-inject one extra `logvol` after the preset/layout block | Works for both `disk.preset` and `disk.layout` without schema migration. |
| User scope | Container users are distinct from the admin user | The mirror is for rootless container workloads; admins manage the host, not the workloads. |
| Container-user access | SSH login with `authorized_keys`, no sudo, no wheel | Matches the rootless-podman operational model — operator SSHs in as the user. |
| Provisioning logic | A single shell script (`create-rootless-user.sh`) is the source of truth, called by both kickstart and operator | Eliminates drift between install-time and post-install user creation. |
| Quadlet scaffold at kickstart | Off | Production hosts shouldn't ship example.container; operator can re-run `-q` post-install. |

## Architecture

### High-level shape

- New `Containers` config model at `cfg.containers`. Default `enabled=False` — backwards compatible.
- New rule `src/ks_gen/rules/container_host.py` with `applies(cfg): cfg.containers.enabled`.
- Provisioning script ships in the repo at `src/ks_gen/assets/create-rootless-user.sh` and is loaded by the rule via `importlib.resources`.
- The rule's `emit_post` block: drops the script to `/root/create-rootless-user.sh` (mode 0550), writes `/etc/containers/storage.conf`, and calls the script once per configured user.
- The rule's `emit_packages` adds the podman tooling stack.
- The ks.cfg.j2 template gains a small Jinja block that auto-injects one extra `logvol /srv/containers` line when `cfg.containers.enabled`.

### Composition with #65 (lean package baseline)

Orthogonal. `packages.preset: lean` and `containers.enabled: true` are independent switches; the recommended container-host config sets both. Documented in MANUAL.md.

## Config schema

```yaml
containers:
  enabled: true
  users:                          # may be empty — script still installed at /root
    - name: webapp
      gecos: "Web app workloads"
      authorized_keys:
        - "ssh-ed25519 AAAA... webapp@bastion"
        - "ssh-ed25519 BBBB... webapp@laptop"
    - name: dbproxy
      authorized_keys:
        - "ssh-ed25519 CCCC... dbproxy@bastion"
  volume:
    size: "20G"                   # default 20G; parsed to MiB at template time
    fsoptions: "nodev,nosuid"     # default; validator rejects token == "noexec"
```

### `Containers` model

- `enabled: bool = False`
- `users: list[ContainerUser] = []` — default empty is intentional (script still installed for later use)
- `volume: ContainerVolume = Field(default_factory=ContainerVolume)`
- `@model_validator(mode="after")`: when `enabled=True`, all `users[].name` are distinct.

### `ContainerUser` model

- `name: str = Field(..., pattern=r"^[a-z_][a-z0-9_-]{0,31}$")` — matches the script's own regex.
- `@field_validator("name")`: rejects `root` (same as `AdminUser._not_root`).
- `gecos: str = ""`
- `authorized_keys: list[str] = Field(..., min_length=1)` — kickstart-created users need at least one way in.

Implicit (not config-surface): shell=`/bin/bash`, password-locked, no sudo, no wheel group. All baked into the script's `useradd` defaults.

### `ContainerVolume` model

- `size: str = Field(default="20G", pattern=r"^\d+(M|G|T)$")` — same shape as `DiskLvDef.size`.
- `fsoptions: str = "nodev,nosuid"`
- `@property size_mib: int` — converts to MiB for the partition line. `"20G" → 20480`, `"500M" → 500`, `"1T" → 1048576`.
- `@field_validator("fsoptions")`: splits on commas + whitespace, rejects any token whose value is exactly `noexec`. Reason: container image layers must execute; `noexec` defeats the preset's purpose.

### HostConfig-level cross-cutting validators

- When `cfg.containers.enabled` and any `cfg.containers.users[].name == cfg.user.admin.name`: reject. Admin user is for host administration; container users are for rootless workloads.
- When `cfg.containers.enabled` and `cfg.disk.layout` is set and any `cfg.disk.layout.lvs[].mount == "/srv/containers"`: reject (duplicate mount). The auto-injected logvol would conflict.

## Disk integration

Edit `src/ks_gen/templates/ks.cfg.j2`, right after the existing partition include block:

```jinja
{% if cfg.disk.layout -%}
{% include 'partials/partitioning_layout.j2' %}
{% else -%}
{% include 'partials/partitioning_' ~ cfg.disk.preset.value ~ '.j2' %}
{% endif %}

{% if cfg.containers.enabled -%}
logvol /srv/containers --vgname={{ cfg.disk.layout.vg_name if cfg.disk.layout else 'vg_root' }} --name=containers --fstype=xfs --size={{ cfg.containers.volume.size_mib }} --fsoptions="{{ cfg.containers.volume.fsoptions }}"
{% endif %}
```

Both partials hardcode the VG name as `vg_root`, so the conditional `cfg.disk.layout.vg_name if cfg.disk.layout else 'vg_root'` covers both shapes correctly. The new LV sits inside the existing PV+VG; the PV already uses `--grow`, so there's space.

## The `container_host` rule

`src/ks_gen/rules/container_host.py` — follows the existing rule contract (`_Rule` dataclass + `RULE` cast, mirroring `admin_user_and_keys.py`).

### Rule contract

- `id = "container_host"`
- `summary = "Install rootless-container helper, storage.conf, and per-user setup on /srv/containers."`
- `depends_on = []`
- `stig_rules_affected = []`
- `applies(cfg) -> bool`: returns `cfg.containers.enabled`
- `emit_tailoring(cfg) -> []` — no STIG rules downgraded
- `exception_entry(cfg) -> None` — nothing to document in exceptions.md
- `emit_packages(cfg) -> list[str]`:
  ```python
  return [
      "podman",
      "crun",
      "slirp4netns",
      "fuse-overlayfs",
      "containers-common",
      "podman-plugins",
  ]
  ```
  (`policycoreutils-python-utils`, which provides `semanage`, is already in `Packages.required` defaults.)

### Asset loading

```python
from importlib.resources import files

_SCRIPT = files("ks_gen.assets").joinpath("create-rootless-user.sh").read_text(encoding="utf-8")
```

Module-level constant — read once on import, embedded verbatim in every emit. Add `src/ks_gen/assets/__init__.py` (empty marker) so `importlib.resources` sees it as a package.

### `emit_post` body shape

```bash
# ===== container_host =====
# Install the rootless-container-user helper at /root for post-install use
cat > /root/create-rootless-user.sh <<'__KS_GEN_EOF__'
{_SCRIPT verbatim}
__KS_GEN_EOF__
chown root:root /root/create-rootless-user.sh
chmod 0550 /root/create-rootless-user.sh

# System-wide storage.conf — pins rootless graphroot to the /srv/containers mirror
install -d -m 0755 /etc/containers
cat > /etc/containers/storage.conf <<'__KS_GEN_EOF__'
[storage]
driver = "overlay"
rootless_storage_path = "/srv/containers/$USER/storage"
__KS_GEN_EOF__
chmod 0644 /etc/containers/storage.conf

# Provision each configured container user
/root/create-rootless-user.sh -l -c "Web app workloads" webapp
install -d -m 0700 -o webapp -g webapp /home/webapp/.ssh
cat > /home/webapp/.ssh/authorized_keys <<'__KS_GEN_EOF__'
ssh-ed25519 AAAA... webapp@bastion
ssh-ed25519 BBBB... webapp@laptop
__KS_GEN_EOF__
chown webapp:webapp /home/webapp/.ssh/authorized_keys
chmod 0600 /home/webapp/.ssh/authorized_keys
restorecon -R /home/webapp/.ssh

# (repeat the user block for each entry in containers.users)
```

### Why we manage `authorized_keys` outside the script

The script's `-k` flag installs exactly one key. Container users typically need multiple authorized keys (bastion + laptop + emergency). Rather than loop the script with `-k` once per key (correct but verbose), we call the script without `-k`, then drop the full `authorized_keys` file in one heredoc — the same pattern `admin_user_and_keys` uses for the admin. The script's `-k` is reserved for the operator's post-install single-key flow.

### Why no `-q` (Quadlet scaffold) at kickstart time

The script's `-q` flag creates `example.network` + `example.volume` + `example.container` units as a starter template. Useful for the operator's "let me try this" workflow; not appropriate to ship on every production host. The script is idempotent, so the operator can re-run `/root/create-rootless-user.sh -q <existing-user>` post-install to add the scaffold to an already-provisioned user.

### Why always `-l` (linger) at kickstart time

Quadlet units and `systemctl --user` workloads need linger to survive logout and start at boot. There's no use case for a kickstart-provisioned container user without linger.

### Heredoc safety

The script body contains literal `$user`, `$store`, `$home`, etc. shell variable references. Embedding via a single-quoted heredoc (`<<'__KS_GEN_EOF__'`) prevents any expansion at the kickstart's `%post` shell. Project convention (see `admin_user_and_keys.py:35,43`) already uses this delimiter.

## Validation rules — full list

1. `ContainerUser.name`: pattern `^[a-z_][a-z0-9_-]{0,31}$`; rejects `root`.
2. `ContainerUser.authorized_keys`: `min_length=1`.
3. `ContainerVolume.size`: pattern `^\d+(M|G|T)$`.
4. `ContainerVolume.fsoptions`: token `"noexec"` rejected.
5. `Containers` (when enabled): `users[].name` distinct.
6. `HostConfig` (when `containers.enabled`): no `users[].name == cfg.user.admin.name`.
7. `HostConfig` (when `containers.enabled` and `disk.layout` set): no LV mounted at `/srv/containers`.

## Testing

### Unit tests (`tests/test_config_schema.py`)

- `Containers` defaults — `enabled=False`, empty users, default volume.
- `ContainerUser` rejects `root`, rejects invalid name patterns, requires ≥1 authorized key.
- `Containers` validator rejects duplicate user names.
- `ContainerVolume` size parses correctly: `"20G" → 20480`, `"500M" → 500`, `"1T" → 1048576`.
- `ContainerVolume.fsoptions` rejects whole-token `"noexec"`; accepts `"nodev,nosuid"`, `"nodev,nosuid,noatime"`, and similar.
- `HostConfig` validator: rejects when `containers.users[].name == user.admin.name`.
- `HostConfig` validator: rejects when `containers.enabled` and `disk.layout` includes an LV mounted at `/srv/containers`.

### Golden tests (`tests/golden/`)

- **`container-host.host.yaml`** — `containers.enabled: true`, two users with multi-key, default volume, default `disk.preset: stig_server`. Snapshot diff vs `test_minimal_dhcp` should add: one `logvol /srv/containers` line in the partition block, container-related packages in `%packages`, the `# ===== container_host =====` block in `%post` with script body, storage.conf, and per-user provisioning. Nothing else should drift.
- **`container-host-lean.host.yaml`** — same plus `packages.preset: lean`. Confirms #65 and #66 compose cleanly. Diff vs the standard container-host golden should differ only in `%packages` (lean stripping `@standard` + adding compensators).

### Lint

No new lint rule. The HostConfig-level validators above catch the only meaningful misconfigurations.

### Install-regression harness (`.scratch/install-regression/`)

Recommended before merge per project CLAUDE.md guidance — this PR touches `%packages`, partition layout, AND `%post` rule emission. Acceptance checks for the harness run:

- `findmnt /srv/containers` → mounted XFS, options include `nodev,nosuid`, NOT `noexec`.
- `matchpathcon /srv/containers/webapp/storage` → resolves to `container_file_t` (via the script's `semanage fcontext -e /var/lib/containers /srv/containers` equivalence rule).
- As `webapp`: `podman info --format '{{.Store.GraphRoot}}'` → `/srv/containers/webapp/storage`.
- As `webapp`: `podman run --rm docker.io/library/alpine echo ok` → `ok`.
- `loginctl show-user webapp -p Linger` → `Linger=yes`.
- `ls -l /root/create-rootless-user.sh` → exists, mode `r-xr-x---` (0550), `root:root`.
- Idempotency: as root, re-run `/root/create-rootless-user.sh -q webapp` → exits 0, creates `~/.config/containers/systemd/example.{network,volume,container}` for `webapp`, leaves the existing user/storage/subuid setup untouched.

## Out of scope

- CNI / podman networking configuration (the script's `-q` Quadlet scaffold ships an example `Driver=bridge` network for operator use, but no opinionated networking enforcement).
- Container image pre-staging.
- Multi-VG layouts where `/srv/containers` should live on a separate VG from `/`. Current design uses the same VG (`vg_root` or `cfg.disk.layout.vg_name`) so the existing PV's `--grow` covers it. A future RAID1-mirror / separate-VG variant could be a follow-up but is not in this PR.
- A list of `extra_users` for non-admin SSH access not tied to containers — out of scope.
- Auto-creating an admin equivalent for container users (e.g. a `containerops` group with sudo to `systemctl --user`). The current model is: each container user manages their own units; the host admin manages the host.

## Notes for the implementation plan

- The lean preset (#65) is the recommended pairing but not a hard dependency. Plan can execute independently.
- Suggested task order: asset directory + script copy + asset loader → config models (`ContainerVolume`, `ContainerUser`, `Containers`) → HostConfig wiring + cross-cutting validators → disk template change → the `container_host` rule → goldens → MANUAL.md. TDD throughout.
- **The script body in Appendix A is the source of truth.** Copy it byte-identical into `src/ks_gen/assets/create-rootless-user.sh`. Do not "improve" it during implementation — any change to the script's behavior is a separate design decision, not part of this PR.
- Spec lives on its own branch (`spec/container-host-preset`) off `origin/main` so it's durable independently of the #65 PR.

## Appendix A: `create-rootless-user.sh` (script body, verbatim)

This is the source of truth for the provisioning script. Copy it to `src/ks_gen/assets/create-rootless-user.sh` during implementation. Do not modify.

```bash
#!/usr/bin/env bash
#
# create-rootless-user.sh
#
# Provision a Linux user account to run rootless Podman containers whose
# storage lives on the /srv/containers mirror (XFS on LVM RAID1).
#
# Idempotent: safe to re-run for an existing user. It will:
#   * create the account if it doesn't exist
#   * ensure subordinate UID/GID ranges exist (user namespaces need them)
#   * create a per-user storage dir on the mirror, owned by the user
#   * apply the correct SELinux labels
#   * optionally enable linger (containers run at boot / survive logout)
#   * optionally install an SSH public key for remote management
#   * optionally scaffold a wired-together starter Quadlet set:
#       example.network + example.volume + example.container
#
# Target: AlmaLinux 9 / Podman. Must be run as root.

set -euo pipefail

# --- configuration ---------------------------------------------------------
CONTAINERS_ROOT="/srv/containers"          # mount point of the mirror
STORAGE_CONF="/etc/containers/storage.conf"
SUBID_COUNT=65536                          # size of each subuid/subgid block
DEFAULT_SHELL="/bin/bash"

# --- logging ---------------------------------------------------------------
info() { printf '[*] %s\n' "$*"; }
warn() { printf '[!] %s\n' "$*" >&2; }
die()  { printf '[x] %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<EOF
Usage: ${0##*/} [options] <username>

Provision a user for rootless containers on ${CONTAINERS_ROOT}.

Options:
  -c "Full Name"   GECOS comment for a new account
  -s SHELL         login shell for a new account (default: ${DEFAULT_SHELL})
  -k "SSH KEY"     install this public key into the user's authorized_keys
  -l               enable linger (start containers at boot / outlive logout)
  -q               scaffold a starter Quadlet set (network + volume + container)
                   in the user's ~/.config/containers/systemd/ directory
  -h               show this help

Examples:
  ${0##*/} appsvc
  ${0##*/} -l -q -c "App Service" appsvc
  ${0##*/} -l -k "\$(cat ./id_ed25519.pub)" deploy
EOF
}

# --- option parsing --------------------------------------------------------
comment=""
shell="${DEFAULT_SHELL}"
ssh_key=""
enable_linger=0
scaffold_quadlet=0
home=""
qdir=""
appdata=""

while getopts ':c:s:k:lqh' opt; do
    case "$opt" in
        c) comment="$OPTARG" ;;
        s) shell="$OPTARG" ;;
        k) ssh_key="$OPTARG" ;;
        l) enable_linger=1 ;;
        q) scaffold_quadlet=1 ;;
        h) usage; exit 0 ;;
        :) die "option -$OPTARG requires an argument (use -h)" ;;
        \?) die "unknown option -$OPTARG (use -h)" ;;
    esac
done
shift $((OPTIND - 1))

[ $# -eq 1 ] || { usage; exit 1; }
user="$1"

# --- preflight checks ------------------------------------------------------
[ "$(id -u)" -eq 0 ] || die "must be run as root"

[[ "$user" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || die "invalid username: '$user'"

command -v semanage >/dev/null 2>&1 \
    || die "semanage not found; install policycoreutils-python-utils"

command -v podman >/dev/null 2>&1 \
    || warn "podman not found in PATH; install container-tools before running containers"

# Refuse to write into the root filesystem if the mirror isn't mounted.
mountpoint -q "$CONTAINERS_ROOT" \
    || die "$CONTAINERS_ROOT is not a mounted filesystem; refusing to write to the root fs"

if ! grep -Eq "^[[:space:]]*rootless_storage_path[[:space:]]*=.*${CONTAINERS_ROOT}" \
        "$STORAGE_CONF" 2>/dev/null; then
    warn "rootless_storage_path in $STORAGE_CONF does not point under $CONTAINERS_ROOT;"
    warn "rootless storage for this user may not land on the mirror."
fi

# --- ensure the SELinux equivalence for the tree --------------------------
if ! semanage fcontext -l | grep -q "^${CONTAINERS_ROOT} "; then
    info "adding SELinux fcontext equivalence ${CONTAINERS_ROOT} -> /var/lib/containers"
    semanage fcontext -a -e /var/lib/containers "$CONTAINERS_ROOT"
fi

# --- create the account ----------------------------------------------------
if id "$user" >/dev/null 2>&1; then
    info "user '$user' already exists; ensuring container setup"
else
    info "creating user '$user'"
    useradd_args=(--create-home --shell "$shell")
    [ -n "$comment" ] && useradd_args+=(--comment "$comment")
    useradd "${useradd_args[@]}" "$user"
fi

# --- ensure subordinate id ranges -----------------------------------------
# useradd auto-allocates these on Alma9, but a pre-existing account may lack
# them. Compute the next free block and assign it via usermod.
ensure_subids() {
    local file="$1"      # /etc/subuid or /etc/subgid
    local flag="$2"      # --add-subuids or --add-subgids
    if grep -q "^${user}:" "$file" 2>/dev/null; then
        return 0
    fi
    local start
    start=$(awk -F: 'NF>=3 {e=$2+$3; if (e>m) m=e} END {print (m>100000)?m:100000}' \
        "$file" 2>/dev/null)
    [ -n "$start" ] || start=100000
    info "allocating ${file##*/} range for '$user': ${start}-$((start + SUBID_COUNT - 1))"
    usermod "$flag" "${start}-$((start + SUBID_COUNT - 1))" "$user"
}
ensure_subids /etc/subuid --add-subuids
ensure_subids /etc/subgid --add-subgids

# --- per-user storage on the mirror ---------------------------------------
store="${CONTAINERS_ROOT}/${user}/storage"
info "creating storage dir $store"
install -d -m 0700 -o "$user" -g "$user" "$store"
restorecon -R "${CONTAINERS_ROOT}/${user}"

# --- optional: linger ------------------------------------------------------
if [ "$enable_linger" -eq 1 ]; then
    info "enabling linger for '$user'"
    loginctl enable-linger "$user"
fi

# --- optional: ssh key -----------------------------------------------------
if [ -n "$ssh_key" ]; then
    home=$(getent passwd "$user" | cut -d: -f6)
    [ -n "$home" ] || die "could not determine home dir for '$user'"
    info "installing SSH key into $home/.ssh/authorized_keys"
    install -d -m 0700 -o "$user" -g "$user" "$home/.ssh"
    keyfile="$home/.ssh/authorized_keys"
    touch "$keyfile"
    if ! grep -qxF "$ssh_key" "$keyfile"; then
        printf '%s\n' "$ssh_key" >> "$keyfile"
    fi
    chown "$user:$user" "$keyfile"
    chmod 0600 "$keyfile"
    restorecon -R "$home/.ssh"
fi

# --- optional: starter Quadlet set (network + volume + container) ---------
if [ "$scaffold_quadlet" -eq 1 ]; then
    home=$(getent passwd "$user" | cut -d: -f6)
    [ -n "$home" ] || die "could not determine home dir for '$user'"
    qdir="$home/.config/containers/systemd"
    appdata="${CONTAINERS_ROOT}/${user}/appdata"

    info "scaffolding Quadlet units in $qdir"
    runuser -l "$user" -c 'mkdir -p ~/.config/containers/systemd'

    # Persistent SELinux label so the bind-mounted volume data is usable by
    # containers. One regex rule covers <root>/<any-user>/appdata for everyone.
    if ! semanage fcontext -l | grep -qF "${CONTAINERS_ROOT}/[^/]+/appdata"; then
        info "adding container_file_t fcontext rule for per-user appdata dirs"
        semanage fcontext -a -t container_file_t "${CONTAINERS_ROOT}/[^/]+/appdata(/.*)?"
    fi
    info "creating volume backing dir $appdata"
    install -d -m 0700 -o "$user" -g "$user" "$appdata"
    restorecon -RF "$appdata"

    # network unit -> example-network.service, podman net 'systemd-example'
    netfile="$qdir/example.network"
    if [ -e "$netfile" ]; then
        info "leaving existing $netfile untouched"
    else
        cat > "$netfile" <<'UNIT'
# Rootless container network. Generates 'example-network.service' and a
# podman network named 'systemd-example'. Reference from a .container with:
#   Network=example.network

[Network]
Driver=bridge
# Subnet=10.89.0.0/24
# Gateway=10.89.0.1
UNIT
        chown "$user:$user" "$netfile"; chmod 0644 "$netfile"
        restorecon "$netfile" 2>/dev/null || true
    fi

    # volume unit -> bind-backed local volume pinned to $appdata on the mirror
    volfile="$qdir/example.volume"
    if [ -e "$volfile" ]; then
        info "leaving existing $volfile untouched"
    else
        cat > "$volfile" <<UNIT
# Rootless named volume bind-mounted to a directory on the mirror.
# Generates 'example-volume.service' and a podman volume 'systemd-example'.
# Reference from a .container with:  Volume=example.volume:/data

[Volume]
Driver=local
Type=none
Device=${appdata}
Options=bind
UNIT
        chown "$user:$user" "$volfile"; chmod 0644 "$volfile"
        restorecon "$volfile" 2>/dev/null || true
    fi

    # container unit, wired to the network and volume above
    starter="$qdir/example.container"
    if [ -e "$starter" ]; then
        info "leaving existing $starter untouched"
    else
        cat > "$starter" <<'UNIT'
# Starter rootless Quadlet unit -- EDIT THIS FILE, then as the user run:
#   systemctl --user daemon-reload
#   systemctl --user start example        # test it now
# To start automatically at boot (requires: loginctl enable-linger <user>),
# uncomment the [Install] section below, then:
#   systemctl --user enable example
#
# Reference: man quadlet

[Unit]
Description=Starter rootless container (edit me)

[Container]
Image=registry.access.redhat.com/ubi9/ubi-minimal:latest
Exec=sleep infinity
Network=example.network
Volume=example.volume:/data
# PublishPort=8080:8080
# Environment=KEY=value
AutoUpdate=registry

[Service]
Restart=on-failure

# [Install]
# WantedBy=default.target
UNIT
        chown "$user:$user" "$starter"; chmod 0644 "$starter"
        restorecon "$starter" 2>/dev/null || true
    fi

    if [ "$enable_linger" -eq 0 ]; then
        warn "Quadlet units won't start at boot until you enable linger (-l) for '$user'"
    fi
fi

# --- best-effort verification (also initializes the store) ----------------
if command -v podman >/dev/null 2>&1; then
    if gr=$(runuser -l "$user" -c "podman info --format '{{.Store.GraphRoot}}'" 2>/dev/null); then
        info "podman store for '$user': $gr"
        [ "$gr" = "$store" ] || warn "store path ($gr) != expected ($store)"
    else
        warn "could not query podman as '$user' yet; verify manually after first login"
    fi
fi

# --- summary ---------------------------------------------------------------
cat <<EOF

[*] Done. '$user' is configured for rootless containers.
    storage : $store
    subuid  : $(grep "^${user}:" /etc/subuid 2>/dev/null || echo MISSING)
    linger  : $([ "$enable_linger" -eq 1 ] && echo enabled || echo 'not enabled (pass -l)')
    quadlet : $([ "$scaffold_quadlet" -eq 1 ] && echo "$qdir (example.network/.volume/.container)" || echo 'not scaffolded (pass -q)')
    appdata : $([ "$scaffold_quadlet" -eq 1 ] && echo "$appdata (volume bind target)" || echo '-')

Verify manually:
    runuser -l $user -c "podman info --format '{{.Store.GraphRoot}}'"
    # expect: $store
EOF
```
