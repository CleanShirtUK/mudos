# Flatpak provider

Flatpak is an optional Mudos plugin component. The provider owns discovery,
installation, update inspection, launch, and uninstall jobs; Flatpak owns
remotes, runtimes, sandbox deployment, and application data.

## Scope and ownership

Mudos-managed applications use the **lulu user Flatpak installation**. System
applications are enumerated for visibility and duplicate detection but are
never migrated or removed by Mudos. Uninstall uses Flatpak's normal application
removal and deliberately does not pass `--delete-data`; `~/.var/app/<id>` is
preserved.

Stable identities are `flatpak:<application-id>`. An app installed in both
scopes is represented once with a combined scope marker. Non-game applications
remain provider-visible but are not inserted into the Game Library unless a
future Apps surface explicitly requests them. AppStream category metadata is
used when available.

## Adapter and jobs

`src/lulu/plugins/flatpak/adapter.py` is the only Flatpak-specific API boundary.
It detects `gi.repository.Flatpak` and records `libflatpak` availability.
On this appliance the native `Flatpak.Transaction` path is active; the
supported Flatpak CLI remains a compatibility fallback when the GI binding is
unavailable. Install/update/remove operations run as one Mudos
parent job, report normalized resolving/transferring/installing/finalizing
stages, terminate only their owned child process on cancellation, and reconcile
actual user installation state after completion or interruption.

Flatpak application launch contributes a generic `launch` capability. Core
passes the normalized command to ProcessSupervisor/sessiond, which owns the
process group, presentation selection, and Guide Quit lifecycle. No Flatpak
branch was added to Home/Store rendering or generic session supervision.

## Remotes and provisioning

`scripts/provision-flatpak.sh` installs the native `flatpak` and
`python-gobject` packages through pacman, then idempotently adds Flathub only
to the lulu user scope with `flatpak remote-add --if-not-exists`. Existing
system and user remotes are preserved. The component manifest declares these
requirements for future OOBE/provisioning enumeration.

Flathub contributes the declarative `Flathub` Store card. It uses the shared
`f324` fallback glyph and disappears automatically when the component is
disabled. StoreHome contains no Flathub or Flatpak identity.

## Browser install handoff

The component declares a generic browser handoff for `flatpak+https` with the
trusted origin `https://flathub.org`. MudosBrowser reports non-web navigation
requests through the generic bridge; it does not mention Flatpak or Flathub.
The registry selects the owning component, and Acquisitiond asks that backend
to fetch and validate the HTTPS `.flatpakref` before creating the normal
provider JobManager parent job. Native `Flatpak.Transaction.add_install_flatpakref`
consumes the staged ref. Untrusted origins are rejected pending explicit
confirmation, and unknown schemes are rejected without execution.

The bridge immediately returns `Preparing installation…`; the resulting job
is visible in global Downloads while the browser remains usable.

## Current appliance limitation

Reconnaissance found no Flatpak executable, libflatpak library, or Flatpak GI
typelib on the initial live reconnaissance. Provisioning subsequently installed
Flatpak 1.18.2 and Python GObject 3.56.3; GI Flatpak 1.18 and native
transactions are now active. Flathub is configured only in the lulu user
scope. `org.openttd.OpenTTD` was discovered, installed, launched, quit,
uninstalled, and reinstalled through Mudos; its user data directory remained
present and its stable provider identity was preserved.

The launch process tree was `bwrap`/Flatpak sandbox to `openttd`, all in the
ProcessSupervisor-owned process group. OpenTTD exposed the existing X11
compatibility path in this session; the session-level delegated surface
metadata remained empty, so native external-Wayland delegation is not claimed.
No application-specific X11 environment hack was added.

Flathub browser install handoff was not implemented: no DOM scraping or
Flathub-specific browser branch was added. A future generic artifact-handoff
capability can claim `.flatpakref`/AppStream URLs without changing StoreHome.
