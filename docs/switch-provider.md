# Nintendo Switch Provider

Mudos uses the maintained Linux build of [Eden](https://eden-emu.dev/) through
`eden-cli`. Eden supports direct game paths, an alternate configuration file,
fullscreen startup, and SDL gamepad input. Mudos writes the deterministic
source profile to the provider-owned `lulu-switch.ini` and applies the same
`[Controls]` section to the active `qt-config.ini` immediately before launch.
Each connected player is emitted as an Eden-native SDL slot (`type=0`) with a
distinct SDL port; no unpopulated slot is left as a keyboard mapping.
`LULU_SWITCH_SDL_GUID` overrides the default Xbox 360 SDL GUID when hardware
validation identifies a different virtual-device GUID.

Place only legally obtained user-owned files under the Mudos Switch locations:

```text
/var/lib/lulu/roms/switch/                 # .nsp or .xci games
/var/lib/lulu/bios/switch/keys/prod.keys   # user-dumped keys, if required
/var/lib/lulu/bios/switch/keys/title.keys  # user-dumped keys, if required
/var/lib/lulu/bios/switch/firmware/        # user-dumped firmware, if required
```

Mudos does not download, include, or provide firmware, keys, games, or other
copyrighted material. Eden configuration and prerequisite discovery remain
subject to hardware validation; the provider does not claim that a package is
launchable without the user's legally obtained prerequisites.
