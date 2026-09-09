# UI Checkpoint: 2026-09-09

This is the bounded checkpoint immediately before System/Settings work.

## Accepted And Working

- Home static presentation baseline and current responsive geometry.
- Recent horizontal rail with bounded, no-wrap navigation.
- Interruptible/retargetable Recent Left/Right navigation.
- Compact to focal Recent card geometry using `500ms Easing.OutQuint`.
- Monotonic artwork geometry with no overshoot.
- Focal-only chrome fades.
- Compact title fade without title scaling during the card morph.
- Accepted focal glass treatment and canonical live sampling.
- Accepted Play stacked-glass treatment.
- Persistent shell-owned Library spatial glass surface.
- All Games Home surface to fullscreen Library morph.
- Fullscreen Library presentation, grid, collection and game navigation.
- Library content fade choreography.
- Controller glyph hints and controller-first input routing.
- Steam catalogue and SteamGridDB artwork path.

## Partial And Deferred

Vertical Home category animation is not accepted. Experimental Recent/Library
vertical work exists in the current working tree, but must not be treated as a
finished interaction or extended tonight.

Deferred animation work:

- Finish and settle the Home vertical category transition.
- Generalize the category transition to Store/System only after Recent/Library is accepted.
- Add rapid Up/Down retargeting only after single-step category motion is accepted.
- Add retargetable selected/unselected game-card size, dimming and brightness animation.
- Add a Steam card beneath Library alongside All Games for horizontal transition testing.
- Use Library cards and System pages as horizontal transition grammar test beds.

## Current Checkpoint Notes

- Current active deployment is the development HOST, not BC-250 evidence.
- The current Home category experiment is intentionally preserved for tomorrow's review.
- No Settings implementation is included in this checkpoint.

## Tomorrow Queue

1. Finish the vertical Home-category transition.
2. Animate selected/unselected game-card size and dimming using accepted easing and retargeting principles.
3. Add a Steam card beneath Library alongside All Games.
4. Use Library cards and System pages to develop horizontal transitions.
