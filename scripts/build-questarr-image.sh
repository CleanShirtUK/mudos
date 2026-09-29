#!/usr/bin/env bash
set -euo pipefail

repo_root=${LULU_SOURCE_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
package_root="$repo_root/packages/questarr"
lock="$package_root/IMAGE.lock"
source_commit=$(sed -n 's/^upstream_git_commit=//p' "$lock")
upstream_image=$(sed -n 's/^upstream_image=//p' "$lock")
upstream_digest=${upstream_image##*@}
node_image=$(sed -n 's/^node_build_image=//p' "$lock")
expected_image_id=$(sed -n 's/^image_id=//p' "$lock")
expected_image_digest=$(sed -n 's/^image_digest=//p' "$lock")
recipe_commit=$(sed -n 's/^build_recipe_commit=//p' "$lock")
patch_file=$(sed -n 's/^patch=//p' "$lock")
patch_sha=$(sed -n 's/^patch_sha256=//p' "$lock")
record_image_id=${LULU_QUESTARR_RECORD_IMAGE_ID:-0}
pin_existing=${LULU_QUESTARR_PIN_EXISTING:-0}
build_root=${LULU_QUESTARR_BUILD_ROOT:-/var/lib/lulu-questarr/build/questarr-v1.4.2-mudos1}
source_root="$build_root/source"
image_repository=localhost/mudos-questarr
tag="$image_repository:1.4.2-mudos1"

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
  [[ $expected_image_id == TO_BE_BUILT && $expected_image_digest == TO_BE_BUILT \
     && $recipe_commit == TO_BE_BUILT ]] || {
    echo "Refusing to replace an existing pinned Questarr image id." >&2
    exit 78
  }
  recipe_commit=$(git -C "$repo_root" rev-parse HEAD)
  [[ -z $(git -C "$repo_root" status --porcelain) ]] || {
    echo "Refusing to build/pin Questarr from a dirty Mudos checkout." >&2
    exit 78
  }
else
  [[ $expected_image_id =~ ^[0-9a-f]{64}$ ]] || {
    echo "Questarr image lock lacks a pinned image id." >&2
    exit 78
  }
  [[ $expected_image_digest =~ ^sha256:[0-9a-f]{64}$ ]] || {
    echo "Questarr image lock lacks its pinned manifest digest." >&2
    exit 78
  }
  [[ $recipe_commit =~ ^[0-9a-f]{40}$ ]] || {
    echo "Questarr image lock lacks its Mudos build recipe commit." >&2
    exit 78
  }
fi

persist_image_pin() {
  local image_digest=$1
  data_root=${LULU_QUESTARR_DATA_ROOT:-/var/lib/lulu-questarr}
  install -d -o root -g root -m 0755 "$data_root"
  printf '%s@%s\n' "$image_repository" "$image_digest" > "$data_root/questarr-image-ref.new"
  chmod 0644 "$data_root/questarr-image-ref.new"
  mv -f "$data_root/questarr-image-ref.new" "$data_root/questarr-image-ref"
}

if [[ $pin_existing == 1 ]]; then
  immutable_ref="$image_repository@$expected_image_digest"
  actual_image_id=$(podman image inspect --format '{{.Id}}' "$immutable_ref")
  actual_image_digest=$(podman image inspect --format '{{.Digest}}' "$immutable_ref")
  recipe_label=$(podman image inspect --format '{{ index .Config.Labels "org.mudos.questarr.build-recipe-commit" }}' "$immutable_ref")
  patch_label=$(podman image inspect --format '{{ index .Config.Labels "org.mudos.questarr.patch.sha256" }}' "$immutable_ref")
  base_label=$(podman image inspect --format '{{ index .Config.Labels "org.opencontainers.image.base.digest" }}' "$immutable_ref")
  source_label=$(podman image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$immutable_ref")
  [[ $actual_image_id == "$expected_image_id" && $actual_image_digest == "$expected_image_digest" \
     && $recipe_label == "$recipe_commit" && $patch_label == "$patch_sha" \
      && $base_label == "$upstream_digest" && $source_label == "$source_commit" ]] || {
    echo "Existing Questarr image failed pin/provenance verification." >&2
    exit 78
  }
  persist_image_pin "$actual_image_digest"
  printf 'Questarr image pinned: %s@%s (image id %s)\n' "$image_repository" "$actual_image_digest" "$actual_image_id"
  exit 0
fi

mkdir -p "$build_root"
if [[ ! -d "$source_root/.git" ]]; then
  git clone --filter=blob:none --no-checkout https://github.com/Doezer/Questarr.git "$source_root"
fi
git -C "$source_root" fetch --depth=1 origin "$source_commit"
git -C "$source_root" checkout --detach "$source_commit"
git -C "$source_root" show "$source_commit:server/downloaders/nzbget.ts" \
  > "$source_root/server/downloaders/nzbget.ts"
rm -f "$source_root/server/nzbget-destdir.spec.ts" \
  "$source_root/server/nzbget-destdir.test.ts" \
  "$source_root/server/__tests__/nzbget-destdir.test.ts"
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
printf '!vitest.config.ts\n' >> "$source_root/.dockerignore"

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
actual_image_digest=$(podman image inspect --format '{{.Digest}}' "$tag")
[[ $actual_image_digest =~ ^sha256:[0-9a-f]{64}$ ]] || {
  echo "Built Questarr image has no usable manifest digest." >&2
  exit 78
}
if [[ $record_image_id == 1 ]]; then
  sed -e "s/^build_recipe_commit=TO_BE_BUILT$/build_recipe_commit=$recipe_commit/" \
      -e "s/^image_id=TO_BE_BUILT$/image_id=$actual_image_id/" \
      -e "s/^image_digest=TO_BE_BUILT$/image_digest=$actual_image_digest/" \
      "$lock" > "$lock.new"
  chmod --reference="$lock" "$lock.new"
  chown --reference="$lock" "$lock.new"
  mv "$lock.new" "$lock"
else
  [[ $actual_image_id == "$expected_image_id" ]] || {
    echo "Built Questarr image id $actual_image_id differs from IMAGE.lock $expected_image_id." >&2
    exit 78
  }
  [[ $actual_image_digest == "$expected_image_digest" ]] || {
    echo "Built Questarr manifest digest $actual_image_digest differs from IMAGE.lock $expected_image_digest." >&2
    exit 78
  }
fi

persist_image_pin "$actual_image_digest"
printf 'Questarr image pinned: %s@%s (image id %s)\n' "$image_repository" "$actual_image_digest" "$actual_image_id"
