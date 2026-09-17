# Storage settings

Storage settings use UDisks2 on the system D-Bus as the authority for block
devices, filesystem metadata, mount state, hotplug, unmount, and removable-drive
power-off. `src/lulu/storage_manager.py` normalizes useful filesystems and
filters ignored/pseudo objects. The active root filesystem and UDisks system
devices are protected from unmount/eject and target selection; read-only
filesystems cannot become targets. Stable filesystem UUIDs, never `/dev/sdX`,
are persisted.

The controller page exposes physical devices, capacity/free space, filesystem,
mount point/state, removable/internal classification, and two logical targets:
Game Install Storage and Emulation Storage. Mounting/unmounting is performed by
UDisks2. Selecting a mounted writable filesystem creates:

```
<mount>/Mudos/Executables/{steam,lutris,native}
<mount>/Mudos/ROMs
<mount>/Mudos/BIOS
```

Selection changes the future canonical policy only; existing content is not
silently migrated. `paths.py` resolves configured target mount paths and keeps
`~/Games` as the default. Steam libraries resolve through
`Executables/steam`; ROMM, catalogue scanning, RetroArch, and BIOS paths use
the canonical emulation root. A missing selected target remains explicitly
unavailable rather than silently redirecting writes.

The current machine has no UDisks2 service installed and only the protected
NVMe system disk was present during implementation, so physical USB
mount/eject/hotplug validation is pending installation of UDisks2 and insertion
of an explicitly identified disposable USB. No partitioning or formatting UI
was added. Audio, Guide, UI sounds, and other settings are unchanged.
