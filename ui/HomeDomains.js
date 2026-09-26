.pragma library

function recentVisible(recentCount, transitioning, fromIndex, targetIndex) {
    return recentCount > 0 || (transitioning && (fromIndex === 3 || targetIndex === 3))
}

function categories(recentVisible) {
    return recentVisible ? ["System", "Store", "Library", "Recent"]
                         : ["System", "Store", "Library"]
}

function clampSelection(index, recentCount) {
    return Math.max(0, Math.min(index, recentCount > 0 ? 3 : 2))
}

function titleRailY(domainY, selectedIndex, pitch) {
    return domainY - selectedIndex * pitch
}
