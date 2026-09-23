# Epic Games Store provider

The Epic provider uses Legendary for authentication, ownership, acquisition,
launch metadata, and ephemeral launch credentials. Windows execution is handed
to UMU with a per-game prefix under `Games/Prefixes/umu/egs`.

## Validation status

- Epic acquisition and uninstall complete through the controller lifecycle.
- Acquisition reconciliation self-completes without a service restart.
- Legendary returns a fresh non-empty exchange credential for each launch.
- Mudos passes the normalized Legendary arguments intact to UMU.
- Launch credentials are not persisted and `AUTH_PASSWORD` is redacted from
  process logs and public process results.
- Direct Legendary → UMU and Mudos → UMU reproduce the same result for the
  tested title: `Epic Login: InvalidAuth`, followed by an EOS device-login
  prompt.

The tested title therefore has an unresolved EOS automatic-authentication
compatibility issue despite receiving correct fresh Epic launch credentials.
It is not yet established whether this is title-specific or affects other
EOS-protected Epic games. A second Epic title is the next control test.
