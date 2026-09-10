# Steam Input Routing Evidence

The Steam bootstrap initially launched outside `console-sessiond`, leaving the
session in `shell` mode and InputPlumber on `Lulu SHELL`. The physical Xbox 360
controller could drive Mudos because that profile maps controller events to QML
keyboard events, but Steam Big Picture did not receive the intended gamepad
route.

For the bounded live proof, `console-sessiond.SetInputMode("game")` changed
InputPlumber to `Lulu GAME` without replacing the persistent composite or its
virtual targets. The same physical controller then navigated Steam Big Picture.

After Steam exited, `console-sessiond.SetInputMode("shell")` restored
InputPlumber to `Lulu SHELL`; the controller again navigated Mudos. The
persistent composite remained connected and retained navigation ownership. No
HOST controller device or HOST user state was involved.

The durable bootstrap must therefore be lifecycle-integrated: Steam foreground
requires a sessiond-owned GAME transition, and Steam return requires a
sessiond-owned SHELL transition. The current operator bootstrap is intentionally
not an autonomous lifecycle owner.
