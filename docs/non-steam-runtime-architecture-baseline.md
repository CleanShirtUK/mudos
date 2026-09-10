# Non-Steam Runtime Architecture Baseline

Status: validated architecture checkpoint, 2026-09-09.

This record defines the accepted Mudos-side contract for the first non-Steam
runtime provider. It does not define a production launcher, AppID allocator, or
catalogue integration.

## RetroArch Path

The validated path is:

```text
Mudos/Lulu shell (STEAM_GAME=769)
-> predeclared Gamescope AppID priority: <runtime-appid>, 769
-> RetroArch in a transient systemd user scope
-> Gamescope derives the runtime AppID from the scope cgroup
-> RetroArch gameplay surface
-> scope termination
-> Gamescope naturally falls through to the Mudos shell (769)
```

The scope basename must match Gamescope's process-derived AppID convention:

```text
app-steam-app<runtime-appid>-<integer>.scope
```

For the controlled experiment, the temporary runtime identity was
`4000000001`.

## Responsibilities

Identity is provided by the systemd cgroup. Gamescope reads the RetroArch PID's
cgroup and derives `4000000001`; RetroArch and Gamescope remain unmodified.

Presentation is provided by Gamescope's root AppID priority list. Mudos
predeclares `4000000001, 769` before launching RetroArch. Gamescope skips the
absent runtime AppID, selects the Mudos shell while idle, selects RetroArch when
its window becomes focusable, and falls back to the Mudos shell when the runtime
disappears.

Containment and lifetime are provided by the transient systemd user scope.

RetroArch-specific graceful termination is provided by stopping its scope.
For packaged RetroArch this sends SIGTERM, allows clean deinitialization, and
does not require Mudos to monitor or restore presentation state.

This termination behavior is provider-specific and must be validated again for
future runtime providers.

## Validated Environment

The test environment uses:

```text
gamescope-git 3.16.28.r94.g51403849-1
gamescope version 3.16.28-94-g51403849
```

The former stable package, `gamescope 3.16.25-1`, did not contain the required
process-derived cgroup AppID feature. `gamescope-git` is a test-environment
dependency swap, not yet a permanent Lulu package requirement. Package policy
must be decided separately from the required Gamescope capability.

## Explicit Rejections

The accepted path does not use RetroArch or Gamescope patches, SDL patches,
application-window properties, post-map identity assignment, X11 window
polling or discovery, `gamescope-fg`, nested Gamescope, LD_PRELOAD or Xlib
interposition, synthetic keyboard Escape as Lulu's quit mechanism, or a
focus/lifecycle supervisor.

## Outstanding Decisions

- Production synthetic AppID namespace and allocation remain unresolved.
- RomM and catalogue integration remain out of scope.
- Other emulator providers require independent validation.
- Permanent Gamescope package and version policy remains unresolved.
