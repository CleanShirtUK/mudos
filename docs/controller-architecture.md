# Controller Architecture

The production controller path is intentionally non-persistent:

```text
physical controller appears
  -> InputPlumber creates a composite
  -> InputPlumber creates the virtual Xbox target
  -> Lulu initializes InterceptMode=1 once
  -> normal pass-through

physical controller disappears
  -> the composite and virtual target disappear

physical controller returns
  -> a fresh composite and virtual target are created
  -> Lulu initializes InterceptMode=1 once
  -> clients hotplug and reacquire normally
```

The composite uses `persist: false` intentionally. During validation,
InputPlumber's persistent composite was observed entering stale dispatch after
the physical source disconnected and reconnected. Fresh composite recreation
recovered cleanly instead. Lulu therefore listens for InputPlumber's
`GamepadOrder` property changes, initializes each newly connected composite to
`InterceptMode=1` exactly once, and otherwise leaves device and client
lifecycle handling to InputPlumber and the clients.

Recovery must not depend on restarting the InputPlumber daemon, polling for
devices, switching profiles, or changing modes as part of controller
lifecycle handling. Lulu navigation and already-running Steam/Proton/Wine
games are expected to reacquire the recreated virtual Xbox controller through
normal hotplug behavior.

## Validated checkpoint

Manual testing verified Cuphead, Oddworld Abe's Oddysee, and native Linux
Super Meat Boy across repeated launches. Each game accepted controller input
and audio, exited normally, and returned to Lulu; Lulu navigation resumed
after each return. An already-running Cuphead also reacquired a recreated
controller after the physical source reconnect. Guide handling is intentionally
not defined here; it remains an InputPlumber production-design decision.
