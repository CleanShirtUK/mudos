.pragma library

// Fixed landing-card and in-view navigation order. Keep the semantic key on
// each item so activation never has to infer identity from a mutable index.
var all = [
    {label: "Platform", mode: "platform"},
    {label: "Provider", mode: "provider"},
    {label: "Game Mode", mode: "game_mode"},
    {label: "Genre", mode: "genre"}
]

function has(mode) {
    for (var i = 0; i < all.length; ++i)
        if (all[i].mode === mode) return true
    return false
}

function adjacent(mode, delta) {
    var index = -1
    for (var i = 0; i < all.length; ++i)
        if (all[i].mode === mode) index = i
    if (index < 0 || !all.length) return "platform"
    var next = (index + delta + all.length) % all.length
    return all[next].mode
}
