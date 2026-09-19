# Provider and Service Configuration

`lulu.provider_config.ProviderConfigurationService` is the single ordinary
configuration boundary for optional external services. It loads, in order:

1. built-in safe defaults;
2. `/etc/lulu/provider-services.toml` (site configuration);
3. `$XDG_CONFIG_HOME/lulu/provider-services.toml` (user/runtime configuration);
4. the file named by `LULU_PROVIDER_CONFIG` (development/testing override).

Later layers override earlier layers by table/key. Missing or malformed layers
are non-fatal; malformed layers are ignored and optional providers remain
`disabled` or `unconfigured`.

The file contains ordinary values only. Secret-shaped keys such as `password`,
`token`, `api_key`, and `client_secret` are rejected. Providers may refer to an
encrypted `SecretStore` value with `namespace/name` under a `secrets` table.
The secret store remains backed by `systemd-creds`; values are never exposed by
configuration diagnostics.

Use `config/provider-services.toml.example` as the placeholder-only template.
`scripts/provision-provider-config.sh` creates the user file if absent and
never overwrites it.
