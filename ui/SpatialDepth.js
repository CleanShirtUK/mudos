.pragma library

var maxDistance = 3
var cardScales = [1.0, 0.95, 0.86, 0.78]
var cardBlurPixels = [0.0, 4.0, 8.0, 12.0]
var titleScales = [1.0, 0.97, 0.92, 0.86]
var titleBlurPixels = [0.0, 0.0, 0.0, 0.0]
var gapFactors = [1.0, 0.62, 0.32, 0.20]

function distanceFromSelectedIndex(itemIndex, selectedIndex) {
    return Math.min(maxDistance, Math.abs(itemIndex - selectedIndex))
}

function cardScale(distance) {
    return cardScales[Math.min(maxDistance, Math.max(0, Math.round(distance)))]
}

function cardBlur(distance) {
    return cardBlurPixels[Math.min(maxDistance, Math.max(0, Math.round(distance)))]
}

function titleScale(distance) {
    return titleScales[Math.min(maxDistance, Math.max(0, Math.round(distance)))]
}

function titleBlur(distance) {
    return titleBlurPixels[Math.min(maxDistance, Math.max(0, Math.round(distance)))]
}

function visualGapForDepth(distance, baseGap) {
    var depth = Math.min(maxDistance, Math.max(0, Math.round(distance)))
    return baseGap * gapFactors[depth]
}

function visibleWidthForDepth(depth, focalWidth, compactWidth) {
    return depth === 0 ? focalWidth : compactWidth * cardScale(depth)
}

function projectedXForRelativeIndex(relativeIndex, focalWidth, compactWidth, baseGap) {
    var depth = Math.min(maxDistance, Math.abs(Math.round(relativeIndex)))
    if (depth === 0)
        return 0
    var sign = relativeIndex < 0 ? -1 : 1
    var currentWidth = visibleWidthForDepth(1, focalWidth, compactWidth)
    var position = sign > 0
        ? focalWidth + visualGapForDepth(1, baseGap)
        : -(currentWidth + visualGapForDepth(1, baseGap))
    for (var step = 2; step <= depth; step++) {
        var nextWidth = visibleWidthForDepth(step, focalWidth, compactWidth)
        var stepDistance = currentWidth * 0.5
            + visualGapForDepth(step, baseGap) + nextWidth * 0.5
        position += sign * stepDistance
        currentWidth = nextWidth
    }
    return position
}
