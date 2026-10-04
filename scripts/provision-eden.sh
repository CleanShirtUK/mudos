#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
manifest="$root/config/providers/eden/runtime.json"
if [[ $(id -u) -ne 0 ]]; then
    echo "Eden AppImage provisioning requires root" >&2
    exit 1
fi

mapfile -t spec < <(python3 - "$manifest" <<'PY'
import json
import re
import sys
from pathlib import Path

value = json.loads(Path(sys.argv[1]).read_text())
if value.get("schema") != 1:
    raise SystemExit("unsupported Eden runtime manifest")
for key in ("source_commit_short", "filename", "url", "sha256"):
    if not isinstance(value.get(key), str) or not value[key]:
        raise SystemExit(f"Eden runtime manifest is missing {key}")
if not re.fullmatch(r"[0-9a-f]{10}", value["source_commit_short"]):
    raise SystemExit("invalid Eden source commit in runtime manifest")
if not re.fullmatch(r"[0-9a-f]{64}", value["sha256"]):
    raise SystemExit("invalid Eden SHA-256 in runtime manifest")
if not value["filename"].endswith(".AppImage") or not value["url"].startswith("https://"):
    raise SystemExit("Eden runtime must be an official HTTPS AppImage")
for key in ("source_commit_short", "filename", "url", "sha256"):
    print(value[key])
PY
)
commit=${spec[0]}
filename=${spec[1]}
url=${spec[2]}
expected_sha=${spec[3]}
runtime_dir="/var/lib/lulu/providers/eden/$commit"
target="$runtime_dir/$filename"

install -d -o root -g lulu -m 0750 "$runtime_dir"
if [[ -e $target ]]; then
    printf '%s  %s\n' "$expected_sha" "$target" | sha256sum --check --status || {
        echo "existing Eden AppImage does not match the pinned SHA-256: $target" >&2
        exit 1
    }
    chmod 0550 "$target"
    chown root:lulu "$target"
else
    temporary="$runtime_dir/.${filename}.$$"
    trap 'rm -f "$temporary"' EXIT
    curl --fail --location --retry 3 --retry-delay 1 --connect-timeout 20 \
        --max-time 300 "$url" --output "$temporary"
    printf '%s  %s\n' "$expected_sha" "$temporary" | sha256sum --check --status || {
        echo "downloaded Eden AppImage failed its pinned SHA-256 check" >&2
        exit 1
    }
    chmod 0550 "$temporary"
    chown root:lulu "$temporary"
    mv -- "$temporary" "$target"
    trap - EXIT
fi

# These grants were added for the old Mudos Eden Flatpak wrapper. Revoke only
# the two exact Mudos-owned paths; preserve unrelated Flatpak permissions and
# keep the generic Flatpak provider untouched.
if command -v flatpak >/dev/null 2>&1 && flatpak info --system dev.eden_emu.eden >/dev/null 2>&1; then
    flatpak override --system \
        --nofilesystem=/home/lulu/Games \
        --nofilesystem=/home/lulu/.config/lulu/providers/eden/config \
        dev.eden_emu.eden
fi

# Remove only the byte-identical wrapper installed by the retired Mudos
# Flatpak provisioner. A user-customized /usr/local/bin/eden is left untouched.
legacy_wrapper=/usr/local/bin/eden
legacy_wrapper_sha=088493a08bd67c19972ec8cfeb35825f3ebe354ec0e304e7b0d54fe61ee00969
if [[ -f $legacy_wrapper && ! -L $legacy_wrapper ]] \
        && [[ $(sha256sum "$legacy_wrapper" | cut -d ' ' -f 1) == "$legacy_wrapper_sha" ]]; then
    rm -- "$legacy_wrapper"
fi

echo "Installed pinned Eden AppImage $commit at $target"
