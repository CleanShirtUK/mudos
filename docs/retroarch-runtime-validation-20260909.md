# RetroArch Runtime Validation

Status: validated evidence, 2026-09-09.

This is the controlled evidence record for the non-Steam runtime architecture.
It is not an implementation specification.

## Identity And Presentation

The installed Gamescope was `gamescope-git 3.16.28.r94.g51403849-1`, reporting
`3.16.28-94-g51403849`. Its binary contained:

```text
app-steam-app%u-%d.scope
```

The installed source implements process-derived AppID lookup from
`/proc/<pid>/cgroup` before the XWayland window is mapped.

RetroArch was launched unmodified with the packaged Nestopia core and the
controlled NES fixture inside scopes such as:

```text
app-steam-app4000000001-3.scope
```

Observed RetroArch cgroup:

```text
0::/user.slice/user-958.slice/user@958.service/app.slice/app-steam-app4000000001-3.scope
```

Before launch, Gamescope control state was set once to:

```text
GAMESCOPECTRL_BASELAYER_APPID = 4000000001, 769
```

`GAMESCOPECTRL_BASELAYER_WINDOW` was removed because its previous value
`135822` was stale and invalid. No RetroArch window property was written or
discovered.

Before the runtime window existed:

```text
GAMESCOPE_FOCUSABLE_APPS = 769
GAMESCOPE_FOCUSED_APP = 769
GAMESCOPE_FOCUSED_APP_GFX = 769
```

After RetroArch mapped:

```text
GAMESCOPE_FOCUSABLE_APPS = 4000000001, 769
GAMESCOPE_FOCUSED_APP = 4000000001
GAMESCOPE_FOCUSED_APP_GFX = 4000000001
```

RetroArch was the focused/presented gameplay surface. A second launch using
the unchanged priority list reproduced the same identity and presentation
result.

## Scope Termination

The live scope reported:

```text
KillMode=control-group
KillSignal=15
TimeoutStopUSec=10s
SendSIGKILL=yes
FinalKillSignal=9
```

Stopping the scope with:

```text
systemctl --user stop app-steam-app4000000001-5.scope
```

returned successfully in approximately 61 ms. The scope became inactive with
`Result=success`; no SIGKILL escalation was required. RetroArch's log recorded
runtime accounting, game unload, core unload, saved core options, and monitor
restore.

After scope termination:

```text
GAMESCOPE_FOCUSABLE_APPS = 769
GAMESCOPE_FOCUSED_APP = 769
GAMESCOPE_FOCUSED_APP_GFX = 769
```

No Gamescope control property was restored or changed at exit.

## Baseline Warning

The test session initially contained stale control state:

```text
GAMESCOPECTRL_BASELAYER_WINDOW = 135822
GAMESCOPECTRL_BASELAYER_APPID = 413091, 769
```

The window value was already invalid. Future Lulu session startup must
establish a deterministic Gamescope control baseline rather than inheriting
stale root properties.
