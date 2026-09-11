#!/usr/bin/env bash
set -Eeuo pipefail

root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
payload=$root/deploy/payload
commit=${1:?usage: refresh-payload.sh COMMIT TAG}
tag=${2:?usage: refresh-payload.sh COMMIT TAG}

[[ $commit =~ ^[0-9a-fA-F]{7,40}$ ]] || { printf 'invalid commit: %s\n' "$commit" >&2; exit 1; }
[[ -n $tag && $tag != *$'\n'* ]] || { printf 'invalid tag\n' >&2; exit 1; }
[[ -x $payload/scripts/steam-session-bootstrap.sh && -x $payload/scripts/steam-bootstrap.sh ]] || {
    printf 'Steam bootstrap payload is incomplete\n' >&2
    exit 1
}

while IFS= read -r -d '' path; do
    case "$path" in
        */__pycache__/*|*.pyc|*/.cache/*) printf 'generated state in payload: %s\n' "$path" >&2; exit 1 ;;
    esac
done < <(find "$payload" -type f ! -name manifest.sha256 -print0)

(cd "$payload" && find . -type f ! -name manifest.sha256 -print0 | sort -z | xargs -0 sha256sum > manifest.sha256)
manifest=$(sha256sum "$payload/manifest.sha256" | cut -c1-12)
printf 'commit=%s\ntag=%s\ngenerated=%s\n' "$commit" "$tag" "$(date -u +%Y%m%d)" > "$root/deploy/CHECKPOINT"
