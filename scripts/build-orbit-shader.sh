#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
orbit_wave_frag=${ORBIT_WAVE_FRAG:-}
output=${1:-"$repo_root/ui/shaders/orbit-wave.frag.qsb"}

if [ -z "$orbit_wave_frag" ] || [ ! -f "$orbit_wave_frag" ]; then
    printf '%s\n' "ORBIT_WAVE_FRAG must point to Orbit's upstream wave.frag" >&2
    exit 2
fi

temporary=$(mktemp "${TMPDIR:-/tmp}/lulu-orbit-wave.XXXXXX.frag")
trap 'rm -f "$temporary"' EXIT HUP INT TERM
python3 "$repo_root/scripts/build-orbit-qsb.py" "$orbit_wave_frag" "$temporary"
mkdir -p "$(dirname -- "$output")"
/usr/lib/qt6/bin/qsb --qt6 --batchable -o "$output" "$temporary"
