# Isolated host Steam runtime

Mudos starts `lulu-steam-runtime.service` for the appliance session. The
service owns Xvfb `:99` and the normal `/usr/bin/steam` client; Steam receives
only that display plus the active `lulu` session's runtime directory. The
Gamescope display and its Wayland variables remain exclusive to Mudos,
Aurelia, Proton, and games. Steam stays alive across Home/game transitions and
is stopped before Xvfb when the Mudos session ends.

The supervisor reports ready only after the host Steam connection log confirms
an authenticated `LogOnResponse 'OK'`/`Logged On`. It does not store or enter
credentials. If authentication needs user interaction, start Xvfb and Steam
temporarily on the isolated display (never use the Mudos `DISPLAY`):

```sh
sudo systemctl stop lulu-steam-runtime.service
runtime=$(loginctl show-user lulu --property=RuntimePath --value)
sudo -u lulu /usr/bin/Xvfb :99 -screen 0 1280x720x24 -nolisten tcp -noreset &
sudo -u lulu env DISPLAY=:99 XDG_RUNTIME_DIR="$runtime" \
  DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime/bus" /usr/bin/steam
```

Complete any required sign-in on the virtual display using an appropriate
remote X11 viewer or local maintenance workflow. Do not set `DISPLAY=:99` in
Sessiond, Acquisitiond, Aurelia, or the graphical launch context.
