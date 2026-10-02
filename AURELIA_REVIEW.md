# EXTREMELY EARLY DEVELOPMENT BUILD — NOT FOR GENERAL USE

This document covers the Mudos Aurelia review build. It is based on the
physically tested checkpoint `checkpoint/aurelia-only-steam-56827df-20261002`
(`56827df68083d2f688b2c6827280d38c270fd257`). The checkpoint itself is
unchanged; this branch contains installation, packaging, audit, and review
documentation changes only.

## Mudos and the provider flow

Mudos is a Linux gaming platform and console UI. Providers expose authentication,
library, and acquisition capabilities; Mudos maintains the catalogue, user
interface, acquisition lifecycle, canonical library layout, and launch
supervision.

```text
Aurelia → Mudos Installable → Acquisitiond → canonical Steam library
        → Mudos UI → Sessiond → Aurelia → Proton/Wine → Gamescope
```

- **External dependency:** Aurelia is not bundled. `packages/aurelia/PKGBUILD`
  fetches upstream release/tag **v0.1.38** and verifies executable SHA-256
  `3b67cf258100d466a75095c60b3500dfe1803cf1d803e1f414f1cf53d8c80a8e`.
  `scripts/provision-aurelia.sh` builds and installs that package through
  `makepkg` and `pacman`, then checks the installed package identity. This
  preserves Aurelia's separate source, licensing, and release lifecycle.
- **Version display:** the official v0.1.38 release executable itself prints
  `aurelia 0.1.37` for `--version`. The upstream release tag and pinned binary
  checksum define the dependency identity; the executable's reported version
  string is an upstream presentation distinction, not a different artifact.
- **Clean install:** `./install-mudos.sh` builds/verifies/activates the Mudos
  immutable release, provisions the pinned Aurelia package as an external
  dependency, configures `LULU_AURELIA_EXECUTABLE=/usr/bin/aurelia` in the
  Sessiond, Consoled, and Acquisitiond units, enables
  `providers.steam_aurelia`, and initializes private Aurelia configuration
  under Mudos' provider state. Initialization points Aurelia at Mudos'
  canonical Steam library and does not authenticate. The existing separate
  Aurelia authentication flow remains responsible for Steam login.
- **Entitlements and Installable:** the Aurelia source reads owned AppIDs from
  Aurelia after authentication and maps them to `steam-aurelia` entries in
  Installable. Before authentication, the provider is registered and health
  reports an authentication-required/unauthenticated state; no entitlements
  are fabricated.
- **Acquisition:** Acquisitiond registers the Aurelia executor. It maps
  download progress and cancellation to Mudos jobs and reconciles the catalogue
  after completion. Installed content uses the canonical Mudos Steam library,
  not a separate Aurelia library.
- **Launch and graphics:** the real Mudos UI routes Aurelia library entries to
  Sessiond. Sessiond supervises the Aurelia-launched process. Mudos passes its
  validated graphical environment to the wrapper using Aurelia's `--script`
  facility, before Proton/Wine and Gamescope launch.

This path has no Steam client or SteamCMD dependency and requires no SteamCMD
credentials. Legacy SteamCMD implementation files remain available in the
source tree for separate legacy development, but the Aurelia provider does not
register or invoke them. They are excluded from the installed release payload.

## Installation and verification

On a clean supported Arch-based Mudos appliance, install from a clean committed
review checkout using the normal installer:

```sh
./install-mudos.sh
```

The installer must run with the repository's documented privilege escalation
and supported host prerequisites. It provisions Aurelia externally from the
pinned release URL/checksum, sets the executable path, writes the provider
enablement without replacing unrelated provider settings, and initializes the
Aurelia library config as the Mudos user. Authentication remains a separate
user action. No legacy Steam client or SteamCMD is installed.

For a reproducible inactive Mudos candidate, use the canonical release builder
on the canonical build host from a clean committed review branch:

```sh
python3 scripts/release.py build --release-dir /opt/lulu/releases/aurelia-review-COMMIT
python3 scripts/release.py verify --release-dir /opt/lulu/releases/aurelia-review-COMMIT
```

Archive the verified immutable release directory with this review document and
publish its SHA-256. Do not activate it over another installation for review.

## Limitations and physical checkpoint evidence

Known limitations include DLC/update handling, adoption of an acquisition
already active across restart, games requiring Steam integration/DRM, and
compatibility-mode restoration.

The following observations were supplied for the checkpoint and were not
retested for this packaging pass:

- **BEEP:** successful launch through the real Mudos UI, including
  launcher-first behavior.
- **Super Meat Boy:** successful launch and noticeably faster startup than the
  previous Steam integration; it returned to Mudos, which remained in
  compatibility mode.
- **Dead by Daylight:** reached the main game window after its anti-cheat and
  launcher sequence, then reported Steam offline.
- **Rocket League:** launch stalled; cause undetermined.
- **Controller:** preliminary successful gameplay/navigation, not formal
  acceptance.

These observations do not imply broad compatibility or fresh-machine game
validation.
