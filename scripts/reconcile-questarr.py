#!/usr/bin/env python3
from lulu.questarr_reconciler import QuestarrReconciler


if __name__ == "__main__":
    result = QuestarrReconciler().reconcile()
    print(f"questarr reconciliation status={result.status} transmission={result.transmission} "
          f"nzbget={result.nzbget} prowlarr={result.prowlarr} indexers={result.indexers}")
