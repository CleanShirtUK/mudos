# OOBE / recovery rehearsal defect ledger

Append findings in order. Do not repair defects during the rehearsal.

1. **OOBE-001 — Handoff URL omits setup path**
   - Observed: Online onboarding advertises `http://mudos.local`; expected setup handoff is `http://mudos.local/setup`.
   - Disposition: Work around by manually opening `/setup`; retest after correction.

2. **OOBE-002 — Local onboarding actions use small standard buttons**
   - Observed: `Set Up Locally` and `Continue to Home` are not presented as Mudos controller-focusable controls.
   - Disposition: Work around with keyboard/mouse; do not fix mid-rehearsal.

3. **OOBE-003 — Wi-Fi screen controller navigation not physically verified**
   - Source review: `ui/InternetSettings.qml` exposes row activation and the console shell routes confirm to it. That is insufficient to verify the physical controller, OSK focus/return, connect, and Back behavior.
   - Verification required: D-pad through Wi-Fi toggle, current connection, discovered network rows and Back; confirm a secured network; verify OSK opens and focus returns; cancel before connecting to an unintended network; confirm connection only on the user's chosen network.
   - Status: Pending physical console pass.

4. **OOBE-004 — Wi-Fi onboarding can escape into empty Mudos**
   - Observed: Back/escape from mandatory first-run Wi-Fi setup can enter an empty Mudos shell/Home before connectivity is available.
   - Expected: While connectivity is a mandatory setup prerequisite, Back must not leave onboarding for an unusable shell.
   - Correction: Back now routes through the onboarding owner even if connectivity changes. It first closes Wi-Fi credentials, then returns from Wi-Fi settings to the onboarding actions; Back on the onboarding surface itself cannot enter the ordinary shell. Only the existing explicit Continue to Home dismissal or completed setup releases that ownership. Offline users can still deliberately continue offline.
   - Status: Source/QML policy and shell wiring tests pass; physical Wi-Fi/controller and browser acceptance remain pending.

5. **OOBE-005 — Wi-Fi OOBE presentation looks like Settings**
   - Observed: OOBE reuses the functional Settings Wi-Fi page.
   - Expected: Retain shared network behavior while presenting an intentional first-run onboarding surface.
   - Scope: Later OOBE/UX pass; not a blocker for underlying Wi-Fi functionality.

6. **OOBE-006 — Questarr is placed in the wrong setup stage**
   - Observed: Questarr appears among API-style integrations although there is little useful configuration there.
   - Expected: Treat it conceptually as a selectable functional component/plugin on an initial “Providers and Plugins” selection page.
   - Scope: Setup taxonomy; defer except for RomM correction.

7. **OOBE-007 — Provider install failure is lost in review**
   - Observed: Steam install explicitly failed, but review collapsed this to “selected; installation may be incomplete.”
   - Expected: Preserve authoritative selected/installing/installed/failed/configured/authenticated/ready status through review.
   - Follow-up: The installer unit's failed state and diagnostic are now carried by setup provider state into review; the provider-selection screen also shows that escaped failure reason when the user returns to retry. Source-generated JavaScriptCore coverage checks both screens. A start request rejected before the unit records a failure, and fresh-install/physical browser behavior, are not yet proven durable across reload.

8. **OOBE-008 — Eden and PCSX2 review status disagrees with provider page**
   - Observed: Both appeared installed without errors on provider selection, but review reported both not installed.
   - Expected: Read one authoritative provider state centrally.

9. **OOBE-009 — Setup should end at normal Mudos web home**
   - Observed/desired architecture: Setup currently terminates in a setup-specific completion experience.
   - Expected: Normal `mudos.local` becomes the Mudos admin/home portal and users land there after setup.

10. **OOBE-010 — Mudos admin needs one authoritative password**
    - Future architecture: Avoid separate web-admin and Linux credentials; authenticate the web admin against the authoritative Mudos Linux account via PAM/system auth or equivalent.
    - Future migration: Remove legacy `lulu` naming and establish final `mudos` account where appropriate; the one account password is the web admin credential. Do not perform account migration during this work.

11. **OOBE-011 — Setup completion transition should enter normal startup/Home**
    - Observed: A “Setup complete” message is presented as the final console experience.
    - Expected: Finish Setup fades current surface to black, reuses the existing startup intro, then enters Home. Do not duplicate the intro for OOBE.
    - Scope: Later transition/polish pass.

