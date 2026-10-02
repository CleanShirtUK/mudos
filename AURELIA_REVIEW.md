# Mudos × Aurelia — early technical review

This is an early technical review of Mudos, not a general Mudos release. The
implementation reviewed here is based on the physically tested checkpoint
`checkpoint/aurelia-only-steam-56827df-20261002`
(`56827df68083d2f688b2c6827280d38c270fd257`). This document is review material;
it does not change the integration or make the checkpoint a turnkey installer.

## What Mudos is

Mudos is a Linux gaming platform and console UI. Providers expose library,
authentication, and acquisition capabilities to Mudos services; Mudos keeps
the user-facing catalogue and install/acquisition lifecycle, and delegates
provider-specific work to external tools where possible.

## Aurelia integration path

The intended flow is:

```text
Aurelia → Mudos Installable → Acquisitiond → canonical Steam library
        → Mudos UI → Sessiond → Aurelia → Proton/Wine → Gamescope
```

- **External dependency:** Mudos does not bundle Aurelia source. `packages/aurelia/PKGBUILD`
  fetches upstream Aurelia release `0.1.38` and pins its binary SHA-256 to
  `3b67cf258100d466a75095c60b3500dfe1803cf1d803e1f414f1cf53d8c80a8e`.
  `scripts/provision-aurelia.sh` builds and installs that package. This keeps
  Aurelia independently maintained and upgradeable under its own license and
  release process.
- **Authentication:** Aurelia owns Steam authentication and session state.
  Mudos calls Aurelia’s CLI/status surface; credentials are not placed in
  Mudos provider TOML. No Steam client or SteamCMD is needed for the Aurelia
  path.
- **Entitlements and Installable:** the Aurelia entitlement source queries
  Aurelia’s library and maps entitled Steam AppIDs into Mudos’ catalogue.
  Installable projects those entries as `steam-aurelia` items.
- **Acquisition:** Acquisitiond registers the Aurelia acquisition executor.
  It maps Aurelia progress and cancellation into Mudos download jobs and
  reconciles the canonical catalogue when a job completes. Steam content is
  installed into the canonical Steam library layout, rather than a separate
  Aurelia library.
- **Launch and graphics:** the real Mudos UI sends `steam-aurelia:<appid>` to
  Sessiond. Sessiond invokes Aurelia for the launch and supervises the process
  lifecycle. `scripts/aurelia-graphical-launch.py` is passed through Aurelia’s
  `--script` facility; it applies Mudos’ validated live graphical-session
  context before executing Aurelia’s resolved game command under Proton/Wine
  and Gamescope. The checkpoint includes the launch-scoped graphical context
  handoff and the direct Consoled route to Sessiond.

The checkpoint contains no Aurelia source, copied Aurelia executable, Steam
client binary, or SteamCMD binary. The upstream executable is downloaded by
the package recipe at provisioning time. Legacy Steam/SteamCMD code remains in
the wider Mudos repository for unrelated compatibility/history, but is not
registered or required by the Aurelia-only path. The release payload does
include the legacy SteamCMD provisioning script and developer/test utilities
as source files; the audit found no Steam/SteamCMD executable binary in the
payload. These files are not dependencies of this integration, but are worth
noting to reviewers.

## Installation and reproducibility status

Build the pinned external Aurelia package on the supported Arch-based target
with `makepkg` available, then install it with the normal provisioning script:

```sh
sudo ./scripts/provision-aurelia.sh
```

Before authentication, configure the Mudos provider setting
`providers.steam_aurelia.enabled = true` in the normal provider-services
configuration and use Aurelia’s own authentication flow. The checkpoint’s
default is disabled. **Important:** at this checkpoint the top-level Mudos
installer does not invoke `provision-aurelia.sh` or enable this setting. Thus
the above is a manual provisioning/configuration recipe, not yet the requested
single normal-install path. The canonical host also reports Aurelia `0.1.37`,
while the pinned recipe specifies `0.1.38`; that host binary is not evidence
that the pinned recipe was installed or exercised. Resolve these setup gaps
before presenting this as a turnkey developer install. No integration change
was made here to conceal or work around them.

The repository’s canonical reproducible release builder is
`scripts/release.py`; its build must run from a clean committed checkout on the
canonical host. See `docs/installation.md` for the host and dependency
requirements. From the canonical checkout, use:

```sh
git checkout review/aurelia-56827df
git status --porcelain       # must be empty
python3 scripts/release.py build --release-dir /opt/lulu/releases/aurelia-review-56827df
python3 scripts/release.py verify --release-dir /opt/lulu/releases/aurelia-review-56827df
```

To make a transport archive, archive the verified immutable release directory
without changing its contents, then publish that archive’s SHA-256 alongside
it. Do not activate this review release over another Mudos installation.

## Known limitations and physical checkpoint results

Known limitations at the checkpoint include DLC/update handling and adoption
of an acquisition already active across restart. Some games may require Steam
integration/DRM that the Aurelia-only route does not currently satisfy.
Compatibility-mode restoration is incomplete.

Physical observations supplied for the checkpoint (not re-tested for this
review package):

- **BEEP:** successful launch through the real Mudos UI, including
  launcher-first behavior.
- **Super Meat Boy:** successful launch, noticeably faster startup than the
  previous Steam integration; returned to Mudos, which remained in
  compatibility mode.
- **Dead by Daylight:** reached the main game window after its anti-cheat and
  launcher sequence, then reported Steam offline.
- **Rocket League:** launch stalled; no cause established.
- **Controller:** preliminary successful gameplay/navigation, not formal
  acceptance.

These results do not imply general compatibility. The checkpoint also does
not validate fresh installation of the `0.1.38` Aurelia package on a separate
machine. This build is shared to invite technical feedback on API usage,
launch/process lifecycle, acquisition integration, and upstream assumptions.
