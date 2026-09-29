#!/usr/bin/env bash
set -euo pipefail

repo_root=${LULU_SOURCE_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
package_root="$repo_root/packages/questarr"
lock="$package_root/IMAGE.lock"
source_commit=$(sed -n 's/^upstream_git_commit=//p' "$lock")
upstream_image=$(sed -n 's/^upstream_image=//p' "$lock")
node_image=$(sed -n 's/^node_build_image=//p' "$lock")
expected_image_id=$(sed -n 's/^image_id=//p' "$lock")
recipe_commit=$(sed -n 's/^build_recipe_commit=//p' "$lock")
patch_file=$(sed -n 's/^patch=//p' "$lock")
patch_sha=$(sed -n 's/^patch_sha256=//p' "$lock")
record_image_id=${LULU_QUESTARR_RECORD_IMAGE_ID:-0}
build_root=${LULU_QUESTARR_BUILD_ROOT:-/var/lib/lulu-questarr/build/questarr-v1.4.2-mudos1}
source_root="$build_root/source"
tag=localhost/mudos-questarr:1.4.2-mudos1

[[ $source_commit =~ ^[0-9a-f]{40}$ ]] || {
  echo "Questarr image lock is incomplete or malformed." >&2
  exit 78
}
[[ $patch_sha =~ ^[0-9a-f]{64}$ ]] && \
  echo "$patch_sha  $package_root/patches/$patch_file" | sha256sum --check --status || {
  echo "Questarr downstream patch hash does not match IMAGE.lock." >&2
  exit 78
}
if [[ $record_image_id == 1 ]]; then
  [[ $expected_image_id == TO_BE_BUILT && $recipe_commit == TO_BE_BUILT ]] || {
    echo "Refusing to replace an existing pinned Questarr image id." >&2
    exit 78
  }
  recipe_commit=$(git -C "$repo_root" rev-parse HEAD)
  [[ -z $(git -C "$repo_root" status --porcelain) ]] || {
    echo "Refusing to build/pin Questarr from a dirty Mudos checkout." >&2
    exit 78
  }
else
  [[ $expected_image_id =~ ^sha256:[0-9a-f]{64}$ ]] || {
    echo "Questarr image lock lacks a pinned image id." >&2
    exit 78
  }
  [[ $recipe_commit =~ ^[0-9a-f]{40}$ ]] || {
    echo "Questarr image lock lacks its Mudos build recipe commit." >&2
    exit 78
  }
fi
mkdir -p "$build_root"
if [[ ! -d "$source_root/.git" ]]; then
  git clone --filter=blob:none --no-checkout https://github.com/Doezer/Questarr.git "$source_root"
fi
git -C "$source_root" fetch --depth=1 origin "$source_commit"
git -C "$source_root" checkout --detach "$source_commit"
git -C "$source_root" show "$source_commit:server/downloaders/nzbget.ts" \
  > "$source_root/server/downloaders/nzbget.ts"
rm -f "$source_root/server/nzbget-destdir.spec.ts" "$source_root/server/nzbget-destdir.test.ts"
[[ $(git -C "$source_root" rev-parse HEAD) == "$source_commit" ]] || {
  echo "Questarr source checkout does not match IMAGE.lock." >&2
  exit 78
}
[[ -z $(git -C "$source_root" status --porcelain) ]] || {
  echo "Questarr source checkout is not pristine before applying the downstream patch." >&2
  exit 78
}
git -C "$source_root" apply "$package_root/patches/$patch_file"
install -m 0644 "$package_root/tests/nzbget-destdir.spec.ts" \
  "$source_root/server/nzbget-destdir.spec.ts"

source_epoch=$(git -C "$source_root" show -s --format=%ct "$source_commit")
podman pull "$node_image"
podman build --pull=never --no-cache --timestamp "$source_epoch" \
  --build-arg "NODE_BUILD_IMAGE=$node_image" \
  --build-arg "UPSTREAM_IMAGE=$upstream_image" \
  --build-arg "MUDOS_PATCH_SHA256=$patch_sha" \
  --build-arg "MUDOS_BUILD_RECIPE_COMMIT=$recipe_commit" \
  --tag "$tag" \
  --file "$package_root/Containerfile" "$source_root"

actual_image_id=$(podman image inspect --format '{{.Id}}' "$tag")
if [[ $record_image_id == 1 ]]; then
  sed -e "s/^build_recipe_commit=TO_BE_BUILT$/build_recipe_commit=$recipe_commit/" \
      -e "s/^image_id=TO_BE_BUILT$/image_id=$actual_image_id/" "$lock" > "$lock.new"
  chmod --reference="$lock" "$lock.new"
  chown --reference="$lock" "$lock.new"
  mv "$lock.new" "$lock"
else
  [[ $actual_image_id == "$expected_image_id" ]] || {
    echo "Built Questarr image id $actual_image_id differs from IMAGE.lock $expected_image_id." >&2
    exit 78
  }
fi

data_root=${LULU_QUESTARR_DATA_ROOT:-/var/lib/lulu-questarr}
install -d -o root -g root -m 0755 "$data_root"
printf '%s\n' "$actual_image_id" > "$data_root/questarr-image-ref.new"
chmod 0644 "$data_root/questarr-image-ref.new"
mv -f "$data_root/questarr-image-ref.new" "$data_root/questarr-image-ref"
printf 'Questarr image pinned: %s (%s)\n' "$actual_image_id" "$tag"
