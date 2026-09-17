# Display Settings

Display Settings uses DRM/KMS connector state from `/sys/class/drm` and
`modetest -c` for the authoritative connected-output and advertised-mode
list. QML receives normalized connectors, modes, preferred mode, and precise
fractional refresh values through Consoled and the UI bridge; it does not run
display commands itself.

Lulu persists the preferred connector and mode in
`~/.config/lulu/display-state.json`, including `requested` and `known_good`.
The connector name is currently the practical stable identity because this
device exposes no more useful monitor identity through the available DRM
interfaces. A missing preferred connector is retained in policy while the
session safely selects a connected fallback; the preferred connector is used
again when it returns.

Apply restarts the Lulu Gamescope session. The session launcher consumes the
policy as `--prefer-output`, `--output-width`, `--output-height`, and
`--nested-refresh`; Gamescope has no `--output-refresh` option. Resolution and
refresh choices are restricted to modes advertised by the selected connector.

Validated on the connected DP-1 display with 1920×1080 at 144.01 Hz and
1680×1050 at 59.88 Hz. Hotplug fallback and invalid-mode handling are covered
by the display-manager tests. HDR, VRR, color management, custom modelines,
desktop monitor arrangement, and live mode changes without a session restart
are intentionally out of scope.
