.pragma library

function recentVisible(recentCount, transitioning, fromIndex, targetIndex) {
    return recentCount > 0 || (transitioning && (fromIndex === 3 || targetIndex === 3))
}

function categories(recentVisible) {
    return recentVisible ? ["system", "store", "library", "recent"]
                         : ["system", "store", "library"]
}

function clampSelection(index, recentCount) {
    return Math.max(0, Math.min(index, recentCount > 0 ? 3 : 2))
}

function settleSelection(currentIndex, desiredIndex) {
    var selected = currentIndex
    while (selected !== desiredIndex)
        selected += desiredIndex > selected ? 1 : -1
    return {selectedIndex: selected, progress: 1, transitioning: false}
}

function titleRailY(domainY, selectedIndex, pitch) {
    return domainY - selectedIndex * pitch
}
