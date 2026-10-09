# Reconciliation Backlog

Status: consolidated repository reconciliation, 2026-09-10. This records work
already implied by implementation, evidence, or existing engineering notes. It
does not add product proposals.

## Active Gaps

| Status | Area | Gap and evidence |
| --- | --- | --- |
| ACTIVE | Eden AppImage migration (EDEN-001) | Physical acceptance failed: v0.8.1 runs MK8 at v1.4.0 and controller input is absent. Read-only comparison shows both the retained v0.2.1 Flatpak and native v0.8.1 configs use `Paths\\external_content_dirs` with `/home/lulu/Games/ROMs/switch`; the MK8 per-title custom INI is byte-identical and lists no disabled add-ons. v0.8.1 source still uses SDL3, clears GUID bytes 2–3, and serializes SDL bindings with `engine:sdl,port:...,guid:...`; however, no Eden-authored v0.8.1 mapping has yet been captured. Do not close either defect or promote until root causes are implemented and physical acceptance passes. | `src/lulu/switch_provider.py`, `tests/test_eden_provider.py`, `docs/switch-provider.md` |
| PARTIAL | Lifecycle | Unify the live Steam UI/bridge launch path with sessiond ownership, or make an explicit retirement decision for the disabled supervisor. `steam-details-baseline.md`, `src/lulu/consoled.py`, `src/lulu/sessiond.py` |
| PARTIAL | Local runtime | Integrate emulator launches with authoritative lifecycle, presentation, and recovery; validate providers beyond RetroArch. `emulation-library.md`, `non-steam-runtime-architecture-baseline.md` |
| BLOCKED | RetroArch audio | Direct NES input/presentation/return evidence exists, but audio was unverified because the output device was not configured. `retroarch-runtime-validation-20260909.md` |
| UNKNOWN | Gamescope | Establish deterministic control-state startup and decide permanent package/version policy. `retroarch-runtime-validation-20260909.md`, `non-steam-runtime-architecture-baseline.md` |
| UNKNOWN | AppID | Decide production synthetic AppID namespace/allocation for non-Steam runtimes. `non-steam-runtime-architecture-baseline.md` |
| SUPERSEDED | Statistics Overlay / legacy Steam route | The routing correction makes every Mudos `steam:<AppID>` identity use the Aurelia Sessiond launch path, so Mudos no longer delegates game launching to the Steam client. The separate background Steam runtime remains. The generic Aurelia route now owns profile application for these identities; any future coverage gap should be tracked against that route, not a Steam-client per-AppID config contract. |
| PARTIAL | Controller | Complete discovery/persistence and management controls; retain the validated InputPlumber reconnect design. `controller-architecture.md`, `system-settings-status-20260909.md` |
| PARTIAL | Settings | Prove and then implement display, audio, network, Bluetooth, storage, power, and Mudos preference capabilities. `system-settings-status-20260909.md` |
| PLANNED | Store | Replace the explicit Store placeholder only if the existing Store/package scope is confirmed. `ui/ConsoleShell.qml`, `src/lulu/applicationd.py` |
| IMPLEMENTED (fresh appliance acceptance pending) | Packaging | Canonical install/uninstall/purge and machine-readable ownership contract are in `install-mudos.sh`, `scripts/install_mudos.py`, and `packaging/mudos-ownership.json`; physical fresh-install/OOBE acceptance remains separate. `docs/installation.md` |
| NOT TESTED | Hardware | Validate accepted visual/UI baseline on BC-250 hardware; host evidence is not hardware evidence. `liquid-glass-optical-evidence.md` |
| NOT TESTED | Integration | Exercise real D-Bus, InputPlumber, Gamescope, Steam, and emulator launch/recovery paths without relying only on unit tests. `tests/`, dated evidence docs |

## Planned Experiments Already Recorded

- Steam lifecycle experiments covering Proton/native titles, launchers,
  dialogs, overlays, recreated windows, and Gamescope/PipeWire signals.
- PipeWire USB disconnect/reconnect observation without restarting the session.
- Physical review of Home, Library, and System choreography on target hardware.

## Superseded Or Historical Material

- The padded Snell glass prototype is archived and not live UI.
- Scene-derived illumination and other rejected optical variants remain useful
  comparison evidence, not active work.
- The former Steam lifecycle/presentation watchdog remains disabled reference
  code pending an ownership decision; do not delete it as cleanup.

## Ambiguities For Review

- Steam documents describe different Gamescope launch environments (`--steam`
  and no `--steam`) and versions. Treat them as dated deployment snapshots until
  one current appliance baseline is recorded.
- `controller-architecture.md` says the production composite is non-persistent,
  while current evidence and session code refer to a persistent composite. The
  intended distinction between composite lifetime and profile/runtime state is
  not established by repository evidence.
- The Guide button's product behavior and its relationship to the controller
  architecture remain intentionally unresolved.
- Archived optical evidence references missing `EVID-D1-014` through
  `EVID-D1-017` artifacts; their external provenance is not locally navigable.
