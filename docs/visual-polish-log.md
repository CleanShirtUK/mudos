# Mudos Minor Issues Log

This document is the canonical, implementation-oriented log of Mudos issues that need correction but are not critical to the workflows currently being addressed. It is intended to provide enough context for a future correction pass to work through each item without needing the original conversation. Items are recorded as feedback arrives; stable IDs are never reused or renumbered. Use a prefix by issue domain (for example, `VP` for visual/presentation issues and `EMU` for emulator issues); continue existing IDs in their own prefix sequence. Functional issues discovered during visual review are labeled as such.

## Global / Shell

### VP-007 — Fix system bar position and animate its glass backing

**Area:** Global / Shell; Library
**Component:** Top-right system bar and its glass backing
**Problem:** The system bar currently looks misaligned in the Library view, despite fitting in that context. Its placement should not shift between different contexts.
**Desired result:** Adjust the system bar to a position that fits nicely in Library and make that its permanent, fixed position across contexts. Give it a dedicated glass backing. Animate icons as they appear and disappear, and animate the backing to grow and shrink with the icon set.
**Status:** Open

## Home

### VP-001 — Hide the empty Recents row

**Area:** Home
**Component:** Recents and Library rows
**Problem:** When Recents has no items, its row is still presented in the Home view.
**Desired result:** Hide the Recents row entirely when it is empty, so Library is the bottom presented row.
**Status:** Open

### VP-002 — Keep Recent card corner sampling accurate during vertical movement

**Area:** Home
**Component:** Recent cards and their sampled-background corners
**Problem:** Vertical movement of Recent cards moves them without updating the corner mapping/painting to match the true card corners against the sampled background texture.
**Desired result:** Update vertical movement of Recent cards so their corners are painted using the correct sampled-background mapping.
**Reference:** Horizontal movement across the Recents row handles the card corners correctly and is the known-good implementation to match.
**Status:** Open

### VP-003 — Assign distinct Nerd Font icons to Home Library cards

**Area:** Home / Library
**Component:** Home Library cards and Flathub store card
**Problem:** All four Home Library cards currently use the same aligned-library symbol, so their icons do not distinguish their destinations.
**Desired result:** Use destination-appropriate Nerd Font icons:
- Provider: use the plugin symbol, if suitable for the Plugins system card.
- Game Mode: use glyph `f0c0`.
- Genre: use glyph `eeb6`.
- Platform: choose an appropriate icon during the polish pass.
- Flathub store card: use glyph `f324`.
**Acceptance notes:** Keep icon alignment consistent across the cards while using the distinct glyphs above.
**Status:** Open

## Downloads

### VP-004 — Prevent selected download rows from clipping on the left

**Area:** Downloads
**Component:** Download rows
**Problem:** A download row clips at its left side when enlarged in its selected state.
**Desired result:** The selected/enlarged row remains fully visible, without left-edge clipping.
**Status:** Open

### VP-005 — Make download failures actionable and clearly explained

**Area:** Downloads
**Component:** Download failure notifications, error messages, and Downloads menu actions
**Problem:** Download failures do not provide a useful explanation. For example, a ROMM download that fails because no provider is associated with the platform reports only a generic “provider error.” Failed downloads are shown as “paused” in the Downloads menu.
**Desired result:** Show a notification when a download fails and explain the actual failure reason in clear, usable language. Cover the missing-provider case and other download failure reasons, rather than surfacing only a generic error label. In the Downloads menu, identify failed downloads as failed and expose a retry option instead of “paused.”
**Type:** Functional issue discovered during visual review
**Status:** Open

## Store

### VP-006 — Match Store row left-edge clipping to other rows

**Area:** Store
**Component:** Store row card
**Problem:** The Store row card clips at the left boundary of the viewport instead of at the monitor edge.
**Desired result:** Match the clipping behavior of other rows, allowing the card to peek in from the left while clipping at the monitor edge.
**Reference:** Other rows currently exhibit the intended monitor-edge clipping and left-side card peek.
**Status:** Open

## OOBE

### VP-008 — Show installation progress after provider selection

**Area:** OOBE
**Component:** Provider installation/loading screen
**Problem:** After selecting providers to install, there is no loading screen showing installation progress.
**Desired result:** Show a progress screen that identifies what is currently being installed and communicates total progress across all applications being installed.
**Status:** Open

## Installable View and Library

### VP-014 — Define a no-installed-games view

