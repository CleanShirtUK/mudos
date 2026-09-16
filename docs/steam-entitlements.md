# Steam entitlement configuration

Lulu reads Steam ownership directly from Valve's `GetOwnedGames` endpoint.
Create `~/.config/lulu/providers/steam.json` with:

```json
{
  "steam_id": "76561198000000000",
  "api_key_file": "~/.config/lulu/providers/steam-web-api-key",
  "timeout": 8
}
```

Put the Web API key in the referenced file with mode `0600`. The key is never
stored in the JSON configuration or in the catalogue. If Valve returns private,
malformed, empty, or unavailable ownership data, Lulu keeps the last valid
entitlement snapshot. Steam manifests remain authoritative for installed state.

Acquisition platform capability is resolved separately from the user-facing
`Steam` platform label. Lulu queries Steam AppDetails and caches the normalized
result in `steam-platforms.json`: Linux is preferred when available; otherwise
Windows is selected for Proton; macOS-only or unresolved titles fail closed.
