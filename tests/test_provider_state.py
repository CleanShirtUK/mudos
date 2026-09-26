from lulu.provider_state import normalized_provider_state


def test_ready_requires_positive_evidence_for_known_capabilities():
    state = normalized_provider_state(
        status="ready", installed=True, selected=True, configured=True,
        authenticated=True, connected=True, catalogue_reconciled=True,
        acquisition_configured=False, running=True, healthy=True)
    assert state["ready"] is False
    assert state["acquisition_configured"] is False


def test_unknown_evidence_is_distinct_from_negative_evidence():
    unknown = normalized_provider_state(status="ready", installed=True, selected=True)
    negative = normalized_provider_state(status="ready", installed=True, selected=True,
                                         connected=False)
    assert unknown["ready"] is True
    assert negative["ready"] is False


def test_running_does_not_mean_ready_or_configured():
    state = normalized_provider_state(status="running", installed=True, selected=True,
                                      configured=False, running=True, healthy=True)
    assert state["running"] is True
    assert state["ready"] is False
    assert state["configured"] is False
