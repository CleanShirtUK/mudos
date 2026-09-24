.pragma library

function select(text, fits) {
    var full = String(text || "")
    if (!full || fits(full))
        return {text: full, elide: false, shortened: false}

    var boundaries = []
    var start = 0
    while (true) {
        var boundary = full.indexOf(". ", start)
        if (boundary < 0)
            break
        boundaries.push(boundary + 1)
        start = boundary + 2
    }
    for (var i = boundaries.length - 1; i >= 0; --i) {
        var candidate = full.slice(0, boundaries[i]).trim()
        if (candidate && fits(candidate))
            return {text: candidate, elide: false, shortened: true}
    }
    return {text: full, elide: true, shortened: false}
}
