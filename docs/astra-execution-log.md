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
Tests/runtime: baseline provenance inspection only; no deployment this run yet.
Commits: initial persistent execution checkpoint (see Git history).
Physical acceptance: list navigation/media/focus require controller/display review after implementation.
New defects: none proven.
Next action: inspect shared Library/Installable QML, navigation and catalogue models and existing tests; record confirmed root causes before edits.

## Continuation discipline

Update this log at each useful internally consistent step and commit each coherent batch. Keep implementation and physical acceptance distinct. Do not reboot, clear live credentials, destroy games/downloads, or alter immutable releases for validation. Continue to OOBE, provider/Questarr, settings, Recovery, visual and acceptance batches based on dependencies; no subagents requested. Source and Git history plus this log are the resumption authority.
