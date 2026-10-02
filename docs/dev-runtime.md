# Mutable development runtime

`/opt/lulu/current` and `/opt/lulu/releases` are immutable-release-only. For
dirty QML/UI validation, `scripts/dev-runtime.sh refresh` copies the canonical
checkout into `/opt/lulu/dev-current`, builds the
development binaries there, writes a `NON_PROMOTABLE` provenance marker, and
installs temporary systemd drop-ins for `lulu-session@` and `lulu-consoled`.

The marker records the source path, Git HEAD, branch, dirty state, and refresh
time. This runtime is never accepted by `scripts/release.py`, never becomes
`/opt/lulu/current`, and is not rollback authority.

Commands (run on Lulu):

```sh
sudo ./scripts/dev-runtime.sh refresh
sudo ./scripts/dev-runtime.sh immutable
```

`refresh` rebuilds the mutable runtime and restarts only the Mudos session and
Consoled. `immutable` removes the development drop-ins and restores the active
immutable release. The normal immutable release chain is not modified.