12. **OOBE-012 — NZBGet was not configured by onboarding**
    - Observed: Setup did not collect/configure required NZBGet connection/authentication information.
   - Follow-up: Audit actual NZBGet requirements and include it correctly in setup; defer during RomM-only correction unless a shared readiness abstraction is directly useful.
   - Status follow-up: A healthy NZBGet RPC no longer marks the Usenet provider Ready. Setup distinguishes a missing enabled news-server host/credential references from a configured-but-not-transfer-validated backend. The existing separate news-server Test and Save remains the connection test; real submission/fresh-install acceptance is still outstanding.

13. **OOBE-013 — Transmission setup is unproven**
    - Observed: Fresh onboarding did not establish whether Transmission installation/configuration is correct.
   - Follow-up: Audit installation, RPC, ownership paths, readiness, and Questarr submission. Development-machine state is not proof of fresh-install behavior.
   - Status follow-up: A healthy Transmission RPC is now Configured, not Ready; a real transfer/Questarr submission remains unproven.

14. **OOBE-014 — Provider installation is confused with readiness**
    - Observed: Package/install state was shown without required authentication/readiness proof.
   - Expected lifecycle: selected → installed → configured → authenticated if required → validated → initial reconciliation/sync completed → ready.
   - Status follow-up: Setup no longer labels installed local providers/emulators (RetroArch, Dolphin, PCSX2, Eden, Lutris, Flatpak) Ready merely because their binaries exist. It reports Installed and distinguishes game/content launch validation as outstanding. Account-backed and RomM readiness remain separately owned; a full fresh-state lifecycle and physical launches still require acceptance.
   - Validation follow-up: After setup saves integration credentials, any previous persisted success for that integration becomes retest-required until the Test and Save validation completes. Review re-reads the persisted state, so a concurrent tab cannot use an old in-memory success. Other Admin configuration paths still need separate invalidation coverage.
   - Account follow-up: A previously persisted Ready for Steam/Epic/GOG no longer overrides the current provider authentication result; Steam additionally requires current ownership API configuration. No live account session was changed for this correction.

15. **OOBE-015 — Steam authentication is missing from onboarding**
    - Observed: Steam install/detection did not establish a usable authenticated account.
    - Follow-up: Add the appropriate Steam authentication flow before Steam may be considered Ready; defer during RomM-only correction.

16. **OOBE-016 — Epic authentication is missing from onboarding**
    - Observed: Epic install/detection may be present, but fresh OOBE did not establish its authentication lifecycle; development authentication must not mask this.
    - Follow-up: Defer during RomM-only correction.

17. **OOBE-017 — GOG authentication is missing from onboarding**
    - Observed: GOG install/detection is not equivalent to authenticated/provider-ready state.
    - Follow-up: Establish fresh-user authentication required by the current provider; defer during RomM-only correction.

18. **OOBE-018 — Questarr is not operational after setup**
    - Observed: Questarr is present conceptually in setup but not operational after onboarding.
   - Follow-up chain: selection → installation → service/container readiness → configuration → acquisition backend connectivity → catalogue/storefront behavior. Do not repair during RomM-only correction.
   - Readiness follow-up: A running Questarr service plus a healthy local downloader no longer asserts Ready. The public read-only first-run status reports whether an upstream account exists; currently it reports no users on Lulu. Setup now asks for the upstream account rather than calling the integration Ready. Authenticated downloader/indexer configuration and initial reconciliation still require operator setup and separate verification; no credentials or Questarr data were changed.

19. **OOBE-019 — Freshly configured RomM does not contribute Installable content**
    - Observed: RomM appeared configured in setup/review, but Home had no content in Installable.
    - Root cause confirmed: OOBE treated URL plus a saved encrypted token as “configured” without authentication. The production RomM client reads the same OOBE URL (`/home/lulu/.config/lulu/plugins/romm/settings.toml`) and SecretStore slot (`/home/lulu/.local/share/lulu/secrets/romm/api-key.cred`), but the current fresh-run token is rejected by RomM with HTTP 401. Fresh startup initially syncs Steam/local only; RomM was deferred to the periodic catalogue reconciliation, and setup did not initiate a sync.
    - Correction in working tree: Add explicit RomM readiness persisted against a URL/token fingerprint; classify rejected credentials as invalid; reload current setup credentials for production reconciliation; make successful RomM validation trigger the normal `RefreshStages romm` reconciliation; mark Ready only after persisted records and Installable projection are reconciled. Client errors retain HTTP status class without exposing credentials.
    - Validation: The deployed production RomM client now validates the explicitly schemed saved URL and Client API Token; the normal `RefreshStages romm` path reconciled successfully and persisted Ready. The API returned 182 records; 84 normalized catalogue records were persisted and projected into Installable. Live validation and sync are fixed; physical UI review remains pending.

