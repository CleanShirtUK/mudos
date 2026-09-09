# Lulu Framework Checkpoint: 2026-09-09

This is the current known-good interaction and presentation baseline.

## Accepted Interaction Primitives

- Home vertical category navigation uses a bounded desired destination: the first hop is 250ms and buffered chained hops are 100ms, both `Easing.OutQuint`.
- Home uses a persistent translated title rail with the accepted active-category gap.
- Home category cards use full-size finished presentations inside masked reveal containers and the fixed card viewport.
- Recent uses a retargetable horizontal rail with compact/focal morphing and natural physical-edge clipping.
- Library and System use sibling `NavigationCard` rails with fixed card geometry, captured-X retargeting, natural edge clipping, and opacity-only emphasis.
- Library landing contains All Games and Steam; activation enters the existing fullscreen Library grid using the selected provider scope.
- System landing contains the eight settings categories; activation enters the selected actual settings page directly.
- B preserves the originating Library/System landing selection; LB/RB switch actual System settings pages directly.

## Shared Card Contract

- `NavigationCard` is the shared All Games, Steam, Store, and System landing-card family.
- Cards retain fixed width, height, symbol geometry, title geometry, and internal padding across selection.
- Navigation cards have no conventional borders and no glow; selection is communicated through accepted opacity/dimming emphasis.
- Navigation cards retain the shared canonical Orbit sampling, transmission, diffusion, bulge, bevel, edge-lighting, and rounded-mask treatment.

## System/Settings Architecture

- `SystemHome.qml` owns the direct multi-card settings-category rail.
- `SystemSpace.qml` owns the actual settings rows for the selected category.
- `SystemSettingsProvider`, consoled D-Bus methods, and the `/settings` bridge provide the existing read-only model and writable metadata.
- Settings navigation does not enter a second category-selector screen.

## Settings Status

- Implemented: normalized category/row model, host status reads, D-Bus exposure, HTTP bridge, row navigation, and direct category-page routing.
- HOST Proven: hostname/platform/kernel, root storage totals, default audio sink when available, NetworkManager state/IP when available, and Bluetooth power state when available.
- TO PROVE: output modes/HDR/VRR, audio mutation, Wi-Fi operations, Bluetooth pairing, detailed controller management, storage usage/mutation, update strategy, reboot/shutdown, and Lulu preference persistence.
- BC-250 Proven: nothing is claimed by this checkpoint; development HOST observations remain HOST-only.

## Known Remaining Work

- Physically review the current Home vertical choreography and buffered stepping across all categories.
- Physically review Library/System landing rail peeking and retargeting on target hardware.
- Add settings capability implementations only after their underlying system behavior is proven.
- Add settings-page horizontal animation later without changing the direct landing-to-page architecture.
