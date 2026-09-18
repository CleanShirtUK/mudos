.pragma library

var maxDistance = 3
var cardScales = [1.0, 0.95, 0.86, 0.78]
var cardBlurPixels = [0.0, 4.0, 8.0, 12.0]
var titleScales = [1.0, 0.97, 0.92, 0.86]
var titleBlurPixels = [0.0, 0.0, 0.0, 0.0]
var gapFactors = [1.0, 0.70, 0.43, 0.29]

function distanceFromSelectedIndex(itemIndex, selectedIndex) {
    return Math.min(maxDistance, Math.abs(itemIndex - selectedIndex))
}

function cardScale(distance) {
    return cardScales[Math.min(maxDistance, Math.max(0, Math.round(distance)))]
}

function interpolateCurve(curve, distance) {
    var value = Math.max(0, Math.min(maxDistance, distance))
    var lower = Math.floor(value)
    var upper = Math.min(maxDistance, lower + 1)
    return curve[lower] + (curve[upper] - curve[lower]) * (value - lower)
}

function cardScaleAt(distance) {
    return interpolateCurve(cardScales, distance)
}

function cardBlur(distance) {
    return cardBlurPixels[Math.min(maxDistance, Math.max(0, Math.round(distance)))]
}

function cardBlurAt(distance) {
    return interpolateCurve(cardBlurPixels, distance)
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

function visualGapAtDepth(distance, baseGap) {
    return baseGap * interpolateCurve(gapFactors, distance)
}

function visibleWidthForDepth(depth, focalWidth, compactWidth) {
    return depth === 0 ? focalWidth : compactWidth * cardScale(depth)
}

function visibleWidthAtDepth(depth, focalWidth, compactWidth) {
    if (depth <= 0)
        return focalWidth
    return compactWidth * cardScaleAt(depth)
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

function projectedXForIndex(index, selectedPosition, focalWidth, compactWidth,
                             baseGap) {
    var relativeIndex = index - selectedPosition
    var depth = Math.abs(relativeIndex)
    if (depth < 0.0001)
        return 0

    var currentDepth = 0
    var currentWidth = focalWidth
    var centreDistance = 0
    while (currentDepth < depth - 0.0001) {
        var nextDepth = Math.min(depth, currentDepth + 1)
        var nextWidth = visibleWidthAtDepth(nextDepth, focalWidth, compactWidth)
        centreDistance += currentWidth * 0.5
            + visualGapAtDepth(nextDepth, baseGap) + nextWidth * 0.5
        currentDepth = nextDepth
        currentWidth = nextWidth
    }

    var focalCentre = focalWidth * 0.5
    return relativeIndex > 0
        ? focalCentre + centreDistance - currentWidth * 0.5
        : focalCentre - centreDistance - currentWidth * 0.5
}
