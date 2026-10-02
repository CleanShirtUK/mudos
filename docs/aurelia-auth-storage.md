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

## Keyring policy gate

Aurelia encrypts its session with an OS keyring when available, but its upstream
fallback is an owner-only plaintext session file. Before authentication is
enabled in an appliance service, confirm the `lulu` user's Secret Service
availability across reboot/headless operation and either require encryption or
explicitly accept/document upstream's `0600` fallback. Never weaken directory
permissions or copy the session into Mudos databases/backups. This keyring
deployment decision remains an authentication-test prerequisite.
