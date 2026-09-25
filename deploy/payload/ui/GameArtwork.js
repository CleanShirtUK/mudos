.pragma library

function displaySource(value) {
    var source = String(value || "")
    if (source.indexOf("http://") === 0 || source.indexOf("https://") === 0
            || source.indexOf("file:") === 0)
        return "image://mudos-artwork/" + encodeURIComponent(source)
    if (source.indexOf("qrc:") === 0)
        return source
    return ""
}

function portraitIcon(game) {
    if (!game || game.artwork_suppressed)
        return ""
    return localDisplaySource(game.icon_square_url || game.icon_url
                              || (game.artwork_type === "icon" ? game.artwork_url : "")
                              || game.preview_still_url)
}

function previewStill(game) {
    if (!game || game.artwork_suppressed)
        return ""
    return localDisplaySource(game.preview_still_url)
}

function localDisplaySource(value) {
    var source = String(value || "")
    if (source.indexOf("file:") === 0 || source.indexOf("qrc:") === 0)
        return displaySource(source)
    return ""
}
