# PC acquisition and Lutris architecture

## Boundary

Questarr owns discovery and release selection. Transmission/NZBGet owns
transfer. Mudos observes completed Questarr-labelled/category downloads and
turns them into `PcInstallSource` records; completion is **Ready to Install**,
not an installed Library game. Manual files and directories use the same
source model with `provenance=manual`.

Questarr's durable association is its parent `gameId` plus each download UUID
and downloader hash/job. Mudos resolves that metadata through Questarr's
read-only API, keyed by `(protocol, downloader hash)`. Release-title matching
is only a fallback and is never the authoritative association. Questarr's
read-only acquisition mounts remain sources; Mudos never grants Questarr write
access to `Executables`.

## Source inspection

`PcInstallSource` records canonical identity, provenance, Questarr/download
IDs, downloader hash/job, completed path, discovered files, source type, and
readiness. Inspection never executes a file, mounts an image, or inspects an
incomplete downloader path. Initial classifications are Windows EXE, MSI,
disc image, archive, directory, multi-part media, and unknown. Unknown data
is preserved for manual classification.

## Lutris adapter

The native Arch package is Lutris **0.5.22**. Mudos isolates Lutris-specific
behavior in `lutris_adapter.py` and reuses Lutris's APIs and installer schema:

- `lutris.api.search_games` and `get_game_installers` query Lutris metadata.
- Recipe `script.files` requirements are mapped against the completed source;
  `N/A` local requirements are automatically supplied only on a unique match.
- Multiple recipes or ambiguous files remain selectable instead of being
  guessed. No recipe leaves the source Ready to Install.
- Installation will use Lutris's `ScriptInterpreter`/`LutrisInstaller`, not a
  Mudos YAML interpreter. Runner and Wine preparation remain Lutris-owned.
- `LutrisInstallExecutor` keeps one Mudos parent job through recipe resolution,
  source-file preparation, Lutris runner preparation, ScriptInterpreter
  execution, registration readback, and catalogue reconciliation. Remote recipe
  files use Lutris's own `Downloader`; local/N/A files are supplied from the
  source without copying the acquisition tree.
- Headless startup creates Lutris's normal XDG directories and invokes Lutris's
  own `syncdb` migration entry point. It does not instantiate the GTK frontend
  or issue SQL directly. Lutris display probing still emits no-display
  warnings, but no Lutris window is presented.
- Lutris's own `Game.write_script` generates the frontend-free launcher. The
  generated script preserves the registered runner/configuration and was
  launched through the existing Mudos session/display. Unresolved installer
  prompts are reported and stopped rather than fake-clicked; real delegated
  child-installer surface integration remains the next controller boundary.

Every Mudos-managed payload is rooted at
`/home/lulu/Games/Executables/lutris/<safe-slug>/`; acquisition sources remain
under `.acquisition`. Uninstall will remove only the Lutris registration and
that canonical payload, preserving the source and shared runners so the game
can return to Ready to Install. Failed transactions clean a destination only
when Mudos created it for that attempt; source media is never deleted.

## Functional validation — OpenTTD

On 2026-09-22, the legal/free OpenTTD `openttd-v141` recipe completed through
Acquisitiond as one parent job. Lutris registered ID `1`, runner `linux`, and
`/home/lulu/Games/Executables/lutris/openttd`; Mudos converged it to one
`lutris:openttd` catalogue identity with the original manual source retained.
The generated Lutris launcher ran in the controlled session and returned after
the test harness terminated it. Uninstall removed the payload and registration
while preserving the source; a second install completed from that source
without redownloading it.

Interactive Wine installer delegation uses the existing delegated surface and
COMPAT input mode. A real commercial Wine payload was not launched; the
ScriptInterpreter-backed synthetic transaction is the milestone proof.

Installed Lutris games are now dispatched through the existing
`ProcessSupervisor` using the generated Lutris script and the catalogue game
identity. This gives Guide Quit an owned process-group boundary and avoids
executable-name killing. The live service launch now exposes the child window
under the existing Gamescope session; the controller-native action uses the
same owned boundary.

The graphical launch boundary is now explicit: `consoled` resolves the active
session's allow-listed display/runtime variables and hands them to `sessiond`
as a `DelegatedLaunchContext`. `ProcessSupervisor` merges that context only
into the owned child environment. This preserves process-group ownership and
Guide cleanup while avoiding hardcoded display/socket/PID values or a second
Gamescope instance. OpenTTD now produces an XWayland-observable Gamescope
surface through this path; native Wayland support is not inferred from the
successful XWayland observation and remains subject to the existing
presentation implementation.

The reusable interactive session seam is `RequestInteractiveLaunch`: it gives
an owned external child the same context, process group, Gamescope association,
and COMPAT input mode as a game, with `install` as the delegated surface. A
real GTK fixture demonstrated XWayland surface delegation, successful child
exit, parent-process continuation, and owned-group cancellation. Native
Wayland GTK surfaces are not currently represented by the XWayland-only
 Gamescope focusable-window metadata, so the fixture's X11 mode was used only
 to validate the existing supported presentation path. Parent cancellation is
 transaction-ID based; a legal real Wine smoke test remains pending.

## ScriptInterpreter interactive commands

Lutris 0.5.22's `installer.commands.execute` is the narrow interactive seam.
For upstream recipes Mudos annotates only Wine `wineexec`/`execute` commands
whose executable is a locally supplied installer file and whose arguments do
not contain an unattended switch (`/S`, `/SILENT`, `/VERYSILENT`, `/qn`,
`/quiet`, or GNU equivalents). Linux commands, archive/file operations, runner
setup, and DOSBox recipes remain automatic. The annotation is made on an
in-memory recipe copy; upstream API data is never modified. The resulting
`env.MUDOS_INTERACTIVE=1` marker is internal transport only. Mudos then uses
`RequestInteractiveLaunch` with the same delegated context and owned process
group. The ScriptInterpreter is paused while the child is active, the Mudos
parent job reports `awaiting_interaction`, and the interpreter resumes on a
successful child exit. Explicit Guide cancellation follows the owned-group
cancellation path and does not count as a successful command.

The controlled recipe proof completed pre-step, interactive child, post-step,
and final registration. Ready-to-Install Lutris source records use the
canonical PC identity and the existing Store Install action submits
`SubmitPcInstall`; no Lutris frontend or second download identity is created.
A real Wine recipe remains outstanding; native Wayland surfaces are separately
unsupported by the current XWayland-only Gamescope metadata.
