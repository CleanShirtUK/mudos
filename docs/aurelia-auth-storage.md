# Experimental Aurelia authentication storage policy

This policy applies only to the opt-in `steam-aurelia` backend. It does not
change the current Steam provider or its SteamCMD configuration.

The backend defaults off through the existing provider configuration boundary.
The explicit opt-in setting is `providers.steam_aurelia.enabled = true` in
`/etc/lulu/provider-services.toml` (or the normal user/development override).
Do not set it for appliance activation until the controlled gates below pass.

## Ownership and location

Aurelia's sole persistent configuration/session directory is:

```text
${XDG_CONFIG_HOME:-~/.config}/lulu/providers/steam-aurelia/aurelia
```

The directory is created with mode `0700` and belongs to the `lulu` service
user. Aurelia itself is the only component that reads or writes its `config.json`,
`session.json`, keyring key, and daemon state. The opt-in Acquisitiond adapter
invokes Aurelia through its CLI/daemon and consumes secret-free health/status
responses. Sessiond is not wired to Aurelia yet. Neither service may parse,
copy, back up, or serialize the session token. The configured
`steam_library_path` must explicitly be Mudos' canonical Steam library before
any future mutation test.

On the first Aurelia command, the adapter creates a minimal config with that
canonical library path, cloud sync off, and Windows-Steam discovery off. An
existing config is never rewritten; if its library path differs or it is
malformed, the adapter fails closed for operator review. The config file is
mode `0600`.

## Credential introduction and expiry

Credentials must eventually enter through Aurelia's supported interactive/QR
or machine-readable Guard flow in an explicitly approved authentication
session. They must not be placed in Mudos provider TOML, source, logs, command
arguments, SteamCMD configuration, or another provider's secret store. Mudos
CredentialBroker may present user challenges, but the secret value is handed
only to Aurelia's authentication interaction and is never retained by
Acquisitiond/Sessiond.

Authentication health is secret-free: `authenticated`, `unauthenticated`,
`authentication-required`, `authentication-expired`, or `unavailable`. Expiry
does not trigger silent SteamCMD fallback; Mudos reports authentication needed
and waits for an explicit Aurelia reauthentication. Fresh installation starts
unauthenticated with an empty private directory. No credentials/session are
copied from Steam GUI, SteamCMD, or an old Mudos install.

SteamCMD username/password settings remain owned by the current provider while
that provider is selected. They become obsolete only after a separately
approved migration and parity gate; this experimental backend neither reads
nor deletes them.

## Experimental POC plaintext-session decision

Steam refresh/session tokens are sensitive authentication material. The
experimental Aurelia backend currently accepts Aurelia's own plaintext session
persistence as a deliberate temporary trade-off. A protected session-storage
implementation may be introduced later, but it is not a prerequisite for
proving Aurelia's Steam backend functionality.

This exception is limited to the initial experimental POC. Keep the session
directory private to `lulu` (mode `0700`) and `session.json` mode `0600`. Do not
log session contents, pass tokens in command-line arguments or ordinary
environment variables, or copy session state into Mudos databases/backups.
Authentication state belongs only to Aurelia. Existing SteamCMD passwords and
Steam client tokens are not read, reused, imported, migrated, or deleted; the
production Steam provider and its separate authentication state remain intact.

The session includes the Steam CM refresh token and may also include a web
token. Do not enable Aurelia by default. This plaintext persistence decision is
not an approval for production replacement; any later security gate may require
a protected session-storage backend before promotion.
