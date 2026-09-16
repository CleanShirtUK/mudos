# SteamCMD acquisition adapter

`SteamCmdExecutor` is registered by `lulu-acquisition.service` as the
`steam` executor with concurrency one. It is the only component that knows
about SteamCMD output or command-line policy.

The parser maps startup and `0x3 reconfiguring` to `STARTING`, `0x61
downloading` to `TRANSFERRING`, and `0x101 committing` to `FINALIZING`.
Completion requires both an explicit `Success! App ...` result and exit code
zero. An already-up-to-date result completes without fabricating transfer
progress. Manifests are never used as completion evidence.

SteamCMD's progress numerator and denominator are install/staging counters,
not guaranteed network byte counters. They populate the existing normalized
byte fields only during `TRANSFERRING`. Commit progress is discarded so a
99%-downloaded job cannot appear to fall to 15%; entering finalization clears
the transfer fields atomically and finalization progress is unknown.

Platform policy is explicit AppID metadata loaded from
`$LULU_STEAM_PLATFORM_METADATA`, or by default
`$XDG_CONFIG_HOME/lulu/steam-platforms.json`. Values are `windows` or `linux`.
Unknown metadata fails safely. Windows adds
`@sSteamCmdForcePlatformType windows`; Linux uses SteamCMD's native default.

The executor uses the canonical `PATHS.data_home / "Steam"` library unless a
provider configuration supplies another path. SteamCMD itself is resolved in
this order: an explicit `LULU_STEAMCMD` override, then the Mudos-provisioned
`/var/lib/lulu/steamcmd/steamcmd.sh`. It never searches developer or temporary
directories, and an unavailable executable is normalized as
`steamcmd-unavailable` before process creation.

`scripts/provision-steamcmd.sh` downloads the official Valve Linux SteamCMD
archive, installs it beneath `/var/lib/lulu/steamcmd` as `lulu:lulu`, and runs
`+quit` without a login command to verify startup. Rerunning it is a no-op when
the canonical executable is present. `LULU_STEAMCMD_SHA256` can pin the
download when an operator has a verified Valve archive digest. The provisioner
does not inspect, copy, or migrate the experimental SteamCMD cache.

SteamCMD still requires its own authenticated session. The executor passes
only the account name and relies on SteamCMD's cache; graphical Steam login is
not sufficient. Cancellation is deliberately unsupported until separately
characterized.
