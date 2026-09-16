import QtQuick
import QtTest

TestCase {
    name: "LibrarySpatialMapping"

    Item {
        id: orbitRenderSource
        width: 1920
        height: 1080

        Item {
            id: shell
            x: 40
            y: 28
            scale: 1

            Item {
                id: surface
                property real progress: 0
                property real homeX: 84
                property real homeY: 410
                property real homeWidth: 220
                property real homeHeight: 330
                property real fullscreenX: 76
                property real fullscreenY: 32
                property real fullscreenWidth: 1768
                property real fullscreenHeight: 1032
                property real verticalOffset: 0
                readonly property real surfaceX: homeX
                    + (fullscreenX - homeX) * progress
                readonly property real surfaceY: homeY
                    + (fullscreenY - homeY) * progress
                readonly property real surfaceWidth: homeWidth
                    + (fullscreenWidth - homeWidth) * progress
                readonly property real surfaceHeight: homeHeight
                    + (fullscreenHeight - homeHeight) * progress
                x: surfaceX
                y: surfaceY + verticalOffset
                width: surfaceWidth
                height: surfaceHeight

                readonly property rect canonicalRect: {
                    var presentationDependency = progress + homeX + homeY
                        + homeWidth + homeHeight + fullscreenX + fullscreenY
                        + fullscreenWidth + fullscreenHeight + verticalOffset
                        + x + y + width + height
                    var ancestorDependency = parent.x + parent.y + parent.scale
                    var dependency = presentationDependency + ancestorDependency
                    var topLeft = mapToItem(orbitRenderSource, 0, 0)
                    var bottomRight = mapToItem(orbitRenderSource,
                                               width, height)
                    return Qt.rect(topLeft.x + dependency - dependency,
                                   topLeft.y + dependency - dependency,
                                   bottomRight.x - topLeft.x,
                                   bottomRight.y - topLeft.y)
                }
            }
        }
    }

    function verifyCanonicalRect() {
        var topLeft = surface.mapToItem(orbitRenderSource, 0, 0)
        var bottomRight = surface.mapToItem(orbitRenderSource,
                                            surface.width, surface.height)
        compare(surface.canonicalRect.x, topLeft.x)
        compare(surface.canonicalRect.y, topLeft.y)
        compare(surface.canonicalRect.width, bottomRight.x - topLeft.x)
        compare(surface.canonicalRect.height, bottomRight.y - topLeft.y)
    }

    function test_settledAndContinuousResizeTranslation() {
        verifyCanonicalRect()
        surface.progress = 0.5
        surface.verticalOffset = -96
        wait(10)
        verifyCanonicalRect()
        surface.progress = 1
        wait(10)
        verifyCanonicalRect()
    }

    function test_ancestorMovementAndRetarget() {
        surface.progress = 0.25
        surface.verticalOffset = 18
        shell.x = 112
        shell.y = 64
        shell.scale = 1.04
        wait(10)
        verifyCanonicalRect()

        surface.progress = 0.82
        surface.verticalOffset = -42
        shell.x = 24
        shell.y = 18
        shell.scale = 0.98
        wait(10)
        verifyCanonicalRect()
    }

    function test_adjacentSpatialRegionsRemainUnique() {
        verify(surface.canonicalRect.width > 0)
        verify(surface.canonicalRect.height > 0)
        var firstX = surface.canonicalRect.x
        surface.progress = 0.6
        wait(10)
        verify(surface.canonicalRect.x !== firstX
            || surface.canonicalRect.width !== surface.homeWidth)
    }
}
