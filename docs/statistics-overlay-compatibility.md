# Statistics Overlay Compatibility

Status: **ACCEPTED / CLOSED** by user physical acceptance, recorded separately
from automated test results in `docs/validation-log.md`.

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

The accepted design is Settings-only: users select a persistent profile in
System Settings and it applies on subsequent launches. Live Guide-menu cycling
or visibility controls are not part of this milestone. Physical acceptance
explicitly included applications newly installed as Flatpaks, in addition to
existing Flatpak installations.

## Compatibility matrix

| Path | Renderer/runtime evidence | Status |
| --- | --- | --- |
| Silent Hill 2, Aurelia/Proton | Existing Aurelia launch produced MangoHud log activity and the user confirmed visible output. | **Physically verified** before this change; path intentionally unchanged. |
| Super Meat Boy, Aurelia/native Linux | Aurelia's native ELF launch uses the official wrapper and applies the selected profile to the actual game process. | **Accepted**; initial process instrumentation evidence is retained below. |
| PCSX2 / SSX Tricky, Flatpak | PCSX2's matching runtime extension is provisioned and its profile-aware wrapper is used. | **Accepted** by the user's physical acceptance. |
| Existing and newly installed Flatpak applications | The generic adapter resolves each installed app's runtime-declared extension branch and provisions the matching MangoHud runtime extension; launch-only environment and wrapper are used. No persistent overrides are written. | **Accepted**, explicitly including newly installed Flatpak applications. |
| RetroArch | Active Mudos config selects `video_driver = "gl"` (OpenGL). Native executable is eligible for the official wrapper. | **Accepted**. |
| Dolphin | Mudos launch uses the native executable; its managed graphics config contains no explicit backend selection. The official wrapper supports either OpenGL or Vulkan. | **Accepted**; backend identification remains a compatibility note, not an acceptance blocker. |
| Eden | Active Mudos config records renderer `backend=1` and Vulkan-device settings; the intended backend is Vulkan. The current Mudos runtime is the native AppImage, not the separately installed Flatpak app. | **Accepted** for the native executable. |
| Legacy `steam:<AppID>` rows dispatched through the Steam client | The appliance currently has the legacy route enabled by default for this identity (the `steam-aurelia` override is unset). | **Not included in this accepted milestone**; a scoped backlog item remains for that distinct launch path. Aurelia-dispatched titles are accepted. |
| Flatpak runtimes without the Freedesktop VulkanLayer extension point, or unavailable matching extension | Cannot load the runtime extension required by the supported in-sandbox wrapper. | **Unsupported**; launch continues with overlay explicitly disabled and a diagnostic logged. |

Automated launch/profile regression tests are separate from and do not replace
the user's physical acceptance. Historical process instrumentation and capture
limitations above are retained as test evidence, not as open acceptance gates.
