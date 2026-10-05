# QUIVER-001 upstream contract evidence

Research performed 2026-10-05 against the public upstream documentation for
[Quiver Launcher](https://github.com/tgeorgiadis/quiver-launcher) and this
checkout. This is evidence, not an implementation specification for a new
Mudos-owned downloader.

## Repository findings

- There is no Quiver source, binary, service, configuration, provider entry, or
  Quiver-specific historical implementation in this checkout or its available
  Git history. `BACKLOG.md` also did not contain QUIVER-001 at the start of this
  work.
- Questarr is not Quiver. Commit `636786d` explicitly retired Questarr's
  provider-specific integration while retaining generic Acquisitiond jobs,
  persistence, manual PC installation, and Lutris. Questarr must stay retired.
- Mudos already has generic provider definitions/capabilities in
  `src/lulu/providers/`, provider/catalogue plugins, provider-neutral
  Acquisitiond jobs, and provider launch/session boundaries. None declares or
  implements Quiver.

## Public upstream product identified

The public project matching the name is **Quiver Launcher**, a .NET/Avalonia
desktop application forked from GithubLauncher. Its README describes a personal
app library, community app-catalog subscriptions, and downloads/updates from
GitHub and GitLab releases. Upstream also ships a command-line interface; its
source (`Services/CLIHandler.cs`) implements `--list`, `--download <name>`,
`--update`, `--run <name>`, and `--uninstall <name>`. The CLI is a real
automation boundary, but it is a human-oriented command interface rather than
a documented daemon or structured provider API.

The upstream product owns its `apps.json`, `settings.json`, `Apps/`, `Cache/`,
and backups beside its AppImage (or under its XDG fallback when that location is
not writable). Its app catalog describes names, repository/source, folder name,
release-asset filters, tags, and icon URL. The docs say Quiver downloads and
installs assets into its own app folder, launches from its own library, and
does not delete installed files when an entry/source is removed. Optional
GitHub/GitLab API tokens are entered in Quiver's own settings to avoid rate
limits; public GitLab releases need no token. No Mudos credential contract is
documented.

The CLI prints text (including percentage progress for downloads), returns
process exit codes, and operates by game name/folder name. In the reviewed
contract there is no structured job ID/state API, cancellation command, or
provider-change event/reconciliation interface. The CLI uses Quiver's own
`GamesFolder` and `FolderName` layout. Quiver app definitions do not declare a
Mudos launch command or platform identity; `--run` relies on Quiver's own
selected-executable logic and waits for the launched game process/group to
exit. Those semantics are not automatically equivalent to Mudos catalogue,
canonical storage, and Sessiond ownership.

Thus, for the public project, Quiver is both the library and acquisition
authority of its desktop environment, but is not currently evidenced as a
Mudos library authority. The CLI makes a backend adapter technically possible,
but does not by itself establish the required provider contract.

## Integration consequence

Using the upstream CLI is possible in principle, but would make Quiver's
library/install tree and name-based CLI authoritative unless Mudos deliberately
defines a synchronization/ownership adapter. That presents concrete unresolved
decisions: whether Quiver's own `Apps/` can be the canonical Mudos content root;
how unstructured CLI output becomes durable Acquisitiond progress/restart state;
how Mudos obtains stable identities/platform/launch metadata; and how the CLI's
own selected-executable and process-group behavior composes with Sessiond.
Implementing the release protocol directly in Mudos would instead make Mudos
the acquisition authority, not Quiver. Neither choice is implied by upstream.

No provider code, service, package, credential flow, or data migration should be
implemented until the intended Quiver product/contract is confirmed and that
authority boundary is selected. In particular, do not install or run the
upstream AppImage on Lulu as an acceptance test: that would create a parallel
library and app root, not validate Mudos integration.

## Sources

- https://github.com/tgeorgiadis/quiver-launcher
- https://raw.githubusercontent.com/tgeorgiadis/quiver-launcher/main/README.md
- https://raw.githubusercontent.com/tgeorgiadis/quiver-launcher/main/Services/CLIHandler.cs
- https://raw.githubusercontent.com/tgeorgiadis/quiver-launcher/main/QuiverLauncher.Desktop/QuiverLauncher.Desktop.csproj
- https://github.com/tgeorgiadis/quiver-community-app-catalog
- Mudos `src/lulu/providers/model.py`, `src/lulu/providers/registry.py`, and
  `src/lulu/acquisitiond.py`
- Mudos validation log, “Questarr retirement — 2026-10-04”
