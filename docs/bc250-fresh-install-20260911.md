# BC-250 Fresh-Install Bring-Up

## Confirmed Working Tonight

The fresh provisioning path and the previously validated hardware baseline are
separate. On the real BC-250, Gamescope uses RADV/GFX1013 and the connected
display is `DP-1` at 1920x1080@60. The normal `lulu-session@2.service` path
starts Mudos after Steam initialization; controller navigation, InputPlumber
`InterceptMode=1`, user D-Bus, PipeWire/WirePlumber, seatd, and audio through
the DP-to-HDMI adapter work. Maintenance VT and SSH recovery remain available.

The generic installer no longer assumes `HDMI-A-1`: it honors
`LULU_OUTPUT_CONNECTOR` in `/etc/lulu/presentation.conf`, otherwise discovers
one connected DRM connector. Multiple connected outputs require an explicit
choice and are reported as an installation verification failure.

## Provisioning Fixes

| Defect | Permanent source fix |
| --- | --- |
| CHECKPOINT `=` versus `:` | Installer parses canonical `commit=` and `tag=` fields; metadata is no longer duplicated in shell constants. |
| RapidYAML preflight | Official packages and fallback packages are separate; RapidYAML 0.11.1/Python 3.14 remains on the payload fallback path. |
| Broken `current` link | Releases are linked as `releases/<release>` and verification resolves the link below `/opt/lulu/releases`. |
| Hardcoded HDMI connector | Explicit override or deterministic DRM discovery with ambiguity failure. |
| Transient user runtime | Provisioning enables linger and orders `user-runtime-dir@958.service` and `user@958.service` before the console. |
| Missing InputPlumber group | Installer creates the system `inputplumber` group and adds `lulu`; it never grants `wheel` or weakens Polkit. Hardware verification performs the property operation as `lulu`. |
| Missing Steam helper | Both executable bootstrap scripts are deployed and covered by the payload manifest. |
| Window-selection deadlock | Session D-Bus remains responsive while Gamescope discovery runs in a task. The bridge publishes the actual Mudos shell PID, and selection targets that PID rather than an arbitrary descendant. |
| No-controller boot | Session startup no longer requires a persistent composite; the existing event-driven reconnect path remains in place. Identity/player reassignment remains deferred. |

## Temporary Fixes Replaced

The bring-up required manually enabling linger, confirming the user runtime bus,
creating `inputplumber`, adding `lulu` to it, copying `scripts/steam-bootstrap.sh`,
and completing Steam's first-run initialization. Those are now encoded as
provisioning or explicit operator steps; mutable machine state is not copied
into the payload.

## Steam First Boot

Steam authentication and credentials are deliberately not automated. On a
fresh install, Steam may initialize its client/runtime and show
`-child-update-ui` before the Mudos shell is useful. The operator must launch
Steam through the provisioned session, complete all first-run updates and
login/onboarding, then reboot or restart the normal session before accepting
the appliance. This is a required first-boot setup state, not a game test.

## Deferred Tomorrow

No games or BIOS files are installed on this BC-250. Steam game launch/return,
ROM/emulator launching, RetroArch, PCSX2, Dolphin, multiplayer, Guide/Provider
Menu on this exact fresh machine, reconnect/reassignment acceptance, and Switch
remain untested and must not be marked PASS from `lulu-test-env` evidence.

The remaining controller concern is physical identity preservation across
recreated composites and transient InputPlumber races. The bounded change made
tonight only permits shell boot with no active controller; reconnect handling
and authorization should be tested manually before further redesign.
