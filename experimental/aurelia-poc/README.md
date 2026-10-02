# Aurelia Steam-backend proof of concept

This is an isolated, non-production adapter prototype. It does not alter or
register with Mudos' production Steam provider. It shells out to Aurelia's
CLI/JSON surface and preserves the upstream command output and exit status. No
credentials are accepted by this adapter. The expanded 2026-10-02 feasibility,
authentication, storage, Acquisitiond, lifecycle and Proton assessment is in
`FINDINGS.md`.

## Setup and safe inspection

Build upstream Aurelia separately, then prepare a private config directory and
point it at the existing Mudos library:

```sh
mkdir -m 700 -p /path/to/aurelia-poc-config
cat > /path/to/aurelia-poc-config/config.json <<'EOF'
{"steam_library_path":"/home/lulu/Games/Executables/steam",
 "proton_version":"experimental",
 "enable_cloud_sync":false,
 "windows_steam_discovery_enabled":false}
EOF
chmod 600 /path/to/aurelia-poc-config/config.json
python experimental/aurelia-poc/adapter.py --binary /path/to/aurelia \
  --config-dir /path/to/aurelia-poc-config snapshot --app-id 40800
```

Run it as the Steam-library owner (`lulu` on this appliance) with access to the
helper file and config directory. The adapter disables Aurelia's daemon
auto-spawn and uses its own socket path.
By default only `snapshot` is allowed. `install`, `cancel-install`, `launch`,
and `stop` require explicit `--allow-write` / `--allow-launch` acknowledgments;
they are intentionally not exercised in this POC. In particular, Aurelia
installation and launch can edit Steam-managed files, perform account-authenticated
operations, or start/stop Steam processes.

The tested upstream was `Drackrath/Aurelia` commit
`50c44d33b97f4aee6fe694e90c464951970d9fd8` (v0.1.37). The config above is a
test fixture, not production configuration. Do not point this tool at real
credentials/config without reviewing Aurelia's behavior first.

See `FINDINGS.md` for architecture, results, risks, and recommendation.

The separate Mudos-side opt-in boundary now lives in
`src/lulu/plugins/steam/aurelia.py`. It is registered under the distinct
`steam-aurelia` identity only when `providers.steam_aurelia.enabled = true` in
the existing provider-services configuration. Its auth/session storage policy
is documented in `docs/aurelia-auth-storage.md`. It is not wired into the
production Steam launch dispatch; Sessiond launch ownership and Gamescope
handoff remain a follow-up integration gate.
