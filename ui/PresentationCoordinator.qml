import QtQuick

// The shell-level owner for presentation choreography. It owns timing and
// presentation state, while content components retain their authoritative
// layout and interaction state.
Item {
    id: coordinator

    readonly property string hiddenState: "HIDDEN"
    readonly property string transitioningInState: "TRANSITIONING_IN"
    readonly property string presentedState: "PRESENTED"
    readonly property string transitioningAwayState: "TRANSITIONING_AWAY"
    property string contentState: hiddenState

    // Startup tuning is deliberately centralized here for physical tuning.
    readonly property int contentRevealAt: 110
    readonly property int titleStartAt: 110
    property int titleCount: 4
    readonly property int titleDuration: 400
    readonly property real titleOvershoot: 0.20
    readonly property real titleApproachFraction: 0.62
    readonly property int titleStagger: 90
    readonly property real titleStartupSafetyMargin: 24
    readonly property int titleTrainDuration:
        titleDuration + Math.max(0, titleCount - 1) * titleStagger
    readonly property int titleTrainCompletionAt:
        titleStartAt + titleTrainDuration
    readonly property int cardStartAt: titleStartAt
    readonly property int cardDuration: titleTrainDuration
    readonly property real recentRowOvershootPixels: 40
    readonly property real recentRowSafetyMargin: 24
    // Presentation blur tuning is expressed in rendered pixels. The signed
    // velocity remains separate from this visual mapping.
    readonly property real motionBlurGain: 8
    readonly property real motionBlurMaxPixels: 64
    readonly property real motionBlurDeadZone: 0.03
    readonly property int hintsStartAt: 780
    readonly property int hintsDuration: 500
    readonly property real hintsTravel: 120
    readonly property int hintsEasePower: 4
    readonly property int recentRowCompletionAt: cardStartAt + cardDuration
    readonly property int hintsCompletionAt: hintsStartAt + hintsDuration
    readonly property int startupDuration: Math.max(contentRevealAt,
        titleTrainCompletionAt, recentRowCompletionAt, hintsCompletionAt)

    property real startupClock: 0
    readonly property bool startupRunning: startupAnimation.running
    readonly property bool contentVisible:
        contentState !== hiddenState
        && (contentState !== transitioningInState
            || startupClock >= contentRevealAt)
    readonly property bool contentPresented: contentState === presentedState
    readonly property bool contentHidden: contentState === hiddenState
    readonly property bool contentTransitioning:
        contentState === transitioningInState
        || contentState === transitioningAwayState

    function clamp01(value) {
        return Math.max(0, Math.min(1, value))
    }

    function easeOut(value, power) {
        return 1 - Math.pow(1 - clamp01(value), power)
    }

    function titleTravelProgress(index) {
        var local = (startupClock - titleStartAt - index * titleStagger) / titleDuration
        if (local <= 0)
            return 0
        if (local >= 1)
            return 1
        // Fast approach through a small, deliberate overshoot, then a short
        // non-elastic correction to the exact final X.
        if (local < titleApproachFraction)
            return (1 + titleOvershoot)
                * easeOut(local / titleApproachFraction, 4)
        var correction = easeOut((local - titleApproachFraction)
                                 / (1 - titleApproachFraction), 2.3)
        return 1 + titleOvershoot * (1 - correction)
    }

    function titleStartupTranslation(restingLeft, titleWidth) {
        return -(restingLeft + titleWidth + titleStartupSafetyMargin)
    }

    function titleOffset(index, restingLeft, titleWidth) {
        var startupTranslation = titleStartupTranslation(restingLeft, titleWidth)
        return startupTranslation * (1 - titleTravelProgress(index))
    }

    function recentRowBackC1(rowRightEdge) {
        var travel = Math.max(rowRightEdge, 0) + recentRowSafetyMargin
        var target = recentRowOvershootPixels / travel
        var coefficient = Math.max(0.01, Math.pow(27 * target / 4, 1 / 3))
        for (var iteration = 0; iteration < 8; iteration++) {
            var denominator = coefficient + 1
            var value = 4 * Math.pow(coefficient, 3)
                / (27 * Math.pow(denominator, 2))
            var derivative = 4 * Math.pow(coefficient, 2)
                * (coefficient + 3) / (27 * Math.pow(denominator, 3))
            coefficient -= (value - target) / derivative
            coefficient = Math.max(0.0001, coefficient)
        }
        return coefficient
    }

    function recentRowProgressAt(local, rowRightEdge) {
        var normalized = clamp01(local)
        var c1 = recentRowBackC1(rowRightEdge)
        var c3 = c1 + 1
        var remaining = 1 - normalized
        // One Back-style polynomial: it crosses 1 once, reaches one smooth
        // maximum, then returns to exactly 1 with zero terminal velocity.
        return 1 - c3 * Math.pow(remaining, 3)
            + c1 * Math.pow(remaining, 2)
    }

    function recentRowVelocityAt(local, rowRightEdge) {
        var normalized = clamp01(local)
        var c1 = recentRowBackC1(rowRightEdge)
        var c3 = c1 + 1
        var remaining = 1 - normalized
        return 3 * c3 * Math.pow(remaining, 2) - 2 * c1 * remaining
    }

    function recentPresentationVelocityPxPerMs(rowRightEdge) {
        var local = clamp01((startupClock - cardStartAt) / cardDuration)
        var startupX = recentRowStartupX(rowRightEdge)
        return -startupX * recentRowVelocityAt(local, rowRightEdge) / cardDuration
    }

    function recentPresentationVelocityAt(local, rowRightEdge) {
        var startupX = recentRowStartupX(rowRightEdge)
        return -startupX * recentRowVelocityAt(local, rowRightEdge) / cardDuration
    }

    function recentSignedBlurPixelsFromVelocity(velocity) {
        if (Math.abs(velocity) <= motionBlurDeadZone)
            return 0
        return Math.max(-motionBlurMaxPixels,
                        Math.min(motionBlurMaxPixels, velocity * motionBlurGain))
    }

    function recentSignedBlurPixels(rowRightEdge) {
        return recentSignedBlurPixelsFromVelocity(
            recentPresentationVelocityPxPerMs(rowRightEdge))
    }

    // Deliberately callable rather than frame-logged: this gives physical
    // tuning a representative-point diagnostic without log flooding.
    function logRecentMotionBlurDiagnostic(label, local, rowRightEdge) {
        var position = recentRowStartupX(rowRightEdge)
            * (1 - recentRowProgressAt(local, rowRightEdge))
        var velocity = recentPresentationVelocityAt(local, rowRightEdge)
        var blur = recentSignedBlurPixelsFromVelocity(velocity)
        console.log("RECENT_MOTION_BLUR", label, "t", local * cardDuration,
                    "x", position, "velocity", velocity, "blur", blur)
    }

    function recentRowProgress(rowRightEdge) {
        return recentRowProgressAt((startupClock - cardStartAt) / cardDuration,
                                   rowRightEdge)
    }

    function recentRowMaximumProgress(rowRightEdge) {
        var c1 = recentRowBackC1(rowRightEdge)
        return 1 + 4 * Math.pow(c1, 3) / (27 * Math.pow(c1 + 1, 2))
    }

    function recentRowOvershootTime(rowRightEdge) {
        var c1 = recentRowBackC1(rowRightEdge)
        return cardDuration * (1 - 2 * c1 / (3 * (c1 + 1)))
    }

    function recentRowStartupX(rowRightEdge) {
        // The composed row is laid out first. Its actual right edge defines
        // the one startup position; no card geometry participates in motion.
        return -Math.max(rowRightEdge, 0) - recentRowSafetyMargin
    }

    function recentRowPresentationX(rowRightEdge, viewportWidth) {
        var startupX = recentRowStartupX(rowRightEdge)
        return startupX + (0 - startupX) * recentRowProgress(rowRightEdge)
    }

    function hintsProgress() {
        return easeOut((startupClock - hintsStartAt) / hintsDuration, hintsEasePower)
    }

    function hintsOffset() {
        return hintsTravel * (1 - hintsProgress())
    }

    function hintsOpacity() {
        return clamp01((startupClock - hintsStartAt) / hintsDuration)
    }

    function beginStartup() {
        startupAnimation.stop()
        startupClock = 0
        contentState = transitioningInState
        startupAnimation.start()
    }

    // These explicit boundaries are intentionally small now. Future exit and
    // freeze/reconcile choreography can use them without moving authority into
    // Recent or introducing a timer-owned launch workaround.
    function beginContentExit() {
        contentState = transitioningAwayState
    }

    function markContentHidden() {
        startupAnimation.stop()
        contentState = hiddenState
    }

    function markContentPresented() {
        startupAnimation.stop()
        contentState = presentedState
    }

    NumberAnimation {
        id: startupAnimation
        target: coordinator
        property: "startupClock"
        from: 0
        to: coordinator.startupDuration
        duration: coordinator.startupDuration
        easing.type: Easing.Linear
        onStopped: {
            if (coordinator.contentState === coordinator.transitioningInState)
                coordinator.markContentPresented()
        }
    }
}
