#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PAYLOAD="${SCRIPT_DIR}/payload"
readonly LOG_FILE=/var/log/mudos-install.log
readonly LOCK_FILE=/run/lock/mudos-install.lock
VERSION=''
VERSION_TAG=''

STAGE="preflight"
VERIFY_ONLY=0
SYSTEM_CHANGED=0
INPUT_CHANGED=0
RELEASE_CHANGED=0

PACKAGES=(
    inputplumber gamescope-git dolphin-emu retroarch
    libretro-nestopia libretro-genesis-plus-gx steam steam-devices
    seatd pipewire wireplumber qt6-base qt6-declarative sdl3 python
    python-dbus-next
)
# These are deliberately absent from PACKAGES: each has an official-repository
# attempt followed by the reviewed payload build when the repository lacks it.

log() { printf '[mudos] %s\n' "$*"; }
die() { log "ERROR: $*" >&2; exit 1; }
step() {
    STAGE="$1"
    log "[$2/10] $1"
}
on_error() {
    local status=$?
    log "FAILED stage: ${STAGE}" >&2
    log "The command failed with status ${status}. Inspect ${LOG_FILE} and run: systemctl status inputplumber.service lulu.target" >&2
    exit "$status"
}
trap on_error ERR

usage() {
    cat <<'EOF'
Usage: sudo ./install-mudos.sh [--verify]

  --verify    verify the installed host without changing it
EOF
}

while (($#)); do
    case "$1" in
        --verify) VERIFY_ONLY=1 ;;
        -h|--help) usage; exit 0 ;;
        *) die "unknown argument: $1" ;;
    esac
    shift
done

if (( EUID != 0 )); then
    die 'run as root, for example: sudo ./install-mudos.sh'
fi

install -d -m 0755 "$(dirname "$LOG_FILE")"
exec > >(tee -a "$LOG_FILE") 2>&1
exec 9>"$LOCK_FILE"
flock -n 9 || die 'another Mudos installer is already running'

require_file() { [[ -f "$1" ]] || die "missing required file: $1"; }
require_dir() { [[ -d "$1" ]] || die "missing required directory: $1"; }

load_checkpoint() {
    local key value
    while IFS='=' read -r key value; do
        case "$key" in
            commit) VERSION=$value ;;
            tag) VERSION_TAG=$value ;;
        esac
    done < "$SCRIPT_DIR/CHECKPOINT"
    [[ "$VERSION" =~ ^[0-9a-fA-F]{7,40}$ ]] || die 'payload checkpoint has no valid commit'
    [[ -n "$VERSION_TAG" && "$VERSION_TAG" != *$'\n'* ]] || die 'payload checkpoint has no valid tag'
}

verify_payload() {
    require_file "$SCRIPT_DIR/CHECKPOINT"
    require_dir "$PAYLOAD"
    load_checkpoint
    require_file "$PAYLOAD/manifest.sha256"
    (cd "$PAYLOAD" && sha256sum --strict --check manifest.sha256)
    for path in lib/lulu bin/lulu-shell bin/mudos-guide bin/lulu-vt bin/verify-mudos.sh ui config packaging scripts/steam-session-bootstrap.sh scripts/steam-bootstrap.sh; do
        [[ -e "$PAYLOAD/$path" ]] || die "payload is incomplete: $path"
    done
    for script in "$PAYLOAD/scripts/steam-session-bootstrap.sh" "$PAYLOAD/scripts/steam-bootstrap.sh"; do
        [[ -x "$script" ]] || die "runtime script is not executable: $script"
    done
    (cd "$PAYLOAD" && while read -r _ path; do [[ "$path" == ./manifest.sha256 || -f "$path" ]] || exit 1; done < manifest.sha256) || die 'payload manifest references a missing file'
}

verify_packages() {
    local package
    for package in "${PACKAGES[@]}"; do
        pacman -Q "$package" >/dev/null 2>&1 || die "required package is not installed: $package"
    done
    pacman -Q ttf-zalando-sans >/dev/null 2>&1 || die 'required package is not installed: ttf-zalando-sans'
    command -v python >/dev/null || die 'python executable is missing'
    command -v systemctl >/dev/null || die 'systemctl executable is missing'
    command -v busctl >/dev/null || die 'busctl executable is missing'
    for executable in dolphin-emu pcsx2 pcsx2-qt retroarch gamescope; do
        command -v "$executable" >/dev/null || die "required executable is missing: $executable"
    done
}

