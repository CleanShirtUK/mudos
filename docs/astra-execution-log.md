# Astra execution log

## Starting authority and safety (2026-09-26)

- Branch: `mudos/modularisation`; starting clean HEAD: `c918b668c5ded9467de7aecc63a92e756d894379`.
- Verified `git status --short` empty. Diff from baseline is solely the intended 80-line `docs/checkpoint-before-astra-20260925.md`.
- Immutable rollback SHA: `27413250763077fbd37e068c5ec462f6038fb3ac`.
- Tag: `mudos-recovery-foundation-pre-astra-20260925-r2`.
- Baseline release: `/opt/lulu/releases/2741325-candidate-20260925220357`.
- Existing selected known-good: `/opt/lulu/releases/1b18377-candidate-20260919133154`. Neither release is to be mutated; no final V1 promotion authorized.
- Development runtime: `/opt/lulu/dev-current`; canonical refresh: `scripts/dev-runtime.sh refresh`.
- Known baseline: Python 741 passed (+23 subtests); native project script and CTest passed; QML 89 passed / 9 pre-existing failures reproduced at `107bd60`; direct CMake linkage gap documented in starting checkpoint.
- Recovery Foundation 1 and CTRL-001/002, STEAM-001 accepted; do not reopen without regression evidence. Recovery physical acceptance remains pending. Wireless 360 idle disconnect is expected.

## Persistent backlog state

All frozen user backlog IDs remain OPEN unless explicitly updated below. Completion means engineering evidence, with physical acceptance tracked separately.

- SET-001: DEFERRED awaiting Bluetooth hardware; excluded from this run.
- VP-014: NEEDS PRODUCT SPECIFICATION; do not invent empty-library design.
- QUEST-004: DEFERRED; ordinary upstream browser login retained absent bounded safe bootstrap.
- VAL-004: packaging review permitted; destructive reinstall requires user coordination.
- VAL-005: final V1 promotion requires user acceptance.

## Current batch — shared Library / Installable behavior

Status: IN PROGRESS (reconnaissance).

Intended IDs: VP-009/010/011/012/013/015/016/017/018/019. Inspect shared model/QML architecture first; fix confirmed defects together and test relevant contracts. Trace metadata separately if its ownership requires a backend batch.

Diagnosis: StoreHome retained six-column grid movement despite using LibrarySpace; shell Left/Right moved games and shoulders categories. Shared list viewport was arbitrary height, previews cropped, fallback glyph always behind loading images, metadata bottom/left aligned.
Implementation (unvalidated intermediate): one-row vertical movement, Left/Right categories and no shoulder categories; selection feedback to StoreHome; shared integral maximum-eight-row viewport; tighter category spacing; fit/black preview backing and loading fallback gating; trailing right-aligned metadata beneath artwork. VP-011/018/019 still require investigation.
Additional implementation: VP-019 uses an explicit provider category dimension (All/Steam/Epic/GOG plus platform categories), with a shared JS projection helper and executable provider-vs-PC filtering test. Initial targeted checks: new projection QML test 3 passed; Store acquisition stability Python tests 5 passed. Shared real-component selection/scroll test added, execution pending.
Validation update: real LibrarySpace test passed (3 including lifecycle), traversing 30 entries and checking viewport containment/integral maximum-eight-row geometry. Full QML: 95 passed, exactly the 9 documented baseline failures. First full Python invocation omitted PYTHONPATH (collection errors); correct command is `PYTHONPATH=src python -m pytest -q --tb=short`. Then identified obsolete source-string layout expectations and compatibility payload equality; updated them to the new specified layout and canonical-source authority. Latest run 740 passed/1 outdated assertion, now corrected; final rerun pending. Keyboard Left/Right and shoulder hints also aligned with controller behavior. Mouse selection uses an explicit external selection signal to preserve the parent-owned binding.
New defect TEST-001: provisioning test wrongly required source QML to equal historical `deploy/payload`; corrected to lint canonical and compatibility trees independently while retaining payload manifest verification. No payload mutation.

### First implementation checkpoint

