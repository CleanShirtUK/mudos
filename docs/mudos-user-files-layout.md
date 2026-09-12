# Mudos User Files Layout

This documents the current compatibility locations and the intended future
organisation for Mudos-owned files. This proposal centralises path selection
but does not move files on an appliance.

## Roots

| Root | Ownership | Purpose |
| --- | --- | --- |
| `/opt/lulu/current` | packaged, read-only | Release binaries, UI, packaged defaults, and bundled config |
| `/etc/lulu` | operator-mutable | Machine-level overrides and secrets supplied by the operator |
| `/var/lib/lulu` | user-mutable | ROMs, firmware, assets, provider data, state, and caches |

The `lulu.paths` module is the single source for the paths currently controlled
by Mudos. `LULU_DATA_ROOT` and `LULU_CONFIG_ROOT` select roots where supported;
the existing per-path `LULU_*` variables remain supported as compatibility and
test overrides. This proposal does not claim that either root relocates every
mutable Mudos file.

`/etc/lulu/` contains machine-level mutable configuration:

```text
/etc/lulu/
  providers/                       provider configuration overrides
  overrides/                       user/operator behavior overrides
  steamgriddb.env                  optional provider secret (existing path)
```

## Mutable Data

```text
/var/lib/lulu/
  roms/<platform>/                 user ROMs
  bios/<platform>/                 user firmware/BIOS files
  assets/                          intended user-supplied Mudos assets
  recordings/                      future gameplay recordings
  captures/                        screenshots and replay artifacts
  providers/                       provider-specific mutable data
  state/                           intended durable application state
  cache/                           intended rebuildable caches
```

## Current Compatibility Locations

The current consumers retain these effective defaults until a separate,
explicit filesystem migration is approved:

```text
/var/lib/lulu/.local/share/lulu/catalogue.sqlite3
/var/lib/lulu/.cache/lulu/steamgriddb/              SteamGridDB artwork cache
/var/lib/lulu/.cache/lulu/steamgriddb/metadata/     SteamGridDB metadata cache
/var/lib/lulu/.local/share/Steam/                   Steam library root
/var/lib/lulu/roms/                                 ROM root
/var/lib/lulu/bios/                                 BIOS root
```

`MudosPaths` currently controls those locations, plus the future-oriented
`assets`, `recordings`, `captures`, `providers`, `state`, and `cache` fields.
The future organisation of generated caches and durable state is intentionally
not applied to existing consumers in this proposal.

Steam's installed library remains a provider-owned path. Mudos defaults to
`/var/lib/lulu/.local/share/Steam` for the appliance and accepts
`LULU_STEAM_ROOT` or the existing colon-separated `LULU_STEAM_ROOTS` override.

Packaged defaults are never written into the mutable tree. Replacing a user
asset means replacing the file in its documented asset directory, not changing
source code. A future migration proposal must define discovery, copy/rollback,
permissions, and adoption of the canonical locations before moving files.

## Configuration Precedence

Packaged defaults under `/opt/lulu/current/config` establish baseline behavior.
Operator overrides under `/etc/lulu/providers` and `/etc/lulu/overrides` take
precedence only where a service supports them. User content and generated state
remain in their current compatibility locations; the future canonical split
under `/var/lib/lulu` is not activated here. Caches may be deleted without
losing ROMs or BIOS files, but the current catalogue database is durable state
and must not be deleted without an explicit reset.

The proposed split follows the XDG Base Directory distinction between data,
configuration, state, cache, and runtime files, while this compatibility phase
retains Mudos' existing explicit system and appliance data paths. Filesystem
migration is future work.
