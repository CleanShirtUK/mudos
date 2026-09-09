# System Settings Status: 2026-09-09

This is the first bounded System/Settings slice on the development HOST.

## Implemented

- `SystemSettingsProvider` normalizes product-facing rows by category.
- `ConsoleInterface.ListSystemCategories` and `ListSystemSettings` expose the model over the existing consoled D-Bus boundary.
- The UI bridge exposes read-only settings at `/settings?category=<name>`.
- System Home presents Display, Audio, Network, Bluetooth, Controllers, Storage, System and Lulu categories.
- A/B opens and backs out of System pages; D-pad moves rows; PageUp/PageDown provide bounded page navigation.
- The System page presents stable row identity, kind, value, detail and writable metadata.

## HOST Proven

- Hostname, OS/platform string and kernel are read from the running host.
- Root storage total/free space is read from the host filesystem.
- Default audio sink is read when `pactl` is available.
- Network general state, Wi-Fi radio state and host IP address are read when NetworkManager tools are available.
- Bluetooth powered state is read when `bluetoothctl` is available.

## TO PROVE

- Display output enumeration, mode switching, HDR and VRR capability/mutation.
- Audio sink selection, volume and mute mutation.
- Network scan, connect, disconnect, forget and controller-native password entry.
- Bluetooth discovery, pairing, connect, disconnect and removal.
- Detailed controller identity, player assignment, battery and vibration controls.
- Per-game storage usage and installation-root mutation.
- Reboot/shutdown confirmation path.
- Lulu-owned preference persistence and reduced-motion policy.

## Unsupported Or Deferred

- No privileged shell command is exposed to QML.
- No arbitrary package-manager/update frontend is exposed.
- No destructive storage or partition controls exist.
- No Wi-Fi password is logged or persisted by this slice.
- Final controller-native virtual keyboard is deferred.
- Settings page animation and horizontal transition grammar are deferred.

## Next Session Animation Queue

1. Finish the vertical Home-category transition.
2. Animate selected/unselected game-card size and dimming with accepted retargeting.
3. Add a Steam card beneath Library alongside All Games.
4. Use Library cards and System pages to develop horizontal transitions.
