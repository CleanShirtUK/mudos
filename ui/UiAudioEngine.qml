import QtQuick

// Shared QML boundary; playback is delegated to the shell's SDL audio device.
// Device initialization and WAV loading remain lazy on the first semantic cue.
Item {
    id: root
    visible: false
    width: 0
    height: 0

    property bool audioEnabled: true
    property int debounceInterval: 55
    property var lastPlayedAt: ({})
    property var bridgeOverride: null

    function audioBridge() {
        if (bridgeOverride)
            return bridgeOverride
        if (typeof controllerBridge !== "undefined")
            return controllerBridge
        return null
    }

    function play(semantic) {
        if (!audioEnabled || !["navigate", "confirm", "back", "error"].includes(semantic))
            return false
        var now = Date.now()
        if (now - (lastPlayedAt[semantic] || 0) < debounceInterval)
            return false
        lastPlayedAt[semantic] = now
        var bridge = audioBridge()
        if (!bridge || typeof bridge.playUiSound !== "function") {
            console.warn("UI_AUDIO_UNAVAILABLE native audio bridge missing", semantic)
            return false
        }
        var submitted = bridge.playUiSound(semantic)
        console.log("UI_AUDIO_QML_SUBMIT", semantic, submitted)
        return submitted
    }
}