- VP-009/010/012/013/015/016/017/019: IMPLEMENTED; executable list/projection checks passed; PHYSICAL ACCEPTANCE PENDING for controller/display presentation.
- TEST-001: DONE.
- Full Python final result: **741 passed, 23 subtests passed** (includes provisioning and OSK checks).
- QML: **95 passed, 9 baseline failures**; no new failures.
- VP-011 remains OPEN (glass/border treatment); VP-018 remains OPEN (backend metadata/media trace).
- Next: commit this bounded checkpoint, refresh canonical dev runtime and verify provenance/services; then metadata/media and remaining shared surfaces.

## Current batch — catalogue/media freshness (VP-018 / PROV-002)

Previous checkpoint: `181de6a`; canonical dev refresh launched in background (result pending).
Deployment completed successfully: native build passed through canonical refresh; `/opt/lulu/dev-current/NON_PROMOTABLE` records `181de6a96902226d7be227f4f283eb8ad0a5e750`, dirty=false. Session, Consoled, Acquisition, Admin, Recovery and InputPlumber all active. `/opt/lulu/current` still selects `1b18377-candidate-20260919133154`. CTest 1/1 passed. No physical input/visual acceptance claimed.
Confirmed root cause: refresh captures catalogue records/eligible presentation IDs **before** provider reconciliation; newly discovered Epic/GOG/RomM records are excluded from matching/artwork in the same pass. Enrichment also receives pre-match records, ignoring freshly established canonical identity. Additional METADATA-001: `enrich_all([])` incorrectly expands an explicitly empty eligible set to the entire catalogue. Implement post-discovery eligibility and fresh matched records, with regression tests using temporary databases and no live credentials. Broader live missing-art diagnosis remains pending; do not claim all upstream omissions solved by these fixes.

Implemented and validated: post-discovery eligibility, post-match enrichment inputs, explicit empty scope honored. Temporary SQLite regression runs actual refresh/reconciliation for both Epic and GOG and checks fresh IGDB identity while preserving installable provider ownership. Targeted metadata suite 23 passed +2 subtests; full Python **743 passed +25 subtests**. METADATA-001 DONE; VP-018/PROV-002 PARTIALLY IMPLEMENTED, live residual diagnosis remains.

Read-only runtime aggregate evidence (no titles or secrets exported): Epic 6 available /4 canonical /4 local previews; GOG 2/2/2; Steam 94/91/91; RomM 79/74/31. Missing Epic records are one ambiguous and one no-exact title/platform match, so do not substitute fake metadata. Missing RomM previews: 43 matched records without source screenshot or IGDB enrichment cache, plus 5 unmatched/ambiguous. Continue by tracing backfill/cache state for these records before claiming VP-018 closed. Recovery `/v1/status` reports overall healthy, 13 healthy components, one connected controller. `job_snapshot_available=false` despite acquisition API available is an observation to investigate in Recovery status audit (not yet proven new defect).

Next checkpoint: commit bounded metadata freshness fix, then continue missing-media diagnosis or another independent actionable batch. Runtime remains at clean `181de6a` until next canonical refresh.

## Current batch — actionable acquisition failures (VP-005)

Metadata checkpoint committed as `dcd33fb`.
Confirmed DownloadsHome maps almost every error code to “Provider error”, offers Retry regardless of retryable flag, and NotificationBroker emits success/start events but no failures. Trace service error categories before implementing generic failure presentation/notification.

VP-005 IMPLEMENTED (physical acceptance pending): Downloads shows the provider's actual error message and code with a wrapping failure row, labels failed rows as failed rather than paused, and gates Retry on both job and error capabilities. JobManager rejects non-retryable retries at the API boundary; Clear remains available without deleting provider/game data. Broker emits one transition-only failure notification with operation-specific title, reason, and correct retry/corrective-action guidance; historical failures are not replayed. RomM's unsupported-platform error already has a specific message and non-retryable code, now surfaced instead of “Provider error”. Updated a persistence test fixture that previously retried an explicitly non-retryable error; added backend, broker and real QML behavior coverage.

