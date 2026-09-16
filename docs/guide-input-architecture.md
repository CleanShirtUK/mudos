# Guide Input Compatibility

Guide input is intentionally handled differently from normal shell and gameplay
input.

InputPlumber 0.79.0 routes intercepted Guide input through its D-Bus target.
The target emits individual input edges from independently spawned asynchronous
tasks.  Consequently, a button `DOWN` and its `UP` are not guaranteed to reach
D-Bus consumers in order.  Disposable testing of the exact v0.79.0 source
observed A `UP` before A `DOWN` in 2,109 of 10,000 Guide-path iterations.

Normal shell/gameplay target routing does not use this detached D-Bus signal
path and is unaffected.

Mudos therefore treats release as the authoritative discrete event while the
Guide helper is open:

- button `DOWN` records state but does not activate a discrete Guide action;
- button `UP` performs the action once;
- late or reordered `DOWN` events cannot activate the action;
- Guide-local edge state is reset when the target disappears or the helper
  generation ends.

Guide opening remains release-based.  The Guide+X OSK chord remains on the
separate SDL pending-Guide path and is not reconstructed from D-Bus edges.

This is deliberately a Mudos-side compatibility policy.  Maintaining a
patched or forked InputPlumber is out of scope; the upstream defect is the
independent per-edge asynchronous emission architecture.

## OSK lifecycle known issue

The controller-first OSK path is implemented and validated in the dev runtime:

```text
Guide+X → OSK visible → bridge-owned controller navigation
B       → OSK hidden → normal Mudos controller ownership
```

Physical testing also shows an intermittent edge-loss issue on the
InputPlumber D-Bus interception path.  Guide+X activation succeeds on roughly
half of attempts, and B dismissal has similar intermittent misses.  Repeating
X while Guide remains held does not recover a missed attempt; releasing Guide
and starting a new chord does.  When either edge sequence succeeds, OSK input,
the dedicated virtual controller, Gamescope composition, dismissal, and return
to Mudos ownership all work correctly.

This is recorded as a known upstream/interception-path issue, not an OSK
architecture failure.  It is intentionally out of scope for this development
pass.  Do not redesign the bridge, mappings, Guide handling, InputPlumber
modes, or Gamescope lifecycle workaround based on these intermittent misses.
