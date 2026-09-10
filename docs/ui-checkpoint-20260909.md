# UI Checkpoint: 2026-09-09

This is the bounded checkpoint immediately before System/Settings work.

## Accepted And Working

- Home static presentation baseline and current responsive geometry.
- Recent horizontal rail with bounded, no-wrap navigation.
- Interruptible/retargetable Recent Left/Right navigation.
- Compact to focal Recent card geometry using `500ms Easing.OutQuint`.
- Monotonic artwork geometry with no overshoot.
- Focal-only chrome fades.
- Compact title fade without title scaling during the card morph.
- Accepted focal glass treatment and canonical live sampling.
- Accepted Play stacked-glass treatment.
- Persistent shell-owned Library spatial glass surface.
- All Games Home surface to fullscreen Library morph.
- Fullscreen Library presentation, grid, collection and game navigation.
- Library content fade choreography.
- Controller glyph hints and controller-first input routing.
- Steam catalogue and SteamGridDB artwork path.

## Current Baseline

- Home vertical category navigation uses buffered destination stepping: 250ms for the first hop and 100ms for chained hops.
- Library and System landing rails use the shared NavigationCard interaction pattern.
- Settings remains a capability/status framework; see [the framework checkpoint](framework-checkpoint-20260909.md) for proof-state boundaries and priorities.

Remaining UI work is physical review of the current vertical/rail choreography
and later settings-page animation. Do not expand settings controls speculatively.

## Current Checkpoint Notes

- Current active deployment is the development host, not BC-250 evidence.
- The current Home category choreography is the accepted framework baseline.
- Settings functionality remains incomplete and proof-state bounded.

## Next Queue

1. Prove display/output, audio, network, Bluetooth, controller, storage, update, power, and Mudos preference capabilities.
2. Add settings controls only after capability proof.
3. Add settings-page horizontal animation without changing landing/page ownership.
