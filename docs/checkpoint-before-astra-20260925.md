# Astra starting baseline — 2026-09-25

This is the committed source/runtime baseline immediately before the GPT Astra
completion pass. The source checkpoint is immutable by Git commit/tag; the
development runtime remains mutable and non-promotable.

```text
baseline_commit=27413250763077fbd37e068c5ec462f6038fb3ac
baseline_tag=mudos-recovery-foundation-pre-astra-20260925-r2
branch=mudos/modularisation
candidate_release=/opt/lulu/releases/2741325-candidate-20260925220357
development_runtime=/opt/lulu/dev-current
immutable_current=/opt/lulu/current
immutable_current_target=/opt/lulu/releases/1b18377-candidate-20260919133154
checkpoint_date=2026-09-25
milestone=Recovery Foundation 1 complete; physical acceptance pending
```

The source checkpoint includes the intended pre-existing OOBE/provider
readiness, acquisition/provider, platform, UI/controller, emulation, and
validation work present in the development checkout, as well as Recovery
Foundation Milestone 1. The first checkpoint candidate
`6f640b5-candidate-20260925215829` is retained as an immutable superseded
artifact; runtime validation exposed its TCP peer-credential authorization
failure. The final checkpoint adds a random installation-local bearer token
for recovery mutations and is the `2741325` commit/tag/candidate above.

## Verification

- Python suite: 741 passed; recovery-focused subset: 56 passed.
- Native build: `scripts/build-lulu-shell.sh build/lulu-shell` passed.
- CTest: `catalogue-model-test` passed (1/1).
- Provisioning checks: `tests/test_provisioning.py` (15) and
  `tests/test_mudos_osk.py` (7) passed; compatibility payload manifest
  verified.
- Python compilation, shell syntax, `git diff --check`, and Recovery QML lint
  passed.
- QML runner: 89 passed, 9 failed. The exact same 9 failures were reproduced
  against pre-checkpoint `107bd60`; they concern existing navigation mapping,
  presentation ownership, and native-model test-environment behavior.
- Direct `cmake --build build/native` cannot link because the existing CMake
  target omits QtWebEngineQuick and xcb-keysyms linkage required by the
  unchanged baseline native source. The project shell build script succeeds.
- Candidate manifest verification passed; `RELEASE` records the baseline SHA,
  branch, source path, clean status, and immutable state. Candidate payload
  contains no symlinks, writable files, database/log/credential files, or
  bytecode. The known-good release manifest remains valid and unchanged.

## Runtime and trust boundary

`/opt/lulu/dev-current/NON_PROMOTABLE` records this baseline SHA with
`dirty=false` and `promotable=false`. Recovery, Admin, normal session,
Consoled, Acquisitiond, and InputPlumber were active after refresh; Sessiond,
Consoled, and Acquisitiond APIs responded. The normal Gamescope session was
running. The independent Recovery API and Admin Recovery status proxy both
reported all 13 components healthy. The recovery listener remains loopback
only; unauthenticated action requests returned 403, and a request with the
appliance token but an unknown action returned 400 without performing an
operation. No restart/power action was exercised.

Transmission and NZBGet units were active. The Questarr systemd unit was
inactive while its local health endpoint responded and the normalized health
component reported healthy. Admin login and status endpoints responded;
unauthenticated setup state correctly returned 401. No Admin password or
credential was read for this checkpoint.

## Rollback and remaining acceptance

The existing immutable known-good release remains
`/opt/lulu/releases/1b18377-candidate-20260919133154` and remains selected by
`/opt/lulu/current`. If the development runtime becomes unusable, run the
canonical `scripts/dev-runtime.sh immutable` on Lulu to remove development
overrides and restore units from the currently selected immutable release.
This does not activate the new candidate. The new candidate is preserved but
not promoted or activated.

Physical controller/D-pad/confirm/back acceptance of the standalone Recovery
UI, display/VT behavior, and physical Home review remain pending at Lulu. The
QML runner's nine baseline failures and the direct CMake target linkage gap
are documented above for Astra; neither is attributed to this checkpoint.
