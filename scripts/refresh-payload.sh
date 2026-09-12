#!/usr/bin/env bash
set -Eeuo pipefail

root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
payload=$root/deploy/payload
commit=${1:?usage: refresh-payload.sh COMMIT TAG}
tag=${2:?usage: refresh-payload.sh COMMIT TAG}

[[ $commit =~ ^[0-9a-fA-F]{7,40}$ ]] || { printf 'invalid commit: %s\n' "$commit" >&2; exit 1; }
[[ -n $tag && $tag != *$'\n'* ]] || { printf 'invalid tag\n' >&2; exit 1; }
actual_commit=$(git -C "$root" rev-parse HEAD)
[[ "$actual_commit" == "$commit" ]] || { printf 'source checkout is not commit %s (found %s)\n' "$commit" "$actual_commit" >&2; exit 1; }
printf '[PAYLOAD] source=%s commit=%s payload=%s\n' "$root" "$actual_commit" "$payload"
git -C "$root" clean -fdx -- "$payload"
[[ -x $payload/scripts/steam-session-bootstrap.sh && -x $payload/scripts/steam-bootstrap.sh ]] || {
    printf 'Steam bootstrap payload is incomplete\n' >&2
    exit 1
}

# Keep component contracts in the payload identical to the authoritative UI.
cp "$root"/ui/*.qml "$payload/ui/"
mkdir -p "$payload/ui/artwork"
cp -a "$root"/ui/artwork/. "$payload/ui/artwork/"
mkdir -p "$payload/ui/sounds"
cp -a "$root"/ui/sounds/. "$payload/ui/sounds/"
cp "$root"/src/lulu/consoled.py "$root"/src/lulu/console_sessiond.py "$root"/src/lulu/process_supervisor.py \
   "$root"/src/lulu/sessiond.py "$root"/src/lulu/steam_provider.py "$root"/src/lulu/system_settings.py "$root"/src/lulu/gamescope.py \
   "$root"/src/lulu/inputplumber.py "$root"/src/lulu/contracts.py "$root"/src/lulu/controllerd.py \
   "$root"/src/lulu/emulation.py "$root"/src/lulu/emulator_runtime.py "$root"/src/lulu/local_content.py \
   "$root"/src/lulu/controller_provisioning.py "$root"/src/lulu/switch_provider.py "$root"/src/lulu/paths.py \
   "$root"/src/lulu/catalogue.py "$root"/src/lulu/artwork.py "$root"/src/lulu/metadata.py "$payload/lib/lulu/"
cp "$root"/scripts/console-ui-bridge.py "$payload/scripts/console-ui-bridge.py"
cp "$root"/scripts/console-ui.sh "$payload/scripts/console-ui.sh"
cp "$root"/scripts/steam-bootstrap.sh "$payload/scripts/steam-bootstrap.sh"
cp "$root"/packaging/lulu-session@.service "$payload/packaging/lulu-session@.service"
cp "$root"/packaging/lulu-consoled.service "$payload/packaging/lulu-consoled.service"
cp "$root"/config/inputplumber/profiles/*.yaml "$payload/config/inputplumber/profiles/"
printf '[PAYLOAD] binaries=preserved-from-tracked-payload\n'

while IFS= read -r -d '' path; do
    case "$path" in
        */__pycache__/*|*.pyc|*/.cache/*) printf 'generated state in payload: %s\n' "$path" >&2; exit 1 ;;
    esac
done < <(find "$payload" -type f ! -name manifest.sha256 -print0)

(cd "$payload" && find . -type f ! -name manifest.sha256 -print0 | sort -z | xargs -0 sha256sum > manifest.sha256)
manifest=$(sha256sum "$payload/manifest.sha256" | cut -c1-12)
printf '[PAYLOAD] manifest=%s files=%s\n' "$manifest" "$(find "$payload" -type f ! -name manifest.sha256 | wc -l)"
printf 'commit=%s\ntag=%s\ngenerated=%s\n' "$commit" "$tag" "$(date -u +%Y%m%d)" > "$root/deploy/CHECKPOINT"
