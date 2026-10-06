import QtQuick

// One geometry authority for all full-screen expanded destinations. Bounds
// are in shell/window coordinates; child screens receive innerInset and apply
// that inset only to their internal content, never to the substrate.
QtObject {
    id: root

    property real screenWidth: 1280
    property real screenHeight: 720
    property real uiScale: 1
    property real shellSideInset: 20
    property real shellTop: 20
    property real titleLeftInset: 22
    property real titleTopInset: 8
    property real titleHeight: 37 * uiScale
    property real titleToSurfaceGap: 21 * uiScale
    property real surfaceLead: 16 * uiScale
    property real surfaceTopExtension: 8 * uiScale
    property real hintBandTop: 648
    property real surfaceToHintGap: 8 * uiScale
    property real innerInset: 20 * uiScale

    readonly property rect titleBounds: Qt.rect(
        shellSideInset + titleLeftInset * uiScale,
        shellTop + titleTopInset * uiScale,
        Math.max(0, screenWidth - 2 * shellSideInset
            - titleLeftInset * uiScale), titleHeight)
    readonly property real surfaceX: shellSideInset
    readonly property real surfaceY: shellTop + titleHeight
        + titleToSurfaceGap + surfaceLead - surfaceTopExtension
    readonly property real surfaceWidth: Math.max(0,
        screenWidth - 2 * shellSideInset)
    readonly property real surfaceBottom: hintBandTop - surfaceToHintGap
    readonly property real surfaceHeight: Math.max(0,
        surfaceBottom - surfaceY)
    readonly property rect surfaceBounds: Qt.rect(surfaceX, surfaceY,
        surfaceWidth, surfaceHeight)
    readonly property real contentY: surfaceY + surfaceTopExtension
    readonly property rect contentBounds: Qt.rect(surfaceX, contentY,
        surfaceWidth, Math.max(0, surfaceBottom - contentY))
    readonly property rect innerBounds: Qt.rect(
        surfaceX + innerInset, contentY + innerInset,
        Math.max(0, surfaceWidth - 2 * innerInset),
        Math.max(0, contentBounds.height - 2 * innerInset))
}