20. **OOBE-020 — Installable is empty after setup**
    - Observed: After setup, normal Installable contained no content. The live RomM source currently contributes zero records because its fresh OOBE token is rejected; Steam/GOG/Epic authentication and Questarr operation also remain outstanding contributors.
    - Acceptance contract: selected source → installed → configured → authenticated → validated → reconciled → content visibly contributes to Mudos.
    - Status: Live RomM validation confirms 84 normalized RomM catalogue records and 84 records in the normal Installable projection, across systems including NDS, GBA, PS2, and PSX. No catalogue games are currently installed locally, so installed-game deduplication is deterministic-test coverage only. Other providers remain outstanding; do not mark OOBE globally complete.

21. **OOBE-021 — Recovery routes rejected minimal-client requests**
    - Observed: The standalone recovery UI could not use the normal admin authentication/CSRF gate when the shell was unavailable.
    - Correction: Recovery operations are available to the recovery client through narrowly scoped recovery routes.
    - Status: Corrected in source; runtime deployment and non-destructive recovery acceptance remain pending.

22. **OOBE-022 — Provider plugin installer authorization and NZBGet package path were incomplete**
    - Observed: The onboarding installer lacked a complete authorized path for selected service plugins, including NZBGet.
    - Correction: Allowlisted installer dispatch, constrained authorization, and the NZBGet package path were added.
    - Status: Corrected in source; fresh-state/live validation remains pending and broad Questarr integration remains out of scope.

23. **OOBE-023 — Optional provider/plugin reconciliation is not readiness-gated**
    - Observed: Ordinary runtime refresh could start Questarr reconciliation without persisted selection/readiness, and optional catalogue stages could run because implementations were installed.
    - Expected: Optional work requires persisted selection plus its configuration/authentication/validation prerequisites; Ready also requires a successful initial reconciliation.
    - Correction in progress: Consoled now skips unselected Steam/Epic/GOG, RomM, and component catalogue stages; Steam/Epic/GOG require authentication state before provider calls, RomM requires fingerprint-matched validation/readiness, and dev refresh no longer enables or starts the Questarr reconciliation unit.
    - Status: Source now gates selected catalogue sources by selection/auth/readiness, recovers stale `syncing` records, removes all unconditional Questarr reconciliation triggers, and makes absent NZBGet provisioning a no-op. Canonical dev refresh now succeeds and the services start. Questarr itself remains excluded pending a complete explicit Ready lifecycle; the refresh initially exposed and then corrected unconditional optional-provider provisioning.

24. **OOBE-024 — Active defect ledger was stored inside immutable quarantine**
    - Observed: The active ledger was located under `/var/lib/lulu/dryrun-backup/20260925T0000+0100`.
    - Correction: Established this live project ledger at `docs/oobe-defect-ledger.md`, carrying forward OOBE-001–020 and adding later findings. The quarantined original remains unchanged.
    - Status: Fixed; use the repository ledger for ongoing work.

25. **OOBE-025 — Scheme-less RomM URL produces a confusing validation error**
    - Observed: A bare hostname proceeds to server validation and can produce a low-level error.
    - Expected: Show a clear RomM URL field error requiring an explicit `http://` or `https://` scheme; do not force HTTPS for local/self-hosted installations.
    - Correction in progress: Added browser field validation and matching server-side validation.
    - Status: Explicit-scheme browser/server validation is deployed; unit coverage passes. Browser field-level error behavior is source-verified; physical retest remains pending.

26. **OOBE-026 — Reset Mudos forgets explicit Continue to Home decision**
    - Observed: After setup edits/reset, the console re-entered OOBE despite a previous explicit Continue to Home choice.
    - Expected: Setup progress and OOBE dismissal are orthogonal persisted state; setup edits do not undo dismissal.
    - Correction in progress: Persist `oobe_dismissed` independently, migrate prior dismissal timestamps, and preserve completed state during later setup edits.
    - Status: Orthogonal persisted state and restart-regression coverage are deployed. After the canonical session refresh, live setup state reports `oobe_dismissed=true` and `required=false`; physical controller acceptance remains pending.
