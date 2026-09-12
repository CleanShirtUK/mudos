import QtQuick
import QtMultimedia

QtObject {
    id: root

    // Keep these names stable so replacing a sound never requires a QML edit.
    readonly property url navigateSource: "sounds/ui-navigate.wav"
    readonly property url confirmSource: "sounds/ui-confirm.wav"
    readonly property url backSource: "sounds/ui-back.wav"
    readonly property url errorSource: "sounds/ui-error.wav"

    property bool enabled: true
    property real volume: 0.35
    property int debounceInterval: 55
    property int maxVoices: 3
    property var lastPlayedAt: ({})

    readonly property SoundEffect navigateVoice: SoundEffect {
        source: root.navigateSource
        volume: root.volume
    }
    readonly property SoundEffect confirmVoice: SoundEffect {
        source: root.confirmSource
        volume: root.volume
    }
    readonly property SoundEffect backVoice: SoundEffect {
        source: root.backSource
        volume: root.volume
    }
    readonly property SoundEffect errorVoice: SoundEffect {
        source: root.errorSource
        volume: root.volume
    }

    function voiceFor(semantic) {
        if (semantic === "navigate")
            return navigateVoice
        if (semantic === "confirm")
            return confirmVoice
        if (semantic === "back")
            return backVoice
        if (semantic === "error")
            return errorVoice
        return null
    }

    function activeVoiceCount() {
        var count = 0
        var voices = [navigateVoice, confirmVoice, backVoice, errorVoice]
        for (var index = 0; index < voices.length; index++) {
            var voice = voices[index]
            if (voice.playing)
                count++
        }
        return count
    }

    // Returns false for unknown, unavailable, muted, debounced, or capped sounds.
    function play(semantic) {
        if (!enabled)
            return false
        var voice = voiceFor(semantic)
        if (!voice || voice.status !== SoundEffect.Ready)
            return false

        var now = Date.now()
        var previous = lastPlayedAt[semantic] || 0
        if (now - previous < debounceInterval)
            return false
        if (!voice.playing && activeVoiceCount() >= maxVoices)
            return false

        lastPlayedAt[semantic] = now
        voice.stop()
        voice.play()
        return true
    }

    function stopAll() {
        navigateVoice.stop()
        confirmVoice.stop()
        backVoice.stop()
        errorVoice.stop()
    }
}
