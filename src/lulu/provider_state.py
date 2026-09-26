"""Canonical provider capability state; presentation layers may only relabel it."""

from __future__ import annotations


def normalized_provider_state(*, status: str, installed: bool, selected: bool,
                              configured: bool | None = None,
                              authenticated: bool | None = None,
                              connected: bool | None = None,
                              catalogue_reconciled: bool | None = None,
                              acquisition_configured: bool | None = None,
                              running: bool | None = None,
                              healthy: bool | None = None,
                              skipped: bool = False, failed: bool = False,
                              degraded: bool = False) -> dict[str, object]:
    """Keep optional/unknown capabilities distinct from negative evidence."""
    ready = status == "ready"
    for evidence in (installed, selected, configured, authenticated, connected,
                     catalogue_reconciled, acquisition_configured, running, healthy):
        if evidence is False:
            ready = False
    return {
        "status": status,
        "installed": bool(installed), "selected": bool(selected),
        "configured": configured, "authenticated": authenticated,
        "connected": connected, "catalogue_reconciled": catalogue_reconciled,
        "acquisition_configured": acquisition_configured,
        "running": running, "healthy": healthy, "ready": ready,
        "skipped": bool(skipped), "failed": bool(failed), "degraded": bool(degraded),
    }
