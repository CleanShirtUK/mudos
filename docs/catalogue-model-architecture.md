# Native Catalogue and Recent Model

Status: accepted Recent-only migration, physically validated 2026-09-15.

## Authority and transport

`CatalogueModel` is the native, long-lived Qt authority for catalogue records.
It synchronizes an initial snapshot and recoverable generation deltas from
`org.lulu.Consoled`. Catalogue truth is immediate: `mark_played()` persists,
publishes its generation, and reaches the native model without waiting for UI
animation.

The D-Bus methods use single STRUCT return values:

- `GetCatalogueSnapshot` — `(ts)`
- `GetCatalogueChanges` — `(bs)`

The dbus-next service supplies struct fields as Python lists. The Qt client
decodes the returned `QDBusArgument` structure rather than treating the
response as flattened `ts`/`bs` arguments. This was found during live
integration and is covered by transport marshalling tests.

The native model is constructed before the asynchronous initial snapshot.
Its `modelReset` subscription rebuilds `RecentModel` when the delayed snapshot
arrives. Subsequent authoritative updates use targeted role changes and row
insert/remove/move notifications.

## Recent consumer

`RecentModel` is a long-lived derived `QAbstractListModel` over
`CatalogueModel`. Recent membership is preserved as installed records with a
positive `last_played`, sorted descending by `last_played` with deterministic
`game_id` tie-breaking.

The production Recent view no longer replaces a JS `recentGames` array. Native
role names are declared on the QML delegate and adapted into one lightweight
delegate-local `gameRecord` for the existing `GameCard` contract. This does
not recreate delegates or transfer catalogue ownership back to QML.

Selection identity is `game_id`; row indexes are transient. Navigation uses
the live repeater count and follows the selected game through row movement.

## Proven evidence

Automated coverage includes:

- D-Bus struct marshalling and decoding;
- delayed empty-model to initial-snapshot population;
- native row movement without model reset;
- native role-to-GameCard mapping;
- QML delegate population and navigation;
- stable identity for unaffected rows.

Physical validation launched **Super Mario Bros** and **Mario Kart** from
Library. Both produced immediate catalogue truth and Recent ordering updates.
The diagnostics showed no Recent model reset or delegate recreation during
launch. The visible reorder occurred while Mudos remained onscreen; it is
classified as presentation choreography timing, not glass or renderer
corruption.

## Required future choreography hook

The future general presentation/choreography coordinator must provide this
state boundary:

```text
launch presentation begins
→ freeze visible structural presentation
→ authoritative catalogue continues updating
→ Mudos reaches hidden/offscreen state
→ reconcile deferred presentation once to current authoritative state
→ release/continue transition
```

The deferred state must reconcile from the current authoritative model,
coalescing multiple changes, and must release on completion, failure,
shutdown, or cancellation. It must not delay persistence, generation
publication, or native catalogue updates. This hook is intentionally not yet
implemented; it belongs to the general choreography owner, not to a timer or
Recent-specific launch workaround.
