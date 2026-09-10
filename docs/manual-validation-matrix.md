# Manual Validation Matrix

Status: evidence reconciliation, 2026-09-10. This matrix does not claim that
interactive testing was performed during this documentation pass. `PASS` is
used only where an existing dated evidence record supports the result.

| Area | Status | Existing evidence or reason |
| --- | --- | --- |
| Boot/session entry | INCOMPLETE | systemd/session architecture exists; complete appliance boot proof is not recorded |
| Home navigation | PASS | `framework-checkpoint-20260909.md`, `ui-checkpoint-20260909.md` |
| Library navigation | PASS | `ui-checkpoint-20260909.md`; QML/navigation tests |
| Settings navigation | PASS | `system-settings-status-20260909.md`; direct category/page routing is evidenced |
| Controller ownership | INCOMPLETE | routing evidence proves bounded mode changes, not autonomous end-to-end ownership |
| Controller disconnect/recovery | PASS | `controller-architecture.md`, `steam-input-routing-evidence.md` |
| Steam launching | PASS | `steam-session-architecture-baseline.md` records repeated Cuphead launches; live-path ownership remains PARTIAL |
| Steam return to Mudos | PASS | same dated baseline records natural return after normal exit |
| Emulator launching | PASS | `retroarch-runtime-validation-20260909.md` records two direct NES launches; other providers NOT TESTED |
| Emulator return to Mudos | PASS | RetroArch direct path records normal return; generalized provider behavior INCOMPLETE |
| Guide invocation | NOT TESTED | implementation exists; no substantive behavioral evidence in repository |
| Guide application termination | NOT TESTED | native actions exist; no behavioral evidence |
| Abnormal application termination | NOT TESTED | recovery code exists; no end-to-end evidence |
| Catalogue population | PASS | catalogue/provider and local-content tests plus implementation inventory |

## Interpretation

- PASS is scoped to the exact path and environment in the cited evidence, not a
  blanket claim for every deployment or provider.
- NOT TESTED means the repository contains no adequate result.
- INCOMPLETE means part of the area is evidenced but its full boundary is not.
- BLOCKED should be added when a repeatable test cannot proceed because of a
  documented environment prerequisite, such as the unconfigured audio output.