Validation: targeted Python 36 passed; complete Python **746 passed +25 subtests**; native CTest **1/1 passed**. Targeted QML **3 passed**; full QML **98 passed, exactly 9 pre-existing failures** (same navigation/presentation/native-model failures as baseline). `git diff --check` clean. Next: commit, canonical dev refresh and provenance/service inspection; then continue independent backlog work, starting with low-risk visual/layout defects or media diagnosis. No live acquisition/retry/cancel was triggered for testing.

REC-002 reconnaissance only (still OPEN): live `/boot/limine.conf` is generated CachyOS tree with linux-cachyos, linux-cachyos-bc250, LTS and snapshot/EFI fallbacks; default_entry=2 and remember_last_entry=yes. `/etc/default/limine` owns normal cmdline. Any implementation must preserve checksummed kernel/module paths, maintain debug entry across kernel updates, and disable remembered Debug selection becoming default. No boot configuration modified. `lulu.target` and session template currently have no debug marker condition. Resume in dedicated safe boot batch rather than mix boot changes into UI work.
Tests/runtime: baseline provenance inspection only; no deployment this run yet.
Commits: initial persistent execution checkpoint (see Git history).
Physical acceptance: list navigation/media/focus require controller/display review after implementation.
New defects: none proven.
Next action: inspect shared Library/Installable QML, navigation and catalogue models and existing tests; record confirmed root causes before edits.

## Continuation discipline

## Continuation checkpoint — 2026-09-26

- VP-005 committed `e0b9978`. Canonical `scripts/dev-runtime.sh refresh` completed from clean committed HEAD; `/opt/lulu/dev-current/NON_PROMOTABLE` records `e0b9978a6e31c00d7ad1e6a3d84c6ac2f4c62bfd`, `dirty=false`, `promotable=false`. Actual `lulu-session@2`, `lulu-consoled`, `lulu-acquisition`, `lulu-admin`, and `mudos-recovery` services active; `/opt/lulu/current` still points at old selected `1b18377` immutable release. No physical controller/display acceptance claimed.
- VP-003 IMPLEMENTED (physical visual acceptance pending): four Home Library dimension cards now have distinct Provider (existing plug), Game Mode (`f0c0`), Genre (`eeb6`), Platform (`f11b` gamepad) glyphs through shared semantic asset mapping. Flathub Store card now renders `f324` instead of generic fallback, without coupling the shared Store component to Flathub. Unknown/default modes keep collection fallback; other Store identities retain behavior. QML asset test verifies all exact glyphs and uniqueness.
- VP-003 validation: targeted Python 73 passed, targeted QML 5 passed; full Python **746 passed +25 subtests**; CTest 1/1; full QML **99 passed, exactly 9 baseline failures**. `git diff --check` clean. Next: commit and canonical dev refresh, then resume other actionable backlog including VP-001/004/011, OOBE and Recovery safety batches. Physical visual acceptance pending.
- VP-003 committed `347259a`; canonical dev refresh completed from clean `347259ac45165ad4115466f59137eac7e7727926`, `dirty=false`. The selected immutable release remains `1b18377`, unchanged; Session, Consoled, Acquisition, Admin, Recovery units active. Home icon appearance still needs physical display review.
- OOBE-006 IMPLEMENTED (physical UI acceptance pending): the Steam username is rendered as visible text in the setup credential form and the in-shell Steam username editor; Steam passwords and other secret inputs remain masked. Existing `secret` save route and secret-backed storage for the username are unchanged. Regression checks assert both presentation paths and password handling. Targeted Python 94 passed; complete Python **747 passed +25 subtests**; CTest 1/1; full QML **99 passed / 9 baseline failures**; compileall and diff check clean. Next: commit, canonical dev refresh, then continue remaining backlog. No live authentication or credential data changed.

Update this log at each useful internally consistent step and commit each coherent batch. Keep implementation and physical acceptance distinct. Do not reboot, clear live credentials, destroy games/downloads, or alter immutable releases for validation. Continue to OOBE, provider/Questarr, settings, Recovery, visual and acceptance batches based on dependencies; no subagents requested. Source and Git history plus this log are the resumption authority.
