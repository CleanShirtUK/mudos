# Mudos Menu and provider launch contract

The Mudos Menu is the system-facing menu reached from the Mudos home rail. Its
fixed actions, in order, are:

1. Reset Mudos
2. Refresh Metadata
3. Refresh Library Catalogue
4. Refresh Available Downloads Catalogue
5. Reboot
6. Shutdown

Provider entries follow those actions and are generated from the normalized
provider registry. A provider appears as `[Provider Name] Menu` only when its
`provider.toml` has a `[launch.standalone]` command. Registry declaration order
is deterministic (currently provider id order).

## Launch declarations

Executable providers may declare independent semantics:

```toml
[launch.standalone]
command = "/usr/bin/retroarch --menu"
controller_mode = "game"

[launch.game]
command = "/usr/bin/retroarch"
```

The standalone command is invoked without a game, ROM, content path, or game
id. The game declaration documents the content-launch executable/base; existing
provider adapters continue to construct provider-specific game arguments. A
provider without a valid standalone frontend omits the standalone table and is
not shown in the Mudos Menu.

Standalone declarations may also specify `controller_mode`: `game` keeps the
normal virtual gamepad path (RetroArch), while `compat` is applied only after
the provider reaches the presented session state (Dolphin, Eden, and PCSX2).

Standalone launches use the same session lifecycle as local games. The session
state identifies `session_kind=provider_standalone` and carries `provider_id`
without inventing a game id. InputPlumber ownership transfers through the
normal session input-mode boundary and returns to Mudos when the provider exits.
Guide therefore exposes only relevant global actions for standalone sessions;
game-specific metadata actions are not inferred.

Metadata, installed-library, and available-download refreshes remain separate
catalogue stages. Available downloads are refreshed through the catalogue's
provider aggregation boundary (currently Steam/RomM sources), not a
provider-specific Mudos Menu branch. The existing refresh task serializes
overlapping requests.

Reset retains the existing safe Mudos session-reset behavior: it restarts the
Mudos graphical session and does not remove installed games, ROMs, BIOS,
provider data, Steam authentication, or unrelated user files. Reset, reboot,
and shutdown require a second activation confirmation; refreshes run directly.
