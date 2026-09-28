#!/usr/bin/env python3
from lulu.onboarding import onboarding_state
from lulu.questarr_reconciler import QuestarrReconciler
from lulu.provider_readiness import ProviderReadinessStore


if __name__ == "__main__":
    setup = onboarding_state()
    if "questarr" not in setup.get("selected_providers", []):
        print("questarr reconciliation skipped reason=not-selected")
        raise SystemExit(0)
    readiness = ProviderReadinessStore().get("questarr")
    if readiness.get("status") != "ready":
        print("questarr reconciliation skipped reason=not-ready status="
              f"{readiness.get('status', 'unknown')}")
        raise SystemExit(0)
    result = QuestarrReconciler().reconcile()
print(f"questarr reconciliation status={result.status} transmission={result.transmission} "
      f"nzbget={result.nzbget} prowlarr={result.prowlarr} "
      f"metadata={result.metadata} indexers={result.indexers}")
