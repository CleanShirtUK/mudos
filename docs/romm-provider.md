# RomM Consumer Boundary

Mudos consumes RomM as a read-only provider. Mullock owns Steam ownership
synchronization, creation of the small Steam manifests, and RomM scanning.
Mudos does not access RomM filesystem paths, scanner endpoints, sockets, or
administrative credentials.

## Configuration and API

The optional configuration is read from
`$XDG_CONFIG_HOME/lulu/providers/romm.json` (override with
`LULU_ROMM_CONFIG`). It contains the RomM server URL and either a bearer
client/access token or basic-auth credentials. Secrets are never logged.

The client uses only normal RomM API endpoints:

- `GET /api/platforms`
- paginated `GET /api/roms` with `with_files=true`
- authenticated content requests only for Steam identity manifests

ROM pages are fetched until the reported total is reached or a short page is
returned. The complete snapshot is parsed before catalogue reconciliation; a
failed or malformed refresh leaves the previous RomM snapshot intact.

## Identity and manifests

Normal RomM records use `romm:<record-id>` as their provider-local identity.
Steam manifest records are promoted to the stable Steam identity
`steam:<appid>`. RomM record IDs and content filenames are retained only as
provider/content metadata. Multiple RomM records describing one AppID are
deduplicated before storage, including managed and manually-created records.

Steam manifests are data, not instructions. Mudos accepts schema `1`,
provider `steam`, and a positive decimal `id`; unknown administrative fields
are ignored. URI, command, executable, and shell fields are never accepted or
executed.

## Availability

Catalogue rows retain the existing installed semantics. RomM-only rows use
`availability_state=available`, `install_state=available`, and are not
launchable. A RomM Steam AppID matching the local Steam provider is represented
by the existing `steam:<appid>` row and remains `installed` and launchable.
Rows previously supplied by RomM become unavailable when a successful fresh
snapshot no longer contains them. Installation is deliberately not part of
this boundary.
