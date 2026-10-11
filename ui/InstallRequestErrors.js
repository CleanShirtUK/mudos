.pragma library

function responseReason(responseText, fallback) {
    var body = null
    try {
        body = JSON.parse(String(responseText || ""))
    } catch (error) {
        body = null
    }
    var reason = body && body.error
    if (reason && typeof reason === "object")
        reason = reason.message || reason.detail || reason.code
    if (reason === undefined || reason === null || String(reason).trim() === "")
        return String(fallback || "The request was rejected")
    return String(reason).trim()
}

function installationFailure(title, reason) {
    var name = String(title || "The game").trim() || "The game"
    var detail = String(reason || "The installation request was rejected").trim()
    return name + " was not installed: " + detail
}
