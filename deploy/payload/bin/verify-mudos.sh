#!/usr/bin/env bash
set -Eeuo pipefail

readonly INSTALL_ROOT=/opt/lulu/current
readonly VERSION=$(sed -n 's/^commit=//p' "$INSTALL_ROOT/RELEASE")
readonly VERSION_TAG=$(sed -n 's/^tag=//p' "$INSTALL_ROOT/RELEASE")
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
getent group inputplumber >/dev/null || fail 'inputplumber group is missing'
id -nG lulu | tr ' ' '\n' | grep -Fxq inputplumber || fail 'lulu is not in inputplumber group'
! id -nG lulu | tr ' ' '\n' | grep -Fxq wheel || fail 'lulu must not be in wheel'
[[ -L "$INSTALL_ROOT" && -f "$INSTALL_ROOT/RELEASE" ]] || fail 'versioned Mudos release is missing'
[[ "$(readlink -f "$INSTALL_ROOT")" == /opt/lulu/releases/* ]] || fail 'current does not resolve below /opt/lulu/releases'

for path in lib/lulu bin/lulu-shell bin/mudos-guide bin/mudos-desktop-theme bin/mudos-desktop-wallpaper bin/lulu-vt ui config scripts/mudos-desktop-session scripts/mudos-desktop-sessionctl scripts/mudos-desktop-settings scripts/steam-session-bootstrap.sh scripts/steam-bootstrap.sh; do
    [[ -e "$INSTALL_ROOT/$path" ]] || fail "missing installed path: $path"
done
for script in "$INSTALL_ROOT/scripts/steam-session-bootstrap.sh" "$INSTALL_ROOT/scripts/steam-bootstrap.sh"; do
    [[ -x "$script" ]] || fail "runtime script is not executable: $script"
done
grep -Fxq "commit=${VERSION}" "$INSTALL_ROOT/RELEASE" || fail 'release commit mismatch'
grep -Fxq "tag=${VERSION_TAG}" "$INSTALL_ROOT/RELEASE" || fail 'release tag mismatch'
(cd "$INSTALL_ROOT" && sha256sum --strict --check manifest.sha256) || fail 'installed payload checksum failed'
for executable in python dolphin-emu pcsx2 pcsx2-qt retroarch gamescope Xephyr xauth xdpyinfo xsetroot xprop openbox tint2 jgmenu busctl systemctl; do
    command -v "$executable" >/dev/null || fail "missing executable: $executable"
done
[[ "$(getent passwd lulu | cut -d: -f6)" == /home/lulu ]] || fail 'lulu home is not /home/lulu'
[[ "$(getent passwd lulu | cut -d: -f7)" == /bin/bash ]] || fail 'lulu shell is not /bin/bash'
[[ "$(readlink /home/user 2>/dev/null || true)" == /home/lulu ]] || fail 'Eden compatibility home link is missing'
for package in inputplumber gamescope-git dolphin-emu retroarch libretro-nestopia libretro-genesis-plus-gx steam steam-devices seatd pipewire wireplumber qt6-base qt6-declarative sdl3 xorg-server-xephyr xorg-xauth xorg-xdpyinfo xorg-xsetroot xorg-xprop openbox tint2 jgmenu python python-dbus-next python-rapidyaml rapidyaml ttf-zalando-sans; do
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
[[ -d /run/user/958 && -S /run/user/958/bus ]] || fail 'lulu runtime bus is unavailable'
runuser -u lulu -- env XDG_RUNTIME_DIR=/run/user/958 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/958/bus busctl --user list >/dev/null || fail 'lulu user D-Bus is unusable'
systemctl is-active --quiet lulu-consoled.service || fail 'lulu-consoled is not active'
systemctl is-active --quiet lulu-session@2.service || fail 'lulu-session@2 is not active'
pacman -Ql steam-devices | grep -Eq '/(udev/rules.d|modprobe.d)/' || fail 'steam-devices rules are missing'
[[ -f /home/lulu/.config/pipewire/pipewire-pulse.conf.d/lulu-fallback-input.conf ]] || fail 'PipeWire fallback configuration is missing'
for path in /home/lulu/Games/ROMs/{nes,genesis,ps2,wii} /home/lulu/Games/BIOS/ps2; do
    [[ -d "$path" ]] || fail "missing data directory: $path"
    [[ "$(stat -c '%U:%G' "$path")" == lulu:lulu ]] || fail "wrong ownership: $path"
done
python - "$INSTALL_ROOT/lib" <<'PY' || fail 'Python syntax validation failed'
import ast
import sys
from pathlib import Path
for path in Path(sys.argv[1]).rglob('*.py'):
    ast.parse(path.read_text(), filename=str(path))
PY
for binary in "$INSTALL_ROOT/bin/lulu-shell" "$INSTALL_ROOT/bin/mudos-guide" "$INSTALL_ROOT/bin/mudos-desktop-wallpaper"; do
    if ldd "$binary" | grep -q 'not found'; then
        fail "native dependency is missing: $binary"
    fi
done

if [[ -n "$PAYLOAD" ]]; then
    [[ -f "$PAYLOAD/manifest.sha256" ]] || fail 'payload manifest is missing'
    (cd "$PAYLOAD" && sha256sum --strict --check manifest.sha256) || fail 'payload checksum failed'
fi

connector=$(sed -n 's/^LULU_OUTPUT_CONNECTOR=//p' /etc/lulu/presentation.conf | tr -d '"' | tail -n 1)
if [[ -n "$connector" ]]; then
    status_path=$(compgen -G "/sys/class/drm/card*-$connector/status" | head -n 1 || true)
    [[ -n "$status_path" && "$(<"$status_path")" == connected ]] || fail "configured connector is not connected: $connector"
else
    mapfile -t outputs < <(for status in /sys/class/drm/card*-*/status; do [[ -f "$status" && "$(<"$status")" == connected ]] && basename "$(dirname "$status")" | cut -d- -f2-; done | sort -u)
    ((${#outputs[@]} == 1)) || fail "expected one connected DRM output, found: ${outputs[*]:-none}"
    connector=${outputs[0]}
fi
pass "presentation connector: $connector"

if (( HARDWARE )); then
    mapfile -t composites < <(busctl get-property org.shadowblip.InputPlumber /org/shadowblip/InputPlumber/Manager org.shadowblip.InputManager GamepadOrder | grep -o '/org/shadowblip/InputPlumber/CompositeDevice[0-9]*' || true)
    ((${#composites[@]} > 0)) || fail 'no InputPlumber controller composite is present'
    for composite in "${composites[@]}"; do
        mode=$(busctl get-property org.shadowblip.InputPlumber "$composite" org.shadowblip.Input.CompositeDevice InterceptMode)
        [[ "$mode" == *' 1' ]] || fail "InterceptMode is not 1: $composite ($mode)"
        busctl get-property org.shadowblip.InputPlumber "$composite" org.shadowblip.Input.CompositeDevice DbusDevices >/dev/null || fail "D-Bus targets unavailable: $composite"
        runuser -u lulu -- busctl set-property org.shadowblip.InputPlumber "$composite" org.shadowblip.Input.CompositeDevice InterceptMode u 1 >/dev/null || fail "lulu is not authorized for InterceptMode: $composite"
    done
    pass 'InputPlumber composites and InterceptMode=1'
fi

pass "Mudos ${VERSION_TAG} (${VERSION}) is installed"
