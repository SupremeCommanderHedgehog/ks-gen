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
    # `loginctl enable-linger` just creates a marker file under
    # /var/lib/systemd/linger, but it talks to logind over D-Bus, which is
    # absent inside anaconda's %post install chroot — there it fails with
    # "Could not enable linger: No such file or directory". Under this
    # script's `set -e`, that non-zero exit aborts the whole %post (and, with
    # `%post --erroronfail`, the install), so fall back to writing the marker
    # directly. logind honours it on first boot either way.
    if ! loginctl enable-linger "$user" 2>/dev/null; then
        warn "logind unavailable (install chroot?); writing linger marker directly"
        install -d -m 0755 /var/lib/systemd/linger
        : > "/var/lib/systemd/linger/$user"
    fi
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
    #
    # The spec is written against /var/lib/containers, NOT $CONTAINERS_ROOT:
    # we registered an fcontext *equivalency* ($CONTAINERS_ROOT -> /var/lib/
    # containers) above, and semanage rejects a local fcontext spec that would
    # shadow an equivalency-covered path ("conflicts with equivalency rule").
    # Writing the rule against the equivalency target still labels
    # $CONTAINERS_ROOT/<user>/appdata correctly at restorecon time, because
    # restorecon resolves that path through the equivalency first.
    if ! semanage fcontext -l | grep -qF "/var/lib/containers/[^/]+/appdata"; then
        info "adding container_file_t fcontext rule for per-user appdata dirs"
        semanage fcontext -a -t container_file_t "/var/lib/containers/[^/]+/appdata(/.*)?"
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
