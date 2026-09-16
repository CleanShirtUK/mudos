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
