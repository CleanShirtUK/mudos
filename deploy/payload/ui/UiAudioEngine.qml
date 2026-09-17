import QtQuick
import QtMultimedia

Item {
    id: root
    visible: false
    width: 0
    height: 0

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
    property string pendingSemantic: ""

    property Component navigateVoiceComponent: Component {
        id: navigateVoiceComponent
        SoundEffect { source: root.navigateSource; volume: root.volume }
    }
    property Component confirmVoiceComponent: Component {
        id: confirmVoiceComponent
        SoundEffect { source: root.confirmSource; volume: root.volume }
    }
    property Component backVoiceComponent: Component {
        id: backVoiceComponent
        SoundEffect { source: root.backSource; volume: root.volume }
    }
    property Component errorVoiceComponent: Component {
        id: errorVoiceComponent
        SoundEffect { source: root.errorSource; volume: root.volume }
    }

    Loader {
        id: navigateVoiceLoader
        sourceComponent: root.navigateVoiceComponent
        active: false
        onLoaded: root.tryPlayPending()
    }
    Loader {
        id: confirmVoiceLoader
        sourceComponent: root.confirmVoiceComponent
        active: false
        onLoaded: root.tryPlayPending()
    }
    Loader {
        id: backVoiceLoader
        sourceComponent: root.backVoiceComponent
        active: false
        onLoaded: root.tryPlayPending()
    }
    Loader {
        id: errorVoiceLoader
        sourceComponent: root.errorVoiceComponent
        active: false
        onLoaded: root.tryPlayPending()
    }

    Connections {
        target: navigateVoiceLoader.item
        function onStatusChanged() {
            root.tryPlayPending()
        }
    }
    Connections {
        target: confirmVoiceLoader.item
        function onStatusChanged() { root.tryPlayPending() }
    }
    Connections {
        target: backVoiceLoader.item
        function onStatusChanged() { root.tryPlayPending() }
    }
    Connections {
        target: errorVoiceLoader.item
        function onStatusChanged() { root.tryPlayPending() }
    }

    function loaderFor(semantic) {
        if (semantic === "navigate")
            return navigateVoiceLoader
        if (semantic === "confirm")
            return confirmVoiceLoader
        if (semantic === "back")
            return backVoiceLoader
        if (semantic === "error")
            return errorVoiceLoader
        return null
    }

    function voiceFor(semantic) {
        var loader = loaderFor(semantic)
        return loader ? loader.item : null
    }

    function activeVoiceCount() {
        var count = 0
        var voices = [navigateVoiceLoader.item, confirmVoiceLoader.item,
                      backVoiceLoader.item, errorVoiceLoader.item]
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
        var loader = loaderFor(semantic)
        if (!loader)
            return false
        var voice = loader.item
        if (!voice) {
            pendingSemantic = semantic
            loader.active = true
            return false
        }
        if (voice.status !== SoundEffect.Ready) {
            pendingSemantic = semantic
            return false
        }

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

    function tryPlayPending() {
        if (!pendingSemantic)
            return
        var semantic = pendingSemantic
        pendingSemantic = ""
        play(semantic)
    }

    function stopAll() {
        var voices = [navigateVoiceLoader.item, confirmVoiceLoader.item,
                      backVoiceLoader.item, errorVoiceLoader.item]
        for (var index = 0; index < voices.length; index++)
            if (voices[index])
                voices[index].stop()
    }
}
