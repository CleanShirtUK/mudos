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
    // The coordinator owns the continuous render clock. Orbit's intro clock is
    // a subordinate animation triggered by beginStartup; it never gates the
    // shell's PRESENTED/HIDDEN boundaries.
    property real orbitBaseTime: 0
    property real orbitSettledOffset: 0
    property real orbitIntroClock: 0
    property bool orbitIntroActive: false
    property real orbitExitStartTime: 0
    property real orbitExitStartBaseTime: 0
    property real orbitExitStartVisibility: 0
    property real orbitExitStartBrightness: 0
    property real orbitExitStartSpeed: 1
    readonly property bool startupRunning: startupAnimation.running
    readonly property bool exitRunning: exitAnimation.running
    readonly property bool contentVisible:
        contentState !== hiddenState
        && (contentState !== transitioningInState
            || startupClock >= contentRevealAt)
    readonly property bool contentPresented: contentState === presentedState
    readonly property bool contentHidden: contentState === hiddenState
    readonly property bool contentTransitioning:
        contentState === transitioningInState
        || contentState === transitioningAwayState

    readonly property real presentationProgress:
        contentState === hiddenState ? 0
        : contentState === presentedState ? 1
        : clamp01(startupClock / startupDuration)
    readonly property real orbitIntroPeakSpeed: 34.0
    readonly property int orbitIntroDuration: 4500
    readonly property int orbitIntroPeakStart: 225
    readonly property int orbitIntroPeakEnd: 360
    readonly property int orbitIntroRevealEnd: 990
    readonly property real orbitIntroDecay: 10.0
    readonly property real orbitNormalSpeed: 1.0
    readonly property real orbitExitTerminalSpeed: 0.15
    readonly property real orbitClockRate: 1.0
    readonly property real orbitVisibility: {
        if (contentState === hiddenState)
            return 0
        if (contentState === transitioningAwayState)
            return orbitExitStartVisibility * presentationProgress
        if (orbitIntroActive)
            return clamp01(orbitIntroClock / orbitIntroRevealEnd)
        return 1
    }
    readonly property real orbitBrightness:
        contentState === hiddenState ? 0
        : contentState === transitioningAwayState
            ? orbitExitStartBrightness * presentationProgress
            : orbitIntroActive ? orbitVisibility : 1
    readonly property real orbitSpeed:
        contentState === hiddenState ? 0
        : contentState === transitioningAwayState
            ? orbitExitSpeedAt(1 - presentationProgress, orbitExitStartSpeed)
            : orbitIntroActive
                ? orbitIntroSpeedAt(orbitIntroClock)
                : orbitNormalSpeed
    readonly property real orbitShaderTime: {
        if (contentState === hiddenState)
            return 0
        if (orbitIntroActive)
            return orbitBaseTime + orbitIntroCorrection(orbitIntroClock)
        if (contentState === transitioningAwayState)
            return orbitExitStartTime + (orbitBaseTime - orbitExitStartBaseTime)
                + orbitExitCorrection(1 - presentationProgress,
                                       orbitExitStartSpeed)
        return orbitBaseTime + orbitSettledOffset
    }

    function clamp01(value) {
        return Math.max(0, Math.min(1, value))
    }

    function smoothstep(value) {
        var normalized = clamp01(value)
        return normalized * normalized * (3 - 2 * normalized)
    }

    function orbitIntroSpeedAt(elapsedMs) {
        var value = Math.max(0, Math.min(orbitIntroDuration, elapsedMs))
        if (value < orbitIntroPeakStart) {
            var rising = value / orbitIntroPeakStart
            return 0.01 + (orbitIntroPeakSpeed - 0.01) * smoothstep(rising)
        }
        if (value < orbitIntroPeakEnd)
            return orbitIntroPeakSpeed
        var decayProgress = (value - orbitIntroPeakEnd)
            / (orbitIntroDuration - orbitIntroPeakEnd)
        var endDecay = Math.exp(-orbitIntroDecay)
        var decay = Math.exp(-orbitIntroDecay * decayProgress)
        return orbitNormalSpeed + (orbitIntroPeakSpeed - orbitNormalSpeed)
            * (decay - endDecay) / (1 - endDecay)
    }

    // Integral of the upstream intro speed curve over elapsed seconds.
    function orbitIntroIntegratedSpeed(elapsedMs) {
        var value = Math.max(0, Math.min(orbitIntroDuration, elapsedMs))
        var duration = orbitIntroDuration
        var firstLength = orbitIntroPeakStart
        var secondLength = orbitIntroPeakEnd - orbitIntroPeakStart
        var finalLength = duration - orbitIntroPeakEnd
        var result = 0
        if (value <= firstLength) {
            var rising = value / firstLength
            result = firstLength * (0.01 * rising
                + (orbitIntroPeakSpeed - 0.01)
                    * (rising * rising * rising
                       - 0.5 * rising * rising * rising * rising))
            return result / 1000
        }
        result = firstLength * (0.01
            + (orbitIntroPeakSpeed - 0.01) * 0.5)
        if (value <= orbitIntroPeakEnd)
            return (result + (value - firstLength) * orbitIntroPeakSpeed) / 1000
        var decayProgress = (value - orbitIntroPeakEnd) / finalLength
        var endDecay = Math.exp(-orbitIntroDecay)
        var decayIntegral = (1 - Math.exp(-orbitIntroDecay * decayProgress))
            / orbitIntroDecay - endDecay * decayProgress
        result += secondLength * orbitIntroPeakSpeed
        result += finalLength * (decayProgress
            + (orbitIntroPeakSpeed - orbitNormalSpeed)
                * decayIntegral / (1 - endDecay))
        return result / 1000
    }

    function orbitIntroCorrection(elapsedMs) {
        return orbitIntroIntegratedSpeed(elapsedMs) - elapsedMs / 1000
    }

    function orbitExitSpeedAt(progress, initialSpeed) {
        return initialSpeed
            + (orbitExitTerminalSpeed - initialSpeed) * smoothstep(progress)
    }

    function orbitExitIntegratedSpeed(progress, initialSpeed) {
        var value = clamp01(progress)
        return initialSpeed * value
            + (orbitExitTerminalSpeed - initialSpeed)
                * (value * value * value - 0.5 * value * value * value * value)
    }

    function orbitExitCorrection(progress, initialSpeed) {
        return (orbitExitIntegratedSpeed(progress, initialSpeed) - clamp01(progress))
            * startupDuration / 1000
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

    // Derivative of titleTravelProgress with respect to its local 0..1 time.
    // It intentionally follows the accepted position curve exactly; no timer
    // sampling or alternate easing is introduced for blur.
    function titleTravelVelocityAt(index) {
        var local = (startupClock - titleStartAt - index * titleStagger) / titleDuration
        if (local <= 0 || local >= 1)
            return 0
        if (Math.abs(local - titleApproachFraction) < 0.000001)
            return 0
        if (local < titleApproachFraction) {
            var approachLocal = local / titleApproachFraction
            return (1 + titleOvershoot) * 4
                * Math.pow(1 - approachLocal, 3) / titleApproachFraction
        }
        var settleLocal = (local - titleApproachFraction)
            / (1 - titleApproachFraction)
        return -titleOvershoot * 2.3
            * Math.pow(1 - settleLocal, 1.3) / (1 - titleApproachFraction)
    }

    function titleStartupTranslation(restingLeft, titleWidth) {
        return -(restingLeft + titleWidth + titleStartupSafetyMargin)
    }

    function titleOffset(index, restingLeft, titleWidth) {
        var startupTranslation = titleStartupTranslation(restingLeft, titleWidth)
        return startupTranslation * (1 - titleTravelProgress(index))
    }

    function titlePresentationVelocityPxPerMs(index, restingLeft, titleWidth) {
        if (contentState === hiddenState)
            return 0
        var startupTranslation = titleStartupTranslation(restingLeft, titleWidth)
        var velocity = -startupTranslation * titleTravelVelocityAt(index) / titleDuration
        return contentState === transitioningAwayState ? -velocity : velocity
    }

    function signedMotionBlurPixelsFromVelocity(velocity) {
        if (Math.abs(velocity) <= motionBlurDeadZone)
            return 0
        return Math.max(-motionBlurMaxPixels,
                        Math.min(motionBlurMaxPixels, velocity * motionBlurGain))
    }

    function titleSignedBlurPixels(index, restingLeft, titleWidth) {
        if (contentState === hiddenState)
            return 0
        return signedMotionBlurPixelsFromVelocity(
            titlePresentationVelocityPxPerMs(index, restingLeft, titleWidth))
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
        if (contentState === hiddenState)
            return 0
        var local = clamp01((startupClock - cardStartAt) / cardDuration)
        var startupX = recentRowStartupX(rowRightEdge)
        var velocity = -startupX * recentRowVelocityAt(local, rowRightEdge) / cardDuration
        return contentState === transitioningAwayState ? -velocity : velocity
    }

    function recentPresentationVelocityAt(local, rowRightEdge) {
        if (contentState === hiddenState)
            return 0
        var startupX = recentRowStartupX(rowRightEdge)
        var velocity = -startupX * recentRowVelocityAt(local, rowRightEdge) / cardDuration
        return contentState === transitioningAwayState ? -velocity : velocity
    }

    function recentSignedBlurPixelsFromVelocity(velocity) {
        return signedMotionBlurPixelsFromVelocity(velocity)
    }

    function recentSignedBlurPixels(rowRightEdge) {
        if (contentState === hiddenState)
            return 0
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
        exitAnimation.stop()
        orbitBaseTimeAnimation.stop()
        orbitBaseTime = 0
        orbitSettledOffset = 0
        orbitIntroClock = 0
        orbitIntroActive = true
        startupClock = 0
        console.log("COORDINATOR", contentState, "->", transitioningInState)
        contentState = transitioningInState
        orbitBaseTimeAnimation.start()
        orbitIntroAnimation.start()
        startupAnimation.start()
    }

    // These explicit boundaries are intentionally small now. Future exit and
    // freeze/reconcile choreography can use them without moving authority into
    // Recent or introducing a timer-owned launch workaround.
    function beginContentExit() {
        if (contentState !== presentedState || exitAnimation.running)
            return false
        orbitExitStartTime = orbitShaderTime
        orbitExitStartBaseTime = orbitBaseTime
        orbitExitStartVisibility = orbitVisibility
        orbitExitStartBrightness = orbitBrightness
        orbitExitStartSpeed = orbitSpeed
        orbitIntroActive = false
        orbitIntroAnimation.stop()
        contentState = transitioningAwayState
        startupClock = startupDuration
        exitAnimation.start()
        return true
    }

    function markContentHidden() {
        startupAnimation.stop()
        exitAnimation.stop()
        orbitBaseTimeAnimation.stop()
        orbitIntroAnimation.stop()
        orbitIntroActive = false
        startupClock = 0
        contentState = hiddenState
        console.log("COORDINATOR", transitioningAwayState, "->", hiddenState)
        contentHiddenReached()
    }

    function markContentPresented() {
        startupAnimation.stop()
        exitAnimation.stop()
        contentState = presentedState
        console.log("COORDINATOR", transitioningInState, "->", presentedState)
        contentPresentedReached()
    }

    signal contentHiddenReached()
    signal contentPresentedReached()

    function finishOrbitIntro() {
        if (!orbitIntroActive)
            return
        orbitIntroClock = orbitIntroDuration
        orbitSettledOffset = orbitIntroCorrection(orbitIntroDuration)
        orbitIntroActive = false
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

    NumberAnimation {
        id: orbitBaseTimeAnimation
        target: coordinator
        property: "orbitBaseTime"
        from: 0
        to: 100000
        duration: 100000000
        loops: Animation.Infinite
        running: true
    }

    NumberAnimation {
        id: orbitIntroAnimation
        target: coordinator
        property: "orbitIntroClock"
        from: 0
        to: coordinator.orbitIntroDuration
        duration: coordinator.orbitIntroDuration
        easing.type: Easing.Linear
        onStopped: {
            if (coordinator.orbitIntroActive
                    && coordinator.contentState !== coordinator.transitioningAwayState)
                coordinator.finishOrbitIntro()
        }
    }

    NumberAnimation {
        id: exitAnimation
        target: coordinator
        property: "startupClock"
        from: coordinator.startupDuration
        to: 0
        duration: coordinator.startupDuration
        easing.type: Easing.Linear
        onStopped: {
            if (coordinator.contentState === coordinator.transitioningAwayState)
                coordinator.markContentHidden()
        }
    }
}
