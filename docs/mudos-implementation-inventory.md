# Mudos Implementation Inventory

Status: repository-derived inventory, 2026-09-10. The implementation is the
authority for this inventory; dated evidence records are separate from runtime
claims.

## UI Screens And Views

| Area | Current implementation | Status |
| --- | --- | --- |
| Home | System, Store, Library, and Recent domains in `ui/ConsoleShell.qml`; Recent catalogue/artwork cards in `ui/RecentHome.qml` | IMPLEMENTED |
| Library | All Games, Steam, and discovered local-platform collections; fullscreen grid and collection navigation in `ui/LibraryHome.qml` and `ui/LibrarySpace.qml` | IMPLEMENTED |
| Settings | Direct System category rail and category row pages in `ui/SystemHome.qml` and `ui/SystemSpace.qml` | PARTIAL: read/status model, not full mutation |
| Store | Landing card and explicit not-implemented activation path in `ui/StoreHome.qml` and `ui/ConsoleShell.qml` | PLANNED |
| Guide | Native shell overlay path, QML invocation, and InputPlumber Guide profile | PARTIAL: limited behavioral evidence and integration boundaries |

## Services And Boundaries

| Area | Implementation | Status |
| --- | --- | --- |
| Catalogue | Steam and local providers reconcile into SQLite `CatalogueGame` records | IMPLEMENTED for discovery; metadata/artwork and refresh integration remain limited |
| Input/controller | InputPlumber profiles and reconnect monitoring; native SDL3 polling in the shell | PARTIAL: low-level reconnect path exists; controller management is deferred |
| Session/lifecycle | State/token contracts, process supervision, input modes, and a Steam supervisor in `sessiond.py` and related modules | PARTIAL: live UI launch path and supervisor ownership are not unified |
| Steam | Manifest discovery, artwork, details navigation, rungame requests, bootstrap, and lower-level process observation | PARTIAL: lifecycle ownership differs by path |
| Emulator/ROM | Registry, root-scoped discovery, readiness checks, launch intents, and direct local runtime launch | PARTIAL: providers and authoritative lifecycle integration are incomplete |
| Background services | `consoled` provides catalogue/settings/launch boundaries; `console-sessiond` provides lifecycle/process/input monitoring | PARTIAL: `controllerd`, `applicationd`, and `console-ui` remain boundary/placeholder services |
| Configuration | Environment-driven runtime configuration, InputPlumber profiles, RetroArch config, and a settings library | PARTIAL: settings persistence is not wired into UI/services |
| System integration | `./install-mudos.sh`, machine-readable `packaging/mudos-ownership.json`, systemd units/target, PAM/logind, VT, seatd/InputPlumber ordering, native Qt/X11 shell | Production install/uninstall/purge contract implemented; shared system settings outside declared ownership remain untouched |
| Recovery | Token ownership, process-group escalation, reconnect handling, and evidenced natural Gamescope fallback | PARTIAL: recovery behavior varies by launch path and has no unified retry UI |
| Evidence/tests | Python unit tests plus dated manual/runtime evidence under `docs/` | PARTIAL: no complete hardware or real service integration matrix |

## Launch Paths

- Steam selections currently issue Steam URI requests through the catalogue/
  bridge path; lower-level sessiond Steam supervision remains in source.
- Local emulator selections can launch runtime processes directly from
  `consoled`; they do not yet consistently use authoritative session lifecycle
  ownership.
- The non-Steam RetroArch architecture has separate dated evidence for a
  transient systemd scope and Gamescope AppID fallback.

## Explicitly Not Present

- Store/package-management backend, installation/update UI, and checkout.
- Full settings mutation for display, audio, network, Bluetooth, storage, and
  power.
- ROM import, metadata enrichment, local artwork, and BIOS management UI.
- Complete controller identity, assignment, battery, vibration, and persistence.
- Permanent Gamescope/AppID policy.
