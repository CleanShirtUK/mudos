#!/usr/bin/env bash
set -Eeuo pipefail

readonly INSTALL_ROOT=/opt/lulu/current
readonly VERSION=7c96e06
readonly VERSION_TAG=known-good-test-environment-20260910
HARDWARE=0
PAYLOAD=''

fail() { printf '[verify] FAIL: %s\n' "$*" >&2; exit 1; }
pass() { printf '[verify] ok: %s\n' "$*"; }
while (($#)); do
    case "$1" in
        --hardware) HARDWARE=1 ;;
        --payload) shift; PAYLOAD=${1:?payload path is required} ;;
        *) fail "unknown argument: $1" ;;
    esac
    shift
done

[[ $EUID -eq 0 ]] || fail 'run as root'
id lulu >/dev/null 2>&1 || fail 'lulu user is missing'
[[ "$(id -u lulu)" == 958 && "$(id -g lulu)" == 958 ]] || fail 'lulu UID/GID is not 958'
getent group seat >/dev/null || fail 'seat group is missing'
[[ -L "$INSTALL_ROOT" && -f "$INSTALL_ROOT/RELEASE" ]] || fail 'versioned Mudos release is missing'

for path in lib/lulu bin/lulu-shell bin/mudos-guide bin/lulu-vt ui config scripts; do
    [[ -e "$INSTALL_ROOT/$path" ]] || fail "missing installed path: $path"
done
grep -Fxq "commit=${VERSION}" "$INSTALL_ROOT/RELEASE" || fail 'release commit mismatch'
grep -Fxq "tag=${VERSION_TAG}" "$INSTALL_ROOT/RELEASE" || fail 'release tag mismatch'
for executable in python dolphin-emu pcsx2 pcsx2-qt retroarch gamescope busctl systemctl; do
    command -v "$executable" >/dev/null || fail "missing executable: $executable"
done
for package in inputplumber gamescope-git dolphin-emu retroarch libretro-nestopia libretro-genesis-plus-gx steam steam-devices seatd pipewire wireplumber qt6-base qt6-declarative sdl3 python python-dbus-next python-rapidyaml rapidyaml ttf-zalando-sans; do
    pacman -Q "$package" >/dev/null 2>&1 || fail "missing package: $package"
done
for file in lulu.target lulu-session@.service lulu-consoled.service; do
    systemd-analyze verify "/etc/systemd/system/$file" || fail "invalid unit: $file"
done
systemctl is-enabled --quiet seatd.service || fail 'seatd is not enabled'
systemctl is-enabled --quiet inputplumber.service || fail 'InputPlumber is not enabled'
[[ -L /etc/systemd/system/multi-user.target.wants/lulu.target ]] || fail 'lulu target is not enabled'
systemctl is-active --quiet inputplumber.service || fail 'InputPlumber is not active'
[[ -f /etc/inputplumber/devices.d/lulu-composite.yaml ]] || fail 'InputPlumber config is missing'
[[ -f /etc/lulu/presentation.conf ]] || fail 'presentation config is missing'
pacman -Ql steam-devices | grep -Eq '/(udev/rules.d|modprobe.d)/' || fail 'steam-devices rules are missing'
[[ -f /var/lib/lulu/.config/pipewire/pipewire-pulse.conf.d/lulu-fallback-input.conf ]] || fail 'PipeWire fallback configuration is missing'
for path in /var/lib/lulu/roms/{nes,genesis,ps2,wii} /var/lib/lulu/bios/ps2; do
    [[ -d "$path" ]] || fail "missing data directory: $path"
    [[ "$(stat -c '%U:%G' "$path")" == lulu:lulu ]] || fail "wrong ownership: $path"
done
python -m compileall -q "$INSTALL_ROOT/lib" || fail 'Python bytecode compilation failed'
for binary in "$INSTALL_ROOT/bin/lulu-shell" "$INSTALL_ROOT/bin/mudos-guide"; do
    if ldd "$binary" | grep -q 'not found'; then
        fail "native dependency is missing: $binary"
    fi
done

if [[ -n "$PAYLOAD" ]]; then
    [[ -f "$PAYLOAD/manifest.sha256" ]] || fail 'payload manifest is missing'
    (cd "$PAYLOAD" && sha256sum --strict --check manifest.sha256) || fail 'payload checksum failed'
fi

if (( HARDWARE )); then
    mapfile -t composites < <(busctl get-property org.shadowblip.InputPlumber /org/shadowblip/InputPlumber/Manager org.shadowblip.InputManager GamepadOrder | grep -o '/org/shadowblip/InputPlumber/CompositeDevice[0-9]*' || true)
    ((${#composites[@]} > 0)) || fail 'no InputPlumber controller composite is present'
    for composite in "${composites[@]}"; do
        mode=$(busctl get-property org.shadowblip.InputPlumber "$composite" org.shadowblip.Input.CompositeDevice InterceptMode)
        [[ "$mode" == *' 1' ]] || fail "InterceptMode is not 1: $composite ($mode)"
        busctl get-property org.shadowblip.InputPlumber "$composite" org.shadowblip.Input.CompositeDevice DbusDevices >/dev/null || fail "D-Bus targets unavailable: $composite"
    done
    pass 'InputPlumber composites and InterceptMode=1'
fi

pass "Mudos ${VERSION_TAG} (${VERSION}) is installed"
