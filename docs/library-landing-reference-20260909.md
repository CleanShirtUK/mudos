# Library Landing Reference

The Library Home category is the reference multi-card landing architecture.

- `LibraryHome.qml` owns sibling `NavigationCard` instances for All Games and Steam.
- `selectedIndex` is the landing selection and is shared with `collectionIndex`.
- Left/Right updates the bounded landing selection and uses the card selection interpolation.
- Activation routes directly into the existing `LibrarySpace.qml` fullscreen grid.
- `collectionIndex` selects the existing catalogue scope: `all` or `steam`.
- Back leaves the fullscreen grid and preserves `collectionIndex`, restoring the originating card.
- No second fullscreen selector is inserted between the landing cards and the grid.
