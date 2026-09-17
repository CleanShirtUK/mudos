# Controller Settings

Controller Settings is a management and policy surface, not an input remapper.
InputPlumber remains authoritative for physical discovery, virtual targets,
interception, and runtime handoff. Mudos consumes its normalized composite
state through `controllerd` and exposes connection, stable physical identity,
logical player, navigation ownership, and battery state when available.

Runtime composite paths and evdev nodes are deliberately not persistent
identities. The strongest available identity is InputPlumber's
`PersistentId` (currently `045e_0291` for the validated Xbox 360 wireless
controller), with the runtime composite path used only as the current handle.
Hardware receiver slot numbering is not changed by Mudos and remains owned by
the receiver/controller power-cycle behavior.

Player assignments and preferred navigation identity are Mudos policy stored
in `~/.config/lulu/controller-policy.json`. Assigning a player changes logical
ownership only; it does not rewrite buttons, axes, keyboard/mouse mappings, or
provider configuration. Provider mappings remain owned by RetroArch,
Dolphin, PCSX2, Eden, Steam, or the game itself. Nintendo face-button and
Dolphin Classic Controller conventions therefore remain provider-side policy
contracts.

If the preferred navigation controller disconnects, the controller registry
selects the lowest-numbered connected logical player and persists that
effective owner. A returning former owner is recognized without forcibly
stealing focus mid-action. InputPlumber recreates composites on reconnect and
Mudos restores the safe default interception baseline without restarting the
daemon. Event-driven updates are supplemented by a one-second reconciliation
pass while Controller Settings is open, and the session monitor also performs
periodic reconciliation to cover startup/readiness races.

The normal page intentionally shows no raw event stream or arbitrary mapping
editor. Battery values are displayed only when the authority reports a
meaningful value. No-controller and unavailable-InputPlumber states remain
valid shell states.