**Area:** Library / installed games
**Component:** Empty state when no games are installed
**Problem:** There is no specific view identified for the state where no games are installed.
**Status:** Logged for later specification; this records the issue only, not a fix to implement. Visual/content specifics are pending follow-up from the user.

### VP-015 — Align metadata beneath preview artwork

**Area:** Library; Installable view
**Component:** Metadata and microtrailer/viewport artwork layout
**Problem:** Metadata is not aligned underneath the microtrailer/viewport artwork.
**Desired result:** Align metadata beneath the microtrailer/viewport artwork in both views, right-align each metadata row, and place its glyph at the end of the row rather than the beginning.
**Status:** Open

### VP-016 — Fit screenshots and microtrailers inside their viewport

**Area:** Library; Installable view
**Component:** Screenshot/microtrailer preview viewport
**Problem:** Screenshots and microtrailers can be cropped when their aspect ratio does not match the displayed viewport.
**Desired result:** Fit the entire content inside the viewport without cropping. When aspect ratios differ, use black bars to fill the unused space.
**Status:** Open

### VP-017 — Avoid showing the question-mark glyph while previews load

**Area:** Library; Installable view
**Component:** Trailer/screenshot preview loading state
**Problem:** When navigating between games, a question-mark glyph briefly appears while a trailer or screenshot is loading.
**Desired result:** Do not show the question-mark glyph during trailer or screenshot loading.
**Status:** Open

### VP-020 — Improve OSK sizing, placement, and invocation

**Area:** Global / Shell
**Component:** On-screen keyboard (OSK)
**Problem:** The OSK takes up too much of the screen, and the Guide+X shortcut does not summon it reliably.
**Desired result:** Reduce the OSK to approximately 60% of its current size and anchor it to the bottom of the screen. Make Guide+X reliably summon the OSK.
**Type:** Includes a functional/input reliability issue.
**Status:** Open

### VP-018 — Trace missing screenshots in Installable view

**Area:** Installable view
**Component:** Game screenshot availability
**Problem:** Many games appear to be missing screenshots.
**Desired result:** Trace why screenshots are missing and identify the cause.
**Status:** Open

### VP-019 — Use distinct provider categories in Installable view

**Area:** Installable view; Platform categories
**Component:** Installable category names and provider grouping
**Problem:** The main Installable category is named “Installable,” and GOG, Epic, and Steam entries are grouped together under “PC.”
**Desired result:** Rename the main category to “All” and give GOG, Epic, and Steam their own separate categories in Installable view. Keep grouping these providers under “PC” in the platform categories, where that combined presentation is intended.
**Status:** Open

### VP-009 — Make Installable view navigation consistent and one-step

**Area:** Installable view
**Component:** Controller navigation and category switching
**Problem:** Up/down navigation jumps across multiple entries. Category switching currently uses LB/RB.
**Desired result:** Up/down should navigate exactly one entry at a time. Use left/right for category switching, matching Library view, and retire LB/RB for this view.
**Type:** Functional issue discovered during visual review
**Reference:** Library view uses left/right for category switching.
**Status:** Open

### VP-010 — Tighten category header spacing in Library and Installable views

**Area:** Library; Installable view
**Component:** Category tape, category underline, and list/game-info views
**Problem:** The vertical gaps are too large both between the category tape and its underline, and between the underline and the top of the content views.
**Desired result:** Reduce both gaps consistently in Library and Installable views.
**Status:** Open

### VP-011 — Apply list/info surfaces to glass backing and add view borders

**Area:** Library; Installable view
**Component:** Game list and game-info views, including their glass backing
**Problem:** The background surface used by the list and game-data views is not applied to the glass backing.
**Desired result:** Apply the list/game-data background surface to the glass backing in both views, and add borders to the game list and game-info views.
**Status:** Open

### VP-012 — Show at most eight items in Library and Installable lists

**Area:** Library; Installable view
**Component:** Game lists and inter-item spacing
**Problem:** The ninth list item is clipped.
**Desired result:** Use deterministic spacing between list items so the list view shows a maximum of eight items, rather than partially clipping a ninth.
**Status:** Open

### VP-013 — Enable list scrolling in Installable view

**Area:** Installable view
**Component:** Installable list navigation
**Problem:** The Installable list does not scroll.
**Desired result:** Allow the list to scroll so entries beyond the visible set can be reached.
**Related:** Library scrolling may already have been fixed, but its current behavior is unverified; check it when addressing this item and keep the two views consistent if needed.
**Type:** Functional issue discovered during visual review
**Status:** Open

## Emulator Issues

### EMU-001 — Expose A/B and X/Y remapping for selected emulators

