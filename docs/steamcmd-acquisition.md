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
provider configuration supplies another path. It passes only the account name
and relies on SteamCMD's own cached authentication; it never reads or copies
credentials. Cancellation is deliberately unsupported until separately
characterized.
