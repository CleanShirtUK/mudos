# Mudos browser and Stores

## Trusted web credentials

The named `mudos-browser` WebEngine profile is persistent, with storage below
`QStandardPaths::AppDataLocation/browser/storage` and forced persistent
cookies. Authentication state remains WebEngine-owned across browser close and
shell restart; autofill is only a recovery path when a login form remains.

Mudos-owned web credentials are separate from provider integration credentials.
No Store currently opts into trusted credential capture. A custom Store URL is
not trusted merely because it resembles a local service origin.

The generic browser adapter detects ordinary username/password controls only
while an authorised profile is active. Backend retrieval, save, replacement,
and clear operations validate both profile ID and exact origin. Autofill sets
normal HTML values and dispatches input/change events without opening the OSK
or activating Login. A candidate is saved only after a submitted login form
leaves the login state; failed forms leave the last known-good values intact.
Requests from page origins to the local credential bridge are rejected.

The Store domain on Home keeps the existing **Available to Download** launch
card and adds sibling Store launch cards. Steam is a fixed card; custom cards are
ordinary user preferences containing a stable UUID, normalized HTTP(S) URL,
and hostname display name. Preferences are stored by the native shell with
`QSettings` under the Mudos/lulu user configuration. They are not provider
credentials and never enter SecretStore.

The expanded Store surface remains exclusively the combined Steam/RomM
download catalogue; Store cards are never inserted into that catalogue.

The browser is a Mudos-owned `QtWebEngine` QML `WebEngineView`, initialized by
`QtWebEngineQuick::initialize()` in the existing shell process. Its named
persistent profile is `mudos-browser`; profile storage is below
`QStandardPaths::AppDataLocation/browser/storage`. There are no tabs. HTTP and
HTTPS new-window requests reuse the current view; unsupported schemes are
reported rather than passed to the desktop.

The native ControllerBridge remains above the web content for Guide and global
Downloads. Opening a browser marks the session delegated surface as `browser`
and enters the existing InputPlumber compatibility profile; closing it restores
the exact prior input mode. Browser Back uses WebEngine history when available,
otherwise it closes the browser and restores Home. Guide gets a browser-scoped
Quit action that clears the delegated surface; the shell then releases the page,
restores input ownership, and keeps the persistent profile intact. The existing
managed credential/OSK flow is reused for Add New Store URL entry.

## Reconnaissance

The target host runs Qt 6.11.2. CachyOS provides `qt6-webengine` 6.11.2-1
(with `qt6-positioning`, `qt6-webchannel`, and `re2` dependencies); it is now
installed for the development runtime. `qt6-webview` is also available, but
WebEngine Quick is preferred because it supplies QML composition, navigation,
persistent profiles/cookies/local storage, new-window requests, loading/error
signals, and Chromium input/focus behavior in one API.

Qt's WebEngine Quick Nano Browser was used as the conceptual donor for the
profile, URL, navigation, loading/error, and new-window lifecycle. Plasma
Bigscreen `webapp-viewer` and KDE Angelfish were inspected as TV/browser
references for focus, fullscreen/lifecycle, URL handling, bookmarks, and
error boundaries. Their Plasma/Kirigami runtime architectures are not imported.

The only native lifecycle change is WebEngine Quick initialization before the
existing single `QGuiApplication`; no second application or desktop session
is created. Hardware video decode is intentionally out of scope.
