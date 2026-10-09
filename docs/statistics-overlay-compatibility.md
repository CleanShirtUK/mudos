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
| Super Meat Boy, Aurelia/native Linux | Aurelia resolved the shell entry script `/home/lulu/.local/share/Steam/steamapps/common/Super Meat Boy/SuperMeatBoy`, which changes into its install directory and `exec`s the ELF at `amd64/SuperMeatBoy`. Gamescope selected a window owned by the actual ELF PID. Journal evidence shows one launch alive from 22:43:28 to 22:43:47, so the earlier ~2-second report was not a consistent lifetime and did not mean Aurelia had only started a wrapper. The adapter now wraps this simple native entry script; its MangoHud preload environment is inherited by the script's `exec`ed game. | **Implemented, not visually verified** with this candidate. Prior process/window evidence is not MangoHud evidence. |
| PCSX2 / SSX Tricky, Flatpak | `net.pcsx2.PCSX2` uses `org.kde.Platform/x86_64/6.10`. Its runtime metadata exposes VulkanLayer version `25.08`; no MangoHud runtime extension was installed at inspection. | **Implemented, not tested**. Installer now provisions matching extension; existing installation needs the new provisioning step. |
| Independently installed Flatpak apps | Shared launch adapter uses each app's declared runtime and app command; no allowlist. | **Implemented, not tested**. No distinct independent Flatpak game was available in the installed-app inventory at inspection. |
| RetroArch | Active Mudos config selects `video_driver = "gl"` (OpenGL). Native executable is eligible for the official wrapper. | **Implemented, not visually verified**. |
| Dolphin | Mudos launch uses the native executable; its managed graphics config contains no explicit backend selection, so the active backend is not established by stored config. The official wrapper supports either OpenGL or Vulkan. | **Implemented, backend unverified**. |
| Eden | Active Mudos config records renderer `backend=1` and Vulkan-device settings; the intended backend is Vulkan. The current Mudos runtime is the native AppImage, not the separately installed Flatpak app. | **Implemented for native executable, not visually verified**. |
| Standard Steam-managed games | No per-game Mudos environment contract. | **Unsupported**, remains a separate backlog item. |
| Flatpak runtimes without the Freedesktop VulkanLayer extension point, or unavailable matching extension | Cannot load the runtime extension required by the supported in-sandbox wrapper. | **Unsupported**; launch continues with overlay explicitly disabled and a diagnostic logged. |

Automated launch/profile regression tests do not establish visual output. The
candidate still needs visible FPS Only, Minimal, Detailed, and Off checks on
subsequent launches, including game exit and return-to-Mudos behavior. The
current change has not been activated, and no physical controller acceptance
is claimed.
