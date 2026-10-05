# Active Backlog

Current engineering work is tracked here. Historical reconciliation notes are
retained in `docs/reconciliation-backlog.md` and are not the status authority.

## ACTIVE

### QUIVER-001 — Quiver acquisition and library provider

**Status:** ACTIVE — contract/authority boundary blocked; no implementation
claimed.

- Repository and upstream investigation is recorded in
  `docs/quiver-provider-contract.md`. This checkout has no Quiver integration.
- The public project matching the name, Quiver Launcher, has a name-based CLI
  (`--list`, `--download`, `--update`, `--run`, `--uninstall`) and its own
  library/app folders, but no structured acquisition-job API. Questarr is a
  separate, retired integration and must not be restored.
- Before implementation, confirm whether this is the intended Quiver and
  whether Mudos should consume a future/other Quiver API or own a separate
  GitHub/GitLab release acquisition backend. These choices change acquisition,
  catalogue, installation, and launch authority; do not guess or treat the
  upstream GUI's local files as an API.

### EDEN-001 — Eden AppImage migration acceptance

**Status:** ACTIVE. Do not close or promote until both regressions are fixed and
the operator completes physical acceptance.

- **EDEN-001A — MK8 update/DLC discovery:** The v0.8.1 runtime loads its config
  below `XDG_CONFIG_HOME/eden`, which for Mudos is
  `~/.config/lulu/providers/eden/config/eden/qt-config.ini`. The prior adapter
  edited `~/.config/eden/qt-config.ini`; the runtime config had
  `Paths\\external_content_dirs\\size=0`. v0.8.1 scans configured NSP/XCI
  directories into an in-memory `ExternalContentProvider`; there is no
  persistent external-content database/index. Point the adapter at the active
  provider config and ensure the ROM directory is registered there. Do not
  move, reinstall, register, or delete update/DLC NSP files during diagnosis.
- **EDEN-001B — controller input:** Use the generic live SDL/InputPlumber
  identity and Eden's native serialization contract; do not add controller
  allowlists or pin event device numbers. The original Mudos face-button map
  (A/B/X/Y = SDL buttons 0/1/2/3) is the correct baseline and must be retained.
  Eden's v0.8.1-authored `gp1` donor was preserved at
  `/home/lulu/.config/lulu/providers/eden/config/eden/input/gp1.ini.eden-v0.8.1-donor`;
  the updated `gp1.ini` now contains the original Mudos-generated mapping.
  Donor profile checksum: `6d9a889c66df2ac7561dbb9681e6e73ca9110dab2ed75d5ced3e91db274b4537`.
  Updated profile checksum: `8447a50eade12c04794a930cdb9364d312ff8eda77caaef2d53f46e9cdbc551b`.
  Physical ABXY correctness remains an operator-confirmed fact, not something
  inferred from Eden's saved mapping.
- Keep the existing pinned AppImage, coherent NAND/profile state, keys and
  firmware, Gamescope ownership, Mudos controller assignment policy, and
  prompt Eden-to-Mudos lifecycle return.
- Preserve the old Flatpak tree as read-only donor evidence. Leave
  `/opt/lulu/current` untouched; development deployment is restricted to
  `/opt/lulu/dev-current` and remains separate from promotion.
- Required operator acceptance: MK8 v4.0.0 with existing DLC active, controller
  input, clean lifecycle return, rendering, and remaining requested checks.

**Implementation status:** The adapter now targets the provider XDG config Eden
actually reads, registers the Switch ROM directory there, and retains the
original Mudos button map. Runtime-path regression coverage is implemented; the
full test suite passes (1,169 tests and 85 subtests). Commit `fe840db` was
deployed to `/opt/lulu/dev-current` on 2026-10-04. The dev tree is explicitly
`promotable=false` and records `dirty=true` because pre-existing, uncommitted
session/lifecycle work was included in the dev refresh. `/opt/lulu/current`
still points to the immutable candidate release. Physical acceptance has not
occurred.

**Next:** Obtain operator acceptance on dev-current for MK8 v4.0.0 plus DLC,
controller input, clean lifecycle return, rendering, and remaining requested
checks. Keep EDEN-001 ACTIVE until those checks pass. Do not promote this dirty
dev runtime.
