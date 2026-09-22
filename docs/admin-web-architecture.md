# Mudos Admin web surface

The Admin service remains a small authenticated, server-rendered Python
application. It uses the existing `SecretStore`, provider configuration
boundary, and service health clients; this document describes the user-facing
information architecture rather than changing ownership of any setting.

## Route/settings audit

| Previous route | Purpose | Editable settings/actions | Audit result |
| --- | --- | --- | --- |
| `/` | Dashboard | Service table, deployment/host details, service links | Duplicated `/services` status and links; now Overview only |
| `/providers` | Provider index | Provider status, Edit, Test | Redirects to canonical `/integrations` |
| `/provider/<id>` | Provider form | Raw provider keys and secret fields | Redirects to `/integration/<id>` |
| `/test/<id>` | Provider test | Test result | Retained as a bookmark-compatible endpoint |
| `/services` | Service index | Service status and Open UI links | Canonical operational links; no editing |

The old forms exposed implementation names such as `endpoint`, `host`,
`connections`, `rpc_password`, and raw provider IDs. Secret values were not
rendered, but their names were exposed. Editing is now centralized under
`/integrations`; Overview and Services contain links/status only.

## Canonical settings owners

| Integration | Canonical route | User-facing settings |
| --- | --- | --- |
| Transmission | `/integration/providers.torrent` | Username, connection address, password replacement |
| NZBGet | `/integration/providers.usenet` | Server address, Web UI username, password replacement |
| Usenet account | `/integration/providers.usenet.server` | Server address, port, encryption, connections, username/password |
| Prowlarr | `/integration/providers.prowlarr` | Server address, API key |
| RomM | `/integration/providers.romm` | Server address and private credential where configured |
| Steam / Game metadata | `/integration/providers.steam`, `/integration/metadata.igdb` | Only fields present in authoritative configuration |
| Questarr | `/services` | Operational status and Open link; no duplicate downloader credentials |

Transmission, NZBGet, and Prowlarr credentials remain SecretStore-backed.
Blank secret fields preserve existing values. Existing values are never put in
HTML. Save, Test connection, and Open Web UI use the same visual action order
where the service has a Web UI.

## Shared design system

`admin_web.py` defines shared CSS tokens and components for the shell, cards,
setting rows, badges, notices, actions, help affordances, and responsive
layout. The visual language follows Mudos' dark surfaces, cool blue accent,
restrained translucent cards, generous spacing, and clear success/warning
states without attempting to reproduce QML effects.

Help uses native `<details>` controls with keyboard/touch support and visible
supporting text. Focus outlines, real labels, actual buttons, responsive
stacking, and non-colour status indicators are provided without JavaScript.

## Operational boundary

The Admin server remains bound and authenticated as before. Service links are
operational shortcuts only. Technical identifiers are available behind the
`Technical details` disclosure on integration pages rather than being used as
normal labels.
