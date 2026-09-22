# Questarr integration

## Upstream reconnaissance

The selected upstream release is **Questarr v1.4.2**, released 2026-08-11.
The release provides an official container image and Docker Compose deployment;
the image is pinned in the appliance unit by digest rather than using `latest`.
The supported native development/production path is Node.js/npm, but this host
had no Node runtime and upstream's production packaging is container-first.

Questarr v1.4.2 uses Node 26 in its image, Express, and a self-contained SQLite
database. `SQLITE_DB_PATH` defaults to `sqlite.db`; the appliance sets it to
`/app/data/sqlite.db`. The public liveness endpoint is `/api/health` and the
readiness endpoint is `/api/ready` (readiness requires authentication).
HTTP defaults to port 5000 and upstream defaults to `0.0.0.0`; the appliance
retains that bind for the LAN browser and restricts access with UFW.

First-run setup is intentionally upstream-owned. `GET /api/auth/status` is
public; when it reports no users, the operator must open Questarr and create
the first username/password through its setup page. Mudos does not invent or
store that password. Authenticated API calls use the returned JWT bearer token.
Questarr generates and persists its JWT signing secret and credential-encryption
key in its SQLite `system_config` table when environment values are absent.
Downloader and indexer credentials are AES-256-GCM encrypted at rest by
Questarr. The persistent database path is `/var/lib/lulu-questarr/data/sqlite.db`.

The supported integration mechanisms are:

- `POST /api/indexers/prowlarr/sync` for Prowlarr synchronization. It reads
  `/api/v1/indexer`, filters torrent/usenet protocols, and creates Torznab or
  Newznab indexers using Prowlarr's `/<indexer-id>/api` feeds.
- Native Questarr Transmission and NZBGet downloader clients.
- Downloader categories/labels. Transmission receives labels; NZBGet receives
  the configured category. Mudos uses `questarr` for both provenance markers.
- Questarr's authenticated downloader test and submission APIs.

Questarr's importer supports `move`, `copy`, `hardlink`, and `symlink`, and has
an auto-delete-after-import option. It resolves completed paths from downloader
metadata and supports path mappings. Automatic import/destructive cleanup is
not enabled in this pass: the acquisition trees are mounted read-only and the
canonical downloaded-versus-installed Mudos boundary remains authoritative.

## Appliance deployment

Questarr is deployed as the systemd-managed rootful Podman service
`lulu-questarr.service`. Rootful Podman was selected over native Node because
it follows upstream's supported production packaging, contains the Node/npm
runtime, avoids adding a second host-level JavaScript runtime, and does not
require a heavyweight orchestration stack. The unit uses host networking only
for narrow local appliance connectivity to the existing Transmission/NZBGet
services; UFW permits TCP 5000 only from the detected LAN subnet.

The image is pinned to:

`ghcr.io/doezer/questarr@sha256:6faaf75f484a20805309315dd9eb9f1550b039a668efb89c13fc028c72b45485`

Persistent state is outside the mutable Mudos runtime at
`/var/lib/lulu-questarr/data`. The existing acquisition trees are exposed at
identical in-container paths, read-only for this pass:

- `/home/lulu/Games/.acquisition/torrents`
- `/home/lulu/Games/.acquisition/usenet`

No second Transmission or NZBGet daemon is created. Questarr is enabled
independently at boot and a failure does not make the graphical Mudos session a
systemd dependency.

## Current integration boundary

Questarr is also an active acquisition source for Nintendo Switch base games,
updates, and DLC.  Its game record is the parent identity and its individual
download records retain the structured `downloadType` (`game`, `update`, or
`dlc`), downloader identity, release title, and status.  Mudos must consume
these as `GameContentComponent` records: each transfer remains visible as its
own download job, while all completed components attach to one Switch library
identity.  Filename parsing is only a fallback when a provider result omits
the structured role.

Questarr is visible in the Mudos admin Services page with service state, an
HTTP health result from `/api/health`, and an Open UI link. The fixed Home Store
card **Questarr** launches the existing Mudos WebEngine browser at
`http://mudos.local:5000/`; it is non-removable and uses the already-implemented
generic delegated browser/compatibility lifecycle.

The Mudos QML Store card uses the internal loopback URL
`http://127.0.0.1:5000/`. The Mudos admin Open UI link and normal LAN browsers
continue to use `http://mudos.local:5000/`; custom bookmark behavior is
unchanged.

The appliance Prowlarr endpoint is now known as
`http://192.168.0.197:9696/`. From inside the Questarr container, an
authenticated probe succeeded against `/api/v1/system/status` (Prowlarr
version 2.5.2.5491) and `/api/v1/indexer` (six indexers: four torrent and two
usenet). The supplied API-key file was read only at runtime; its value was not
copied, logged, or committed.

Questarr has no users yet. Its supported API places Prowlarr synchronization
behind JWT authentication, so synchronization cannot be invoked before the
operator completes first-run setup. SQLite manipulation is explicitly not used.

## Mudos-owned credential authority

The migrated Prowlarr configuration is now in
`/home/lulu/.config/lulu/provider-services.toml`:

```toml
[providers.prowlarr]
enabled = true
endpoint = "http://192.168.0.197:9696/"

[providers.prowlarr.secrets]
api_key = "prowlarr/api-key"
```

The API key itself is in the Mudos SecretStore under `prowlarr/api-key` and
does not appear in the TOML. The temporary RTF is superseded and may be
removed by the operator after confirming the migration.

The existing host-networked Questarr container can reach the existing
downloaders at `http://127.0.0.1:9091/transmission/rpc` and
`http://127.0.0.1:6789/xmlrpc`. Credential probes from inside the container
succeeded. Once Questarr authentication is available, configure Transmission
with label `questarr` and NZBGet with category `questarr`; Mudos discovery
maps both markers to `origin=questarr`.
