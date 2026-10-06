.pragma library

// Return the union of the stable layout row and the current visual AABBs of
// delegates. Bounds and results are local to RecentHome's row/capture source.
function union(layoutLeft, layoutRight, liveBounds) {
    var left = Number(layoutLeft)
    var right = Number(layoutRight)
    var bounds = liveBounds || []
    for (var index = 0; index < bounds.length; index++) {
        var item = bounds[index]
        if (!item)
            continue
        var itemLeft = Number(item.x)
        var itemRight = itemLeft + Number(item.width)
        if (!isFinite(itemLeft) || !isFinite(itemRight))
            continue
        left = Math.min(left, itemLeft)
        right = Math.max(right, itemRight)
    }
    return {left: left, right: right}
}
