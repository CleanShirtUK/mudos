# Guide Foundation

The standalone Guide foundation is validated against the live Gamescope,
InputPlumber 0.79.0, and Cuphead session.

## Architecture

- InputPlumber PASS/ALL interception remains authoritative.
- The native Mudos shell subscribes to
  `/org/shadowblip/InputPlumber/devices/target/dbus0` using
  `org.shadowblip.Input.DBusDevice.InputEvent(string, double)`.
- A `ui_guide` press opens the disposable `mudos-guide` helper.
- `ui_up`, `ui_down`, `ui_accept`, `ui_back`, and `ui_guide` are forwarded to
  the helper over its process stdin; release events are ignored.
- The helper uses only `GAMESCOPE_EXTERNAL_OVERLAY=1` for presentation.
- Helper process exit restores `InterceptMode=1` and clears captured target
  state.
- Default InputPlumber profile remains loaded throughout Guide operation.

## Validation

- Guide opens while Cuphead remains `WM_STATE=Normal`.
- D-pad navigation changes the visible selection.
- B closes Guide and restores mode 1.
- Guide-again closes Guide and restores mode 1.
- Cuphead remains visible and receives controller input after close.

## Known Defect

Guide intermittently requires two presses to open. B intermittently requires
two presses to close. The behavior is intermittent. The underlying Guide
open/navigation/close architecture otherwise works.

This defect is pending and is not addressed by this checkpoint. Future
investigation must begin with external reconnaissance of how OpenGamepadUI and
upstream InputPlumber consumers handle:

- `InputEvent` press/release pairs
- `ui_guide`
- `ui_back`
- event debounce
- held-button state
- transitions into and out of `InterceptMode=2`

Existing logs containing examples of the defect are preserved. No additional
instrumentation is part of this checkpoint.
