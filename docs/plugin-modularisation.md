# Mudos component and plugin modularisation

This checkpoint establishes the common descriptor boundary for future OOBE,
Admin, Store, and provisioning work. A **component** is something the user can
enable or configure. A **plugin** is only one possible deployment mechanism.

## Component registry

`lulu.plugins.ComponentRegistry` combines:

- built-in providers: `retroarch`, `dolphin`, `pcsx2`, and `eden`;
- installable plugin components: Steam, RomM, and Lutris;
- service/deployment components: Transmission and NZBGet.

Every descriptor has an ID, name, description, kind, enabled/installed state,
capabilities, directional `requires_all`/`requires_any` dependencies,
configuration fields, secret slots, provisioning requirements, Store cards,
service contributions, and provider IDs. `GetComponentRegistry` exposes the
same safe metadata to future setup/Admin clients. Secret values are never part
of the response.

The supported kinds are `builtin_provider`, `plugin`, and `service`. A built-in
provider can later be promoted to a plugin without changing the external
descriptor or provider interface.

## Dependency direction

Dependencies are outgoing requirements only. The resolver is shared by all
component kinds and reports unsatisfied alternatives without embedding UI
prompts. Transmission and NZBGet remain independent acquisition services.

## Configuration and secrets

Configuration metadata supports text, URL, username, password/secret, API key,
integer, boolean, and choice fields with labels, descriptions, required flags,
safe defaults, validation hints, and choices. `PluginSecretBoundary` provides
plugin-owned SecretStore slots without exposing values. SteamCMD now prefers
the `steam/username` SecretStore slot and already consumes `steam/password`
automatically; Steam Guard values continue through the ephemeral credential
broker and are cleared rather than persisted.

## Store and service contributions

The native shell reads normalized Store-card contributions and StoreHome renders
them alongside user bookmarks. Transmission and NZBGet contribute service
metadata through the generic component registry.

## Hardcoding audit

| Area | Current assumption | Classification / migration |
| --- | --- | --- |
| Steam provider, SteamCMD, Steam manifests | Valve protocol and catalogue identity | Legitimate Steam plugin/provider adapter |
| RomM API, pairing, content sets | RomM protocol and provenance | Legitimate RomM adapter; generic acquisition boundary consumes it |
| Lutris installer/runtime | Lutris API, runner and registration semantics | Legitimate Lutris plugin adapter |
| Transmission/NZBGet RPC | Downloader protocols | Service/plugin adapters; JobManager lifecycle is generic |
| StoreHome Steam cards | Product identity in core QML | Removed; declarative component cards supply them |
| Component dependencies and setup fields | Previously absent/generic flags only | Unified descriptor and resolver added |
| Core catalogue identity | Steam/RomM compatibility joins | Retained because canonical identity/provenance rules are authoritative |
| Sessiond `RequestSteam*`, Guide targets, Admin labels | Existing public compatibility contracts | Provider-specific branches remain until generic delegated/provider APIs are proven |
| Emulator providers | No plugin boilerplate | Built-in component descriptors with future promotion path |

Provider-specific protocol logic remains in adapters. Core consumes normalized
capabilities, catalogue records, acquisition jobs, delegated launch contexts,
and component metadata rather than selecting a deployment mechanism itself.

## Proof cases

The framework tests include both a synthetic built-in descriptor and a synthetic
third-party plugin. Both use the same dependency resolver, configuration schema,
secret declaration, and Store-card contribution model. Disabled components lose
their contributions safely, and an unknown plugin can be added without editing
Home/Store provider lists.

Steam GUI authentication was inspected conservatively: the installed client
does not expose a documented supported credential-injection path that Mudos
can safely automate. Steam GUI login therefore remains interactive; automatic
SteamCMD authentication uses SecretStore username/password and keeps Guard
codes ephemeral.
