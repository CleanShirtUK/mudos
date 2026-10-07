.pragma library

function completedState(expanding, target) {
    if (expanding) {
        return {
            progress: 1,
            contentOpacity: 1,
            space: target,
            libraryTransitioning: false,
            storeTransitioning: false,
            transitionState: "EXPANDED",
            handoffPending: false
        }
    }
    return {
        progress: 0,
        contentOpacity: 0,
        space: "home",
        libraryTransitioning: false,
        storeTransitioning: false,
        transitionState: "ACTIVATING",
        handoffPending: true
    }
}
