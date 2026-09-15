# Future task: surface-authoritative game lifecycle

## Status

Documented for a future investigation. Do not implement as part of the
current launch/return work.

## Objective

Empirically identify the authoritative gameplay surface for every supported
provider/runtime so Mudos can derive `game surface presented` and `game
surface removed` from actual presentation state. Those boundaries should
eventually drive both launch/return choreography and launch-overlay lifetime.

## Investigation scope

Characterize the complete window/surface lifecycle from launch through return
for each of:

- Steam
- RetroArch
- Dolphin
- local/standalone runtimes

Do not assume the discriminator in advance. Record all observable identity and
lifecycle information, including where available:

- Wayland and XWayland identity
- app-id, class, title, type, and role
- PID and process-tree relationships
- surface/window creation, mapping, focus, presentation, and removal order
- Gamescope focus and presentation observations
- provider/runtime-specific transitions and timing

The result should identify which surface is authoritative per runtime and
document any cases where the surface, process, and provider lifecycle diverge.
