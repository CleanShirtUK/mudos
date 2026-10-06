import QtQuick

// SettingsSpace unit tests validate navigation and composition without
// requiring the production native glass plugin.
Item {
    property var backdrop
    property size canonicalSize
    property rect canonicalRect
    property real cornerRadius: 0
    property real refractionPixels: 0
    property real dispersionIor: 0
    property real diffusionPixels: 0
    property real transmission: 0
    property real bevelWidthPx: 0
    property real bulgeStrength: 0
    property real sceneLightStrength: 0
    property real sceneLightPixels: 0
    property real edgeLightStrength: 0
    property vector2d edgeLightDirection
    property bool transparentOutsideMask: false
}
