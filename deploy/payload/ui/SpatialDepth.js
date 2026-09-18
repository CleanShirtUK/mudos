.pragma library

var maxDistance = 3
var cardScales = [1.0, 0.95, 0.86, 0.78]
var cardBlurPixels = [0.0, 4.0, 9.0, 16.0]
var titleScales = [1.0, 0.97, 0.92, 0.86]
var titleBlurPixels = [0.0, 4.0, 11.0, 20.0]

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