verify_installed() {
    verify_packages
    [[ -L /opt/lulu/current && -f /opt/lulu/current/RELEASE ]] || die '/opt/lulu/current is not a versioned release'
    [[ "$(readlink -f /opt/lulu/current)" == /opt/lulu/releases/* ]] || die '/opt/lulu/current does not resolve below /opt/lulu/releases'
    grep -Fxq "commit=${VERSION}" /opt/lulu/current/RELEASE || die 'installed release commit does not match checkpoint'
    grep -Fxq "tag=${VERSION_TAG}" /opt/lulu/current/RELEASE || die 'installed release tag does not match checkpoint'
    [[ "$(sha256sum /opt/lulu/current/manifest.sha256 | cut -c1-12)" == "$(sed -n 's/^manifest=//p' /opt/lulu/current/RELEASE)" ]] || die 'installed manifest digest does not match release'
    (cd /opt/lulu/current && sha256sum --strict --check manifest.sha256)
    for path in lib/lulu bin/lulu-shell bin/mudos-guide bin/lulu-vt ui config scripts/steam-session-bootstrap.sh scripts/steam-bootstrap.sh; do
        [[ -e "/opt/lulu/current/$path" ]] || die "installed payload is incomplete: $path"
    done
    id lulu >/dev/null 2>&1 || die 'lulu user is missing'
    [[ "$(id -u lulu)" == 958 && "$(id -g lulu)" == 958 ]] || die 'lulu UID/GID is not 958'
    [[ "$(getent passwd lulu | cut -d: -f6)" == /home/lulu ]] || die 'lulu home is not /home/lulu'
    [[ "$(getent passwd lulu | cut -d: -f7)" == /bin/bash ]] || die 'lulu shell is not /bin/bash'
    getent group seat >/dev/null || die 'seat group is missing'
    getent group inputplumber >/dev/null || die 'inputplumber group is missing'
    id -nG lulu | tr ' ' '\n' | grep -Fxq inputplumber || die 'lulu is not in inputplumber group'
    ! id -nG lulu | tr ' ' '\n' | grep -Fxq wheel || die 'lulu must not be granted wheel access'
    for path in /home/lulu/Games/ROMs/nes /home/lulu/Games/ROMs/genesis /home/lulu/Games/ROMs/ps2 /home/lulu/Games/ROMs/wii /home/lulu/Games/BIOS/ps2; do
        [[ -d "$path" ]] || die "required data directory is missing: $path"
        [[ "$(stat -c '%U:%G' "$path")" == lulu:lulu ]] || die "wrong ownership: $path"
    done
    for file in lulu.target lulu-session@.service lulu-consoled.service; do
        systemd-analyze verify "/etc/systemd/system/$file"
    done
    systemd-analyze verify /etc/systemd/system/inputplumber.service.d/restart.conf 2>/dev/null || true
    systemctl is-enabled --quiet seatd.service || die 'seatd.service is not enabled'
    systemctl is-enabled --quiet inputplumber.service || die 'inputplumber.service is not enabled'
    [[ -L /etc/systemd/system/multi-user.target.wants/lulu.target ]] || die 'lulu.target is not enabled at boot'
    systemctl is-active --quiet inputplumber.service || die 'inputplumber.service is not active'
    [[ -f /etc/inputplumber/devices.d/lulu-composite.yaml ]] || die 'InputPlumber device configuration is missing'
    [[ -f /etc/lulu/presentation.conf ]] || die 'presentation configuration is missing'
    local connector
    connector="$(sed -n 's/^LULU_OUTPUT_CONNECTOR=//p' /etc/lulu/presentation.conf | tr -d '"' | tail -n 1)"
    if [[ -n "$connector" ]]; then
        status_path="$(compgen -G "/sys/class/drm/card*-$connector/status" | head -n 1 || true)"
        [[ -n "$status_path" && "$(<"$status_path")" == connected ]] || die "configured connector is not connected: $connector"
    else
        mapfile -t connectors < <(for status in /sys/class/drm/card*-*/status; do [[ -f "$status" && "$(<"$status")" == connected ]] && basename "$(dirname "$status")" | cut -d- -f2-; done | sort -u)
        ((${#connectors[@]} == 1)) || die "expected one connected DRM output, found: ${connectors[*]:-none}"
        connector=${connectors[0]}
    fi
    log "presentation connector: $connector"
    [[ -d /run/user/958 && -S /run/user/958/bus ]] || die 'lulu user runtime bus is unavailable'
    runuser -u lulu -- env XDG_RUNTIME_DIR=/run/user/958 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/958/bus busctl --user list >/dev/null || die 'lulu user D-Bus is unusable'
    systemctl is-active --quiet lulu-consoled.service || die 'lulu-consoled.service is not active'
    systemctl is-active --quiet lulu-session@2.service || die 'lulu-session@2.service is not active'
    runuser -u lulu -- env XDG_RUNTIME_DIR=/run/user/958 systemctl --user is-active --quiet pipewire.service wireplumber.service || die 'PipeWire/WirePlumber user services are not active'
    python - <<'PY'
import ast
from pathlib import Path
for path in Path('/opt/lulu/current/lib').rglob('*.py'):
    ast.parse(path.read_text(), filename=str(path))
PY
    local binary
    for binary in /opt/lulu/current/bin/lulu-shell /opt/lulu/current/bin/mudos-guide; do
        ldd "$binary" | grep -q 'not found' && die "native dependency is missing: $binary"
    done
    log 'static installation verification passed'
}

install_packages() {
    local package
    local missing_repo_packages=()
    for package in "${PACKAGES[@]}"; do
        if ! pacman -Q "$package" >/dev/null 2>&1 && ! pacman -Si "$package" >/dev/null 2>&1; then
            missing_repo_packages+=("$package")
        fi
    done
    ((${#missing_repo_packages[@]} == 0)) || die "required packages are unavailable from configured repositories: ${missing_repo_packages[*]}"
    pacman -S --needed --noconfirm "${PACKAGES[@]}"

    if ! pacman -Q rapidyaml >/dev/null 2>&1 || ! pacman -Q python-rapidyaml >/dev/null 2>&1; then
        if pacman -Si rapidyaml >/dev/null 2>&1 && pacman -Si python-rapidyaml >/dev/null 2>&1; then
            pacman -S --needed --noconfirm rapidyaml python-rapidyaml
        else
            build_payload_packages rapidyaml rapidyaml python-rapidyaml
        fi
    fi
    if ! pacman -Q pcsx2 >/dev/null 2>&1; then
        if pacman -Si pcsx2 >/dev/null 2>&1; then
            pacman -S --needed --noconfirm pcsx2
        else
            build_payload_packages pcsx2 pcsx2
        fi
    fi
    if ! pacman -Q ttf-zalando-sans >/dev/null 2>&1; then
        if pacman -Si ttf-zalando-sans >/dev/null 2>&1; then
            pacman -S --needed --noconfirm ttf-zalando-sans
        else
            build_payload_packages ttf-zalando-sans ttf-zalando-sans
        fi
    fi
}

build_payload_packages() {
    local source_dir="$1"
    local package_name
    shift
    [[ -f "$PAYLOAD/packages/$source_dir/PKGBUILD" ]] || die "$source_dir is unavailable and its payload PKGBUILD is missing"
    local build_user=${SUDO_USER:-}
    [[ -n "$build_user" && "$build_user" != root ]] || die "building $source_dir requires invoking the installer through sudo from a non-root user"
    pacman -S --needed --noconfirm base-devel
    local build_dir
    build_dir="$(mktemp -d "/var/tmp/mudos-${source_dir}.XXXXXX")"
    chown "$build_user:$build_user" "$build_dir"
    cp -a "$PAYLOAD/packages/$source_dir/." "$build_dir/"
    chown -R "$build_user:$build_user" "$build_dir"
    runuser -u "$build_user" -- makepkg --syncdeps --noconfirm --needed --dir "$build_dir"
    for package_name in "$@"; do
        local package_file
        package_file="$(find "$build_dir" -maxdepth 1 -type f -name "${package_name}-*.pkg.tar.*" -print -quit)"
        [[ -n "$package_file" ]] || die "$source_dir PKGBUILD did not produce $package_name"
        pacman -U --needed --noconfirm "$package_file"
    done
    rm -rf "$build_dir"
}

ensure_user() {
    local group
    if getent passwd lulu >/dev/null; then
        [[ "$(id -u lulu)" == 958 ]] || die 'existing lulu user does not have UID 958'
        [[ "$(id -g lulu)" == 958 ]] || die 'existing lulu primary group does not have GID 958'
        getent group lulu >/dev/null || die 'existing lulu user has no lulu group'
        [[ "$(getent group lulu | cut -d: -f3)" == 958 ]] || die 'existing lulu group does not have GID 958'
    else
        getent passwd 958 >/dev/null && die 'UID 958 is already assigned to another user'
        getent group 958 >/dev/null && die 'GID 958 is already assigned to another group'
        groupadd --gid 958 lulu
        useradd --uid 958 --gid 958 --create-home --home-dir /home/lulu --shell /bin/bash lulu
    fi
    install -d -o lulu -g lulu -m 0755 /home/lulu
    usermod --home /home/lulu --shell /bin/bash lulu
    getent group seat >/dev/null || groupadd seat
    getent group inputplumber >/dev/null || groupadd --system inputplumber
    usermod --append --groups seat,inputplumber lulu
    loginctl enable-linger lulu
    for group in lulu seat inputplumber; do getent group "$group" >/dev/null || die "missing group: $group"; done
}

migrate_user_state() {
    local source=/var/lib/lulu destination mapping relative
    [[ -e "$source" && ! -L "$source" ]] || return 0
    for mapping in ".config:/home/lulu/.config" ".local:/home/lulu/.local" ".cache:/home/lulu/.cache" \
        "roms:/home/lulu/Games/ROMs" "bios:/home/lulu/Games/BIOS" \
        "recordings:/home/lulu/Recordings" "captures:/home/lulu/Screenshots" \
        "assets:/home/lulu/.local/share/lulu/assets" "providers:/home/lulu/.config/lulu/providers" \
        "state:/home/lulu/.local/share/lulu/state" "runtime:/home/lulu/.local/share/lulu/runtime" \
        "cache:/home/lulu/.cache/lulu"; do
        relative="${mapping%%:*}"
        destination="${mapping#*:}"
        if [[ -e "$source/$relative" ]]; then
            install -d -o lulu -g lulu -m 0755 "$destination"
            cp -a "$source/$relative/." "$destination/"
            rm -rf "$source/$relative"
        fi
    done
    for item in .bashrc .bash_profile .bash_logout .zshrc .pki .steam .pulse-cookie .Xauthority; do
        if [[ -e "$source/$item" || -L "$source/$item" ]]; then
            cp -a "$source/$item" /home/lulu/
            rm -rf "$source/$item"
        fi
    done
    ln -sfn /home/lulu/.local/share/Steam/ubuntu12_32 /home/lulu/.steam/bin32
    ln -sfn /home/lulu/.local/share/Steam/ubuntu12_64 /home/lulu/.steam/bin64
    ln -sfn /home/lulu/.steam/bin32 /home/lulu/.steam/bin
    ln -sfn /home/lulu/.local/share/Steam /home/lulu/.steam/root
    ln -sfn /home/lulu/.local/share/Steam/linux32 /home/lulu/.steam/sdk32
    ln -sfn /home/lulu/.local/share/Steam/linux64 /home/lulu/.steam/sdk64
    ln -sfn /home/lulu/.local/share/Steam /home/lulu/.steam/steam
    ln -sfn /home/lulu/.steam/sdk32/steam /home/lulu/.steampath
    ln -sfn /home/lulu/.steam/steam.pid /home/lulu/.steampid
    find "$source" -depth -type d -empty -delete
    if [[ -d "$source" ]] && [[ -z "$(find "$source" -mindepth 1 -print -quit)" ]]; then
        rmdir "$source"
    fi
}

normalize_legacy_paths() {
    local link target file
    while IFS= read -r -d '' file; do
        sed -i 's#/var/lib/lulu#/home/lulu#g' "$file"
    done < <(find /home/lulu/.config /home/lulu/.local/share/lulu -type f -size -50M -print0 2>/dev/null | xargs -0 -r grep -IlZ '/var/lib/lulu')
    while IFS= read -r -d '' link; do
        target="$(readlink "$link")"
        if [[ "$target" == *'/var/lib/lulu'* ]]; then
            ln -sfn "${target//\/var\/lib\/lulu/\/home\/lulu}" "$link"
        fi
    done < <(find /home/lulu -type l -print0 2>/dev/null)
    if [[ -d /var/lib/lulu && ! -L /var/lib/lulu ]]; then
        find /var/lib/lulu -depth -type d -empty -delete
        rmdir /var/lib/lulu 2>/dev/null || true
    fi
}

install_tree() {
    install -d -m 0755 /opt/lulu/releases /etc/lulu /etc/inputplumber/devices.d
    for path in \
        /home/lulu /home/lulu/Games/ROMs /home/lulu/Games/ROMs/nes \
        /home/lulu/Games/ROMs/genesis /home/lulu/Games/ROMs/ps2 /home/lulu/Games/ROMs/wii \
        /home/lulu/Games/ROMs/switch /home/lulu/Games/BIOS /home/lulu/Games/BIOS/ps2 \
        /home/lulu/Games/BIOS/switch /home/lulu/Games/BIOS/switch/keys \
        /home/lulu/Games/BIOS/switch/firmware /home/lulu/.config \
        /home/lulu/.cache /home/lulu/.local/share /home/lulu/Recordings \
        /home/lulu/Replays /home/lulu/Screenshots /run/lulu; do
        install -d -m 0755 "$path"
    done
    chown -R lulu:lulu /home/lulu /run/lulu

    local digest release release_dir tmp link
    digest="$(sha256sum "$PAYLOAD/manifest.sha256" | cut -c1-12)"
    release="${VERSION}-${digest}"
    release_dir="/opt/lulu/releases/$release"
    if [[ ! -d "$release_dir" ]]; then
        tmp="$(mktemp -d /opt/lulu/releases/.staging.XXXXXX)"
        cp -a "$PAYLOAD/." "$tmp/"
        printf 'commit=%s\ntag=%s\nmanifest=%s\n' "$VERSION" "$VERSION_TAG" "$digest" > "$tmp/RELEASE"
        chmod -R u+rwX,go+rX "$tmp"
        mv "$tmp" "$release_dir"
    fi
    if [[ "$(readlink /opt/lulu/current 2>/dev/null || true)" != "releases/$release" ]]; then
        link="/opt/lulu/current.new.$$"
        ln -s "releases/$release" "$link"
        mv -Tf "$link" /opt/lulu/current
        RELEASE_CHANGED=1
    fi

    for path in lib bin config ui scripts; do
        local stable="/opt/lulu/$path"
        if [[ -e "$stable" && ! -L "$stable" ]]; then
            mv "$stable" "/opt/lulu/$path.legacy.$(date +%s)"
        fi
        ln -sfn "current/$path" "$stable"
    done
    chown -R root:root "$release_dir"
}

install_system_state() {
    local source destination
    for source in lulu.target lulu-session@.service lulu-consoled.service; do
        destination="/etc/systemd/system/$source"
        if ! cmp -s "$PAYLOAD/packaging/$source" "$destination" 2>/dev/null; then
            install -m 0644 "$PAYLOAD/packaging/$source" "$destination"
            SYSTEM_CHANGED=1
        fi
    done
    if ! cmp -s "$PAYLOAD/packaging/lulu-session.pam" /etc/pam.d/lulu-session 2>/dev/null; then
        install -m 0644 "$PAYLOAD/packaging/lulu-session.pam" /etc/pam.d/lulu-session
        SYSTEM_CHANGED=1
    fi
    install -d -m 0755 /etc/systemd/system/inputplumber.service.d
    if ! cmp -s "$PAYLOAD/packaging/inputplumber-restart.conf" /etc/systemd/system/inputplumber.service.d/restart.conf 2>/dev/null; then
        install -m 0644 "$PAYLOAD/packaging/inputplumber-restart.conf" /etc/systemd/system/inputplumber.service.d/restart.conf
        SYSTEM_CHANGED=1
    fi
    if ! cmp -s "$PAYLOAD/config/inputplumber/devices/lulu-composite.yaml" /etc/inputplumber/devices.d/lulu-composite.yaml 2>/dev/null; then
        install -m 0644 "$PAYLOAD/config/inputplumber/devices/lulu-composite.yaml" /etc/inputplumber/devices.d/lulu-composite.yaml
        INPUT_CHANGED=1
    fi
    if [[ ! -e /etc/lulu/presentation.conf ]]; then
        install -m 0644 "$PAYLOAD/packaging/presentation.conf" /etc/lulu/presentation.conf
        SYSTEM_CHANGED=1
    fi
    install -d -o lulu -g lulu -m 0700 /home/lulu/.config/pipewire/pipewire-pulse.conf.d
    if ! cmp -s "$PAYLOAD/packaging/pipewire/lulu-fallback-input.conf" /home/lulu/.config/pipewire/pipewire-pulse.conf.d/lulu-fallback-input.conf 2>/dev/null; then
        install -o lulu -g lulu -m 0644 "$PAYLOAD/packaging/pipewire/lulu-fallback-input.conf" /home/lulu/.config/pipewire/pipewire-pulse.conf.d/lulu-fallback-input.conf
        SYSTEM_CHANGED=1
    fi
    if ! cmp -s "$PAYLOAD/bin/verify-mudos.sh" /opt/lulu/current/bin/verify-mudos.sh 2>/dev/null; then
        install -m 0755 "$PAYLOAD/bin/verify-mudos.sh" /opt/lulu/current/bin/verify-mudos.sh
        RELEASE_CHANGED=1
    fi
    if (( SYSTEM_CHANGED || INPUT_CHANGED )); then systemctl daemon-reload; fi
    systemd-analyze verify /etc/systemd/system/lulu.target /etc/systemd/system/lulu-session@.service /etc/systemd/system/lulu-consoled.service
}

enable_services() {
    systemctl enable seatd.service inputplumber.service
    mkdir -p /etc/systemd/system/multi-user.target.wants
    ln -sfn /etc/systemd/system/lulu.target /etc/systemd/system/multi-user.target.wants/lulu.target
    systemctl start seatd.service inputplumber.service user-runtime-dir@958.service user@958.service
    systemctl try-restart user@958.service
    systemctl start lulu.target
    if (( RELEASE_CHANGED || SYSTEM_CHANGED )); then
        systemctl try-restart lulu-consoled.service lulu-session@2.service
    fi
}

if (( VERIFY_ONLY )); then
    step 'Checking installed host' 1
    require_file "$SCRIPT_DIR/CHECKPOINT"
    load_checkpoint
    verify_installed
    exit 0
fi

step 'Checking host and USB payload' 1
verify_payload
[[ -f /etc/os-release ]] || die 'missing /etc/os-release'
grep -Eq '^(ID|ID_LIKE)=.*(cachyos|arch)' /etc/os-release || die 'this installer requires CachyOS or an Arch-derived host'
command -v pacman >/dev/null || die 'pacman is required'

step 'Installing packages' 2
install_packages

step 'Creating users and groups' 3
ensure_user
migrate_user_state
normalize_legacy_paths

step 'Creating filesystem state' 4
install_tree

step 'Deploying complete Mudos release' 5
[[ -f /opt/lulu/current/RELEASE ]] || die 'release marker was not installed'

step 'Installing systemd and session state' 6
install_system_state

step 'Installing InputPlumber configuration' 7
if (( INPUT_CHANGED )); then
    systemctl restart inputplumber.service
else
    systemctl start inputplumber.service
fi

step 'Verifying udev and permissions' 8
if pacman -Ql steam-devices | grep -Eq '/(udev/rules.d|modprobe.d)/'; then
    udevadm control --reload-rules
    if (( INPUT_CHANGED )); then udevadm trigger --subsystem-match=input; fi
else
    die 'steam-devices did not install device permission rules'
fi
getent group seat >/dev/null

step 'Installing Gamescope and provider prerequisites' 9
python -m compileall -q /opt/lulu/current/lib
command -v dolphin-emu >/dev/null
command -v pcsx2 >/dev/null
command -v retroarch >/dev/null

step 'Enabling services and final verification' 10
enable_services
verify_installed
log "installation complete: ${VERSION_TAG} (${VERSION})"
log 'Reboot before performing first-boot hardware acceptance.'
