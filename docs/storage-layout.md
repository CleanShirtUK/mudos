# Lulu Storage Layout

Lulu runs as UID/GID 958 with `/home/lulu` as its passwd home. Normal user and
third-party application conventions are authoritative:

- `/home/lulu/.config/lulu`: Lulu-owned configuration, provider profiles, and settings.
- `/home/lulu/.config/<application>`: third-party application configuration.
- `/home/lulu/.local/share/<application>`: third-party application data.
- `/home/lulu/.cache`: rebuildable caches.
- `/home/lulu/.cache/lulu/romm/artwork`: locally synchronized RomM artwork.
- `/home/lulu/.local/share/lulu/catalogue.sqlite3`: persistent normalized Mudos catalogue.
- `/home/lulu/Games/ROMs`: platform ROM directories.
- `/home/lulu/Games/BIOS`: BIOS, Switch keys, and Switch firmware.
- `/home/lulu/Recordings`, `/home/lulu/Replays`, and `/home/lulu/Screenshots`: user media.
- `/opt/lulu`: packaged Mudos code and release payloads.
- `/run/lulu`: ephemeral Mudos runtime state.

## `/etc/lulu` Exceptions

The following files remain root-owned because they are host/session inputs and
must be available before the Lulu user session is initialized:

- `presentation.conf`: root-installed display/session policy consumed by the systemd session unit.
- `steamgriddb.env`: optional root-owned secret supplied through a systemd drop-in-compatible environment file.

No normal Lulu user or provider configuration belongs in `/etc/lulu`.

## Compatibility Symlinks

- `/home/user -> /home/lulu`: required by the shipped Eden AppImage, which
  ignores the process HOME/XDG values and resolves its internal user directory
  as `/home/user`. This is a single canonical target, not duplicated state.

All in-tree consumers and migrated Steam symlink targets use the canonical
layout; `/var/lib/lulu` is removed after successful state migration.
