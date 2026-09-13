# Full Project Recovery Checkpoint

**Checkpoint date:** 13 September 2026

## Canonical Recovery Anchor

- Project checkpoint commit: to be recorded by the commit containing this document.
- Recovery source and application payload commit: `d25d28f766ce26f91f5c131633036309b039d4d9`.
- Source commit timestamp: 2026-09-13 00:40 BST.
- Source commit subject: `checkpoint: record Eden verified SDL mapping`.
- Historical source comparison: this is the modern recovered state, not the obsolete `7c96e0619a749cca5b088cb88421fd57e3a61381` baseline.

## Active Deployment

- Active target: `/opt/lulu/current`.
- Active release: `/opt/lulu/releases/d25d28f766ce26f91f5c131633036309b039d4d9-3eb74eb63bb2`.
- Application release source commit: `d25d28f766ce26f91f5c131633036309b039d4d9`.
- Release tag: `recovery-0406-bst`.
- Release manifest identifier: `3eb74eb63bb2`.
- Manifest SHA-256: `3eb74eb63bb226e7c4ba767188855166f673024b2ff3289e93f3ac5ab9bf7138`.
- Strict installed manifest verification: PASS.
- The deployment was freshly built from the recovered source. The application payload remains intentionally sourced from `d25d28f`; this documentation checkpoint is a project-level commit on top of that application source.

Representative active payload hashes:

| File | SHA-256 |
| --- | --- |
| `ui/ConsoleShell.qml` | `9fb0263d5c6c8e0215e19bd18a9006f7440f536481b7a84bc6e8302ba4b83e44` |
| `scripts/console-ui-bridge.py` | `b05eaf3bdcfcd5f3a15f9b355af4cba3e2da6e31d2108faa6a9c8998bc44b51b` |
| `lib/lulu/controllerd.py` | `ec4dd764054a39ef16b245ab155eddeac77bf088e9b68aca15bd4cdab57fb22a` |
| `lib/lulu/emulator_runtime.py` | `aaa7cddd7c909d280de17243974d0e148f80bbf351b27ea205ec9a2be07e0b8b` |
| `lib/lulu/emulation.py` | `640c2a36264ad61546198b9b7533d5b1fe59d751d0c327f4d8b4fc365e50a9a7` |
| `lib/lulu/catalogue.py` | `67605979a614c2ace87894068e406e8189ee390abcc9d7caca0c476a8f5ef75f` |

The representative source files and deployed counterparts matched byte-for-byte when this checkpoint was created.

## Recovered State

The following areas are present in the recovered modern project state and were accepted or recovered historically during the 12/13 September work. This record does not claim that each item was freshly physically revalidated after recovery.

- Current Home and Library UI, including the modern card, artwork, spatial, and navigation surfaces.
- Mudos Guide and recovery architecture.
- Controller, session, input-mode, and process lifecycle architecture.
- RetroArch integration and normalization.
- PCSX2 integration and normalization.
- Dolphin integration and normalization.
- Current metadata, catalogue, artwork, and asset work.
- Deployment, payload, manifest, service, and provenance infrastructure.

## Post-Recovery Validation Outstanding

- The Mudos shell process/window exists, but readiness detection reports: `Mudos shell readiness window was not found`.
- Current automated hardware validation reports no InputPlumber controller composite.
- Controller navigation, Guide operation, and RetroArch, PCSX2, and Dolphin launch/return regression checks remain outstanding after recovery.
- These issues are recorded here without attempting fixes in this checkpoint.

## Eden Result Preserved For Later

Earlier physical testing established this path:

`physical controller -> InputPlumber virtual Xbox -> SDL events`

The SDL GUID was `030081b85e0400008e02000001000000`. Fresh Eden showed no controller response. The first proven Eden-specific failure boundary was `SDL -> Eden`. Eden investigation is explicitly deferred until after this recovery checkpoint.

## Future Recovery Return Point

Future recovery should return to the annotated Git tag for the commit containing this document, `recovery-2026-09-13-full-project`, and use the application payload from `d25d28f766ce26f91f5c131633036309b039d4d9` with the active release and manifest recorded above. Do not use `7c96e06` or dirty later worktrees as a recovery baseline.
