# Guide Foundation

The standalone Guide foundation is validated against the live Gamescope,
InputPlumber 0.79.0, and Cuphead session.

## Architecture

- InputPlumber PASS/ALL interception remains authoritative.
- The native Mudos shell subscribes to
  `/org/shadowblip/InputPlumber/devices/target/dbus0` using
  `org.shadowblip.Input.DBusDevice.InputEvent(string, double)`.
- A `ui_guide` press opens the disposable `mudos-guide` helper.
- `ui_accept` activates the single Quit action. `ui_up` and `ui_down` do not
  change selection; `ui_back` and `ui_guide` close the helper. Release events
  are ignored.
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

The validated v0 application action is:

```text
WM_DELETE_WINDOW -> captured target XID
helper exits -> parent restores InterceptMode=1
```

The helper does not wait for the target process to exit.

## Deferred Force Close

`Force Close Current Application` is deferred. It must begin with external
reconnaissance and may require provider-specific handling for Steam/Proton,
native games, and emulator process groups. No force-termination primitive is
retained in the v0 production helper.

## Historical Observation

An earlier dirty-session diagnostic observed intermittent two-press behavior
for Guide open and B close. It was not reproduced in the clean v0 validation
above and is retained as historical evidence only.

If the behavior recurs from a clean session, future investigation must begin
with external reconnaissance of how OpenGamepadUI and upstream InputPlumber
consumers handle:

- `InputEvent` press/release pairs
- `ui_guide`
- `ui_back`
- event debounce
- held-button state
- transitions into and out of `InterceptMode=2`

Existing logs containing examples of the defect are preserved. No additional
instrumentation is part of this checkpoint.
