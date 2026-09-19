# Provider-owned uninstall contract

Uninstall is a `JobOperation.REMOVE` job owned by `acquisitiond`. The service
resolves catalogue identity, reports capability, prevents duplicate/conflicting
operations, and publishes the normal job snapshot. UI code does not execute
provider commands or delete files.

Current providers:

* **Local/ROM:** removes only the authoritative installed file or dedicated
  game directory below `MudosPaths.rom_root`. Missing content is idempotent;
  roots, platform directories, outside paths, and escaping symlinks are rejected.
* **RomM:** RomM is provenance. A RomM row linked to a local installed row
  resolves to the local executor; the remote record is never mutated.
* **Steam:** the Steam plugin invokes SteamCMD's provider-native
  `app_uninstall` operation after positively discovering the AppID in the
  canonical Mudos library. Generic Mudos code never removes Steam files.

Future Lutris, Flatpak, and subordinate Switch content providers should expose
the same provider executor `uninstall(job, reporter)` capability. Switch
updates/DLC should use separate content-level operations rather than changing
the full-game contract.
