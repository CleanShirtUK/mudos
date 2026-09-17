# Internet settings

Internet settings are owned by the Mudos shell but NetworkManager remains the
authority. `src/lulu/network_manager.py` is a small system-bus D-Bus adapter;
Consoled exposes its normalized JSON through `GetNetworkState`,
`SetWifiEnabled`, `ConnectWifi`, `DisconnectWifi`, and `ForgetWifi`. The
existing localhost shell bridge carries those intents to `InternetSettings.qml`.
QML never executes a networking command.

The normalized model contains adapter availability, Wi-Fi enabled state,
`connected`/`disconnected`/`disabled` state, current interface and SSID, and
AP rows containing SSID, signal percentage, open/secured state, current state,
and saved state. The page refreshes at a modest interval while open so AP and
connection changes become visible without blocking controller input.

Selecting an unsaved secured AP opens a `TextInput` and requests the existing
Mudos OSK boundary. The password is sent only in the transient D-Bus request
to NetworkManager; Mudos does not persist it. NetworkManager creates and owns
the saved connection profile and secrets. Saved profiles can be forgotten from
the same controller list. Open connections, known connections, radio enable /
disable, disconnect, and failure responses use the same boundary.

The narrow Polkit rule in
`packaging/polkit-1/rules.d/49-lulu-network.rules` grants only the `lulu`
console account the four NetworkManager actions required by this page:
Wi-Fi radio control, network control, system profile modification, and Wi-Fi
scan. It grants no root command execution to QML.

The OSK service waits for Xwayland before starting, avoiding the startup race
that otherwise made secured-network onboarding unavailable. No boot-specific
network behavior was added.

Physical-controller validation passed in the development runtime: AP discovery,
radio toggle, secured onboarding through the OSK, connect/disconnect/reconnect,
LAN removal with Wi-Fi continuity, Back navigation, and responsive state
updates. Ethernet remains represented by NetworkManager but is not configured
by this page. VPN, static IP/DNS, Bluetooth, and advanced networking remain out
of scope.
