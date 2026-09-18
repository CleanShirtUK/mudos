.pragma library

var maxDistance = 3
var cardScales = [1.0, 0.98, 0.94, 0.90]
var cardBlurPixels = [0.0, 1.5, 3.5, 6.0]
var titleScales = [1.0, 0.985, 0.96, 0.935]
var titleBlurPixels = [0.0, 2.0, 5.0, 8.0]

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
