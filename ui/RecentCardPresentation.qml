import QtQuick

// Zero-offset logical wrapper for one live Recent GameCard. The wrapper keeps
// the GameCard at its authoritative scene position while the blur observes a
// bounded, stable-size capture around it.
Item {
    id: root

    required property int index
    required property string game_id
    required property string provider
    required property string install_state
    required property var provider_id
    required property var title
    required property var platform
    required property var launchable
    required property var install_dir
    required property var artwork_url
    required property var artwork_suppressed
    required property var last_played
    required property var total_playtime
    required property var runtime
    required property var genres
    // The native RecentModel exposes this role even when its value is empty;
    // requiring the role makes QML bind the native value instead of retaining
    // a local default binding.
    required property var game_modes
    required property var game_mode
    required property var protondb_rating
    required property var display_title_override
    required property var canonical_title
    required property var platform_label

    property var home
    property var canonicalTexture
    property var canonicalCoordinateRoot
    property size canonicalSize: Qt.size(1280, 720)
    property real focalCardWidth: 760
    property real focalCardHeight: 500
    property real compactCardWidth: 160
    property real focalScale: 1
    property real uiScale: 1
    property var typography
    property var luluPalette
    property int playActivationSerial: 0
    property bool focused: false
    property real startX: 0
    property real startWidth: 0
    property real startProgress: 0
    property real startChrome: 0
    property real startCompactTitle: 0
    property real railProgress: 1
    property int toRelativeIndex: 0
    property bool selectionBlurActive: false
    property string presentationState: "COMPACT"
    signal activationRequested(string gameId)
    signal playFeedbackCompleted(string gameId)

    readonly property real targetProgress: focused ? 1 : 0
    readonly property real presentationProgress: startProgress
        + (targetProgress - startProgress) * railProgress
    readonly property real focalChromeOpacity: startChrome
        + ((focused ? 1 : 0) - startChrome) * railProgress
    readonly property real compactTitleOpacity: startCompactTitle
        + ((focused ? 0 : 1) - startCompactTitle) * railProgress
    readonly property real targetX: home ? home.railX(toRelativeIndex) : 0
    // This is deliberately composed from the properties that move the live
    // Recent presentation. mapToItem() itself does not notify on ancestor
    // transforms, so GameCard consumes this dependency explicitly.
    readonly property var canonicalMappingDependency: ({
        rowX: home ? home.presentationX : 0,
        delegateX: x,
        delegateY: y,
        delegateWidth: width,
        delegateHeight: height,
        railProgress: railProgress,
        transitionProgress: home ? home.transitionProgress : 1,
        presentationProgress: presentationProgress,
        targetX: targetX,
        targetWidth: home ? home.railWidth(toRelativeIndex) : width,
        categoryPresentationOffset: home
            ? home.categoryPresentationOffset : 0
    })
    readonly property real capturePadding: home && home.presentationCoordinator
        ? home.presentationCoordinator.motionBlurMaxPixels : 64
    readonly property real captureWidth: focalCardWidth + 2 * capturePadding
    readonly property real captureHeight: focalCardHeight + 2 * capturePadding
    readonly property var gameRecord: ({
        game_id: game_id,
        provider: provider,
        provider_id: provider_id,
        title: title,
        platform: platform,
        install_state: install_state,
        launchable: launchable,
        install_dir: install_dir,
        artwork_url: artwork_url,
        artwork_suppressed: artwork_suppressed,
        last_played: last_played,
        total_playtime: total_playtime,
        runtime: runtime,
        genres: genres,
        game_modes: game_modes,
        game_mode: game_mode,
        protondb_rating: protondb_rating,
        display_title_override: display_title_override,
        canonical_title: canonical_title,
        platform_label: platform_label
    })

    GameCard {
        id: gameCard
        anchors.fill: parent
        game: root.gameRecord
        focused: root.focused
        presentationProgress: root.presentationProgress
        compactEndpointWidth: root.compactCardWidth
        focalChromeOpacity: root.focalChromeOpacity
        compactTitleOpacity: root.compactTitleOpacity
        focalLayoutCardWidth: root.focalCardWidth
        presentationState: root.presentationState
        focusBrightness: root.focused ? 1 : 0.84
        onPlayFeedbackCompleted: root.playFeedbackCompleted(root.game_id)
        liveSceneCoordinates: true
        opticsStage: root.presentationProgress > 0 ? 7 : -1
        compact: root.presentationState === "COMPACT"
        showAction: false
        actionLabel: root.install_state === "available"
            ? "Installable" : (root.provider === "steam-store"
                ? "Open" : "Play")
        homeCard: true
        playActivationSerial: root.playActivationSerial
        canonicalTexture: root.canonicalTexture
         canonicalCoordinateRoot: root.canonicalCoordinateRoot
         canonicalMappingDependency: root.canonicalMappingDependency
        canonicalSize: root.canonicalSize
        focalScale: root.focalScale
        uiScale: root.uiScale
        typography: root.typography
         luluPalette: root.luluPalette
     }



    function dumpTransitionMapping(mark) {
        var r = gameCard.nativeRecentCanonicalRect
        var directTopLeft = root.canonicalCoordinateRoot
            ? gameCard.mapToItem(root.canonicalCoordinateRoot, 0, 0)
            : Qt.point(0, 0)
        console.log("MUDOS_RECENT_TRANSITION_SAMPLE",
                    "mark", mark,
                    "gameId", root.game_id,
                    "modelIndex", root.index,
                    "relativeIndex", root.toRelativeIndex,
                    "focused", root.focused,
                    "transitionProgress", root.railProgress,
                    "delegateX", root.x,
                    "gameCardX", gameCard.x,
                    "directMapX", directTopLeft.x,
                    "sceneX", r.x,
                    "canonicalRect", r.x, r.y, r.width, r.height,
                    "nativeCanonicalRect", r.x, r.y, r.width, r.height,
                    "uvX", r.x / root.canonicalSize.width,
                    "nativeItem", gameCard.nativeRecentGlassIdentity())
    }

    DirectionalMotionBlur {
        id: cardMotionBlur
        x: -root.capturePadding
        y: -root.capturePadding
        width: root.captureWidth
        height: root.captureHeight
        active: root.selectionBlurActive && root.visible
        sourceItem: gameCard
        sourceRect: Qt.rect(-root.capturePadding, -root.capturePadding,
                            root.captureWidth, root.captureHeight)
        blurPixels: root.home
            ? root.home.selectionSignedBlurPixels(root.startX, root.targetX) : 0
    }

    MouseArea {
        anchors.fill: parent
        onClicked: root.activationRequested(root.game_id)
    }
}
