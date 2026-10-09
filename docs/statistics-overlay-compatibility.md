# Statistics Overlay Compatibility

Status: implementation candidate; live visual validation remains outstanding.

Mudos remains authoritative for the four stored profiles (Off, FPS Only,
Minimal, Detailed). The selected configuration is attached only to a Mudos
game/application launch. Native ELF programs and simple native entry scripts
that `exec` their game use MangoHud's official `mangohud --dlsym` wrapper, which
supports OpenGL and Vulkan; Proton/Wine launchers are deliberately not wrapped, preserving Aurelia's existing
`MANGOHUD=1` Vulkan-layer path.

Flatpak launches go through the shared Flatpak adapter. It reads the installed
application's runtime metadata, obtains the branch declared by the runtime's
`org.freedesktop.Platform.VulkanLayer` extension point, and installs that
matching `org.freedesktop.Platform.VulkanLayer.MangoHud` runtime extension
from the Mudos Flathub remote when missing. Launch-time `--env` options and the
extension's own in-sandbox MangoHud wrapper apply only to that invocation; no
Flatpak override or host `LD_PRELOAD` is written. An unavailable extension or
missing application command is logged, and the application starts with
`MANGOHUD=0` instead of claiming a working overlay.

PCSX2 is a separate managed local-runtime command that launches Flatpak
directly, so its wrapper forwards the same profile values and, when enabled,
executes `pcsx2-qt` through the extension wrapper. Its installer provisions the
extension branch selected by the installed PCSX2 runtime.

## Compatibility matrix

| Path | Renderer/runtime evidence | Status |
| --- | --- | --- |
| Silent Hill 2, Aurelia/Proton | Existing Aurelia launch produced MangoHud log activity and the user confirmed visible output. | **Physically verified** before this change; path intentionally unchanged. |
| Super Meat Boy, Aurelia/native Linux | Aurelia resolved the shell entry script `/home/lulu/.local/share/Steam/steamapps/common/Super Meat Boy/SuperMeatBoy`, which changes into its install directory and `exec`s the ELF at `amd64/SuperMeatBoy`. Gamescope selected a window owned by the actual ELF PID. Journal evidence showed previous launches alive for 8–19 seconds, not ~2 seconds. On the activated candidate, the live game's environment had `MANGOHUD=1`, `MANGOHUD_CONFIG=fps_only=1`, and `/usr/lib/mangohud/libMangoHud_opengl.so` mapped in the actual game PID. | **Physically instrumented: FPS Only**. The X11 screenshot attempt was black (the game surface is not captured by that X11 path), so visible pixels/preset are **not independently verified**. Current game was left running. |
| PCSX2 / SSX Tricky, Flatpak | `net.pcsx2.PCSX2` uses `org.kde.Platform/x86_64/6.10`, whose metadata selects VulkanLayer version `25.08`. That system extension is now installed; wrapper presence and invocation inside the PCSX2 sandbox were checked. | **Implemented, not visually tested**. SSX was left stopped; no game session launched after the candidate activation. |
| Independently installed Flatpak games/apps | SuperTux (runtime `org.freedesktop.Platform` branch `26.08`) and FurMark (`25.08`) were present. The shared adapter resolved their declared app commands and provisioned the corresponding MangoHud extension branches (`26.08` user, `25.08` system). | **Dependency provisioning verified; app rendering untested**. Neither app was launched during this pass. |
| RetroArch | Active Mudos config selects `video_driver = "gl"` (OpenGL). Native executable is eligible for the official wrapper. | **Implemented, not visually verified**. |
| Dolphin | Mudos launch uses the native executable; its managed graphics config contains no explicit backend selection, so the active backend is not established by stored config. The official wrapper supports either OpenGL or Vulkan. | **Implemented, backend unverified**. |
| Eden | Active Mudos config records renderer `backend=1` and Vulkan-device settings; the intended backend is Vulkan. The current Mudos runtime is the native AppImage, not the separately installed Flatpak app. | **Implemented for native executable, not visually verified**. |
| Standard Steam-managed games | No per-game Mudos environment contract. | **Unsupported**, remains a separate backlog item. |
| Flatpak runtimes without the Freedesktop VulkanLayer extension point, or unavailable matching extension | Cannot load the runtime extension required by the supported in-sandbox wrapper. | **Unsupported**; launch continues with overlay explicitly disabled and a diagnostic logged. |

Automated launch/profile regression tests do not establish visual output. The
activated candidate showed MangoHud's OpenGL library in the actual Super Meat
Boy process under FPS Only. Visible profile confirmation and Minimal, Detailed,
and Off checks on subsequent launches remain outstanding, including game exit
and return-to-Mudos behavior. No physical controller acceptance is claimed.
