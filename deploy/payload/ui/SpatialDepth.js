.pragma library

var maxDistance = 3
var cardScales = [1.0, 0.95, 0.86, 0.78]
var cardBlurPixels = [0.0, 5.0, 11.0, 18.0]
var titleScales = [1.0, 0.97, 0.92, 0.86]
var titleBlurPixels = [0.0, 4.0, 11.0, 20.0]
var gapFactors = [1.0, 1.0, 0.76, 0.52]

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

function visualOffsetForRelativeIndex(relativeIndex, baseGap) {
    var depth = Math.min(maxDistance, Math.abs(Math.round(relativeIndex)))
    var sign = relativeIndex < 0 ? -1 : 1
    var compression = 0
    for (var step = 2; step <= depth; step++)
        compression += baseGap - visualGapForDepth(step, baseGap)
    return -sign * compression
}