**Area:** Controllers / emulator input configuration
**Component:** Controller remapping settings
**Problem:** A→B and X→Y button remapping is not exposed as a user-configurable setting for Eden, Dolphin, and Nintendo-based RetroArch cores.
**Desired result:** Add a setting under Controllers to expose A→B and X→Y remapping for Eden, Dolphin, and Nintendo-based RetroArch cores.
**Status:** Open

### EMU-002 — Stop requiring confirmation when quitting Dolphin emulation

**Area:** Dolphin launch mode / emulation exit
**Component:** Confirmation when stopping current emulation
**Problem:** Quitting Dolphin's current emulation requires confirmation.
**Desired result:** Change Dolphin's launch mode so quitting does not require confirmation to stop the current emulation.
**Status:** Open

## Provider Issues

### PROV-001 — Review provider menus, including Steam overlay access

**Area:** Provider menus; Steam games
**Component:** Provider menu actions and Steam overlay access
**Problem:** Provider menus need a full review.
**Desired result:** Review provider menus comprehensively. Include opening the Steam overlay for Steam games in the review and ensure it is available as appropriate. Add a provider-menu action for both Eden and Dolphin that takes the application out of fullscreen so its UI is available for the user to change settings; this action should simply reveal the emulator UI.
**Status:** Open

### PROV-002 — Investigate missing Epic and GOG artwork and metadata

**Area:** Epic and GOG game presentation
**Component:** Game artwork and metadata
**Problem:** Most Epic and GOG games are not displaying artwork or metadata.
**Desired result:** Trace and correct the cause so Epic and GOG games display their artwork and metadata.
**Status:** Open

## Admin Panel Issues

### ADMIN-001 — Verify all connected/not-connected statuses

**Area:** Admin panel
**Component:** Connected/not-connected status indicators
**Problem:** The connected/not-connected statuses appear not to work reliably.
**Desired result:** Sweep all such statuses in the admin panel and verify that each accurately reflects the corresponding connection state and works as intended.
**Type:** Functional issue
**Status:** Open

### ADMIN-002 — Combine Integrations and Services into one view

**Area:** Admin panel
**Component:** Integrations and Services views
**Problem:** Integrations and Services are presented as separate views.
**Desired result:** Combine Integrations and Services into a single view.
**Status:** Open

## OOBE Issues

### OOBE-001 — Make Steam sign-in completion dismiss Steam

**Area:** OOBE / Steam sign-in
**Component:** Steam authentication flow
**Problem:** Completing sign-in does not dismiss/close Steam. If sign-in is already complete, the user still has to launch Steam to confirm it.
**Desired result:** Complete and acknowledge Steam sign-in without requiring an unnecessary Steam launch after sign-in is already complete, and dismiss Steam when sign-in completes.
**Type:** Functional/workflow issue
**Status:** Open

### OOBE-002 — Rework Epic and GOG setup presentation

**Area:** OOBE / Epic and GOG setup
**Component:** Provider setup UI
**Problem:** The UI around Epic and GOG setup is currently disjointed and confusing.
**Desired result:** Review and make the Epic and GOG setup flow coherent and understandable.
**Status:** Open

### OOBE-003 — Give each integration API key its own screen

**Area:** OOBE / integration setup
**Component:** API key entry screens
**Problem:** Integration API keys are bundled together on shared screens.
**Desired result:** Present each provider/integration API key on its own individual screen rather than bundling multiple keys together.
**Status:** Open

### OOBE-004 — Show completion status for every item on the final screen

**Area:** OOBE / final screen
**Component:** Installed/configured item summary
**Problem:** It may not be physically possible for every item to appear with its completion status on the final screen.
**Desired result:** Ensure the final screen can display every item and indicate for each whether it has been installed and configured.
**Acceptance notes:** Account for the full set of items so none are omitted due to screen space or layout constraints.
**Status:** Open

### OOBE-005 — Simplify integration credential testing and failure flow

**Area:** OOBE / integration setup
**Component:** API key and credential entry controls
**Problem:** Testing integration keys and credentials is clunky.
**Desired result:** Provide one button beneath the credential fields labeled “Test and Save.” If testing fails, show a clear error and prevent continuing; offer only “Retry” and “Skip” actions.
**Status:** Open

### OOBE-006 — Keep the Steam username visible while typing

**Area:** OOBE / Steam sign-in
**Component:** Steam username field
**Problem:** The Steam username is blanked/masked while it is being typed.
**Desired result:** Display the username normally while typing; it does not need to be obscured.
**Status:** Open
