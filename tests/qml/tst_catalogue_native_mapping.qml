import QtQuick
import QtTest

TestCase {
    name: "CatalogueNativeMapping"

    Item {
        id: orbitRenderSource
        width: 1920
        height: 1080

        Item {
            id: viewport
            x: 120
            y: 250
            width: 1600
            height: 500
            clip: true

            Item {
                id: grid
                x: 60
                y: 40
                property real contentY: 0
                Item {
                    id: cardA
                    x: 0
                    y: 0
                    width: 240
                    height: 372
                    scale: selected ? 1.05 : 1
                    property bool selected: false
                    property var mappingDependency: ({
                        viewportX: viewport.x,
                        viewportY: viewport.y,
                        gridX: grid.x,
                        gridY: grid.y,
                        contentY: grid.contentY,
                        delegateX: x,
                        delegateY: y,
                        width: width,
                        height: height,
                        scale: scale,
                        selected: selected
                    })
                    property real mappingRevision: viewport.x + viewport.y
                        + grid.x + grid.y + grid.contentY + x + y
                        + width + height + scale + (selected ? 1 : 0)
                    readonly property rect canonicalRect: {
                        var dependency = mappingDependency
                        var revision = mappingRevision
                        var topLeft = mapToItem(orbitRenderSource, 0, 0)
                        var bottomRight = mapToItem(orbitRenderSource,
                                                    width, height)
                        return Qt.rect(topLeft.x + revision - revision,
                                       topLeft.y + revision - revision,
                                       bottomRight.x - topLeft.x,
                                       bottomRight.y - topLeft.y)
                    }
                }
                Item {
                    id: cardB
                    x: 254
                    y: 0
                    width: cardA.width
                    height: cardA.height
                    property bool selected: false
                    property var mappingDependency: cardA.mappingDependency
                    property real mappingRevision: viewport.x + viewport.y
                        + grid.x + grid.y + grid.contentY + x + y
                        + width + height + scale + (selected ? 1 : 0)
                    readonly property rect canonicalRect: {
                        var dependency = mappingDependency
                        var revision = mappingRevision
                        var topLeft = mapToItem(orbitRenderSource, 0, 0)
                        var bottomRight = mapToItem(orbitRenderSource,
                                                    width, height)
                        return Qt.rect(topLeft.x + revision - revision,
                                       topLeft.y + revision - revision,
                                       bottomRight.x - topLeft.x,
                                       bottomRight.y - topLeft.y)
                    }
                }
            }
        }
    }

    function verifyMapping(card) {
        var topLeft = card.mapToItem(orbitRenderSource, 0, 0)
        var bottomRight = card.mapToItem(orbitRenderSource,
                                         card.width, card.height)
        compare(card.canonicalRect.x, topLeft.x)
        compare(card.canonicalRect.y, topLeft.y)
        compare(card.canonicalRect.width, bottomRight.x - topLeft.x)
        compare(card.canonicalRect.height, bottomRight.y - topLeft.y)
    }

    function test_initialScrollScaleAndReuse() {
        verifyMapping(cardA)
        verifyMapping(cardB)
        verify(cardA.canonicalRect.x !== cardB.canonicalRect.x)

        grid.contentY = 180
        wait(10)
        verifyMapping(cardA)
        verifyMapping(cardB)

        cardA.selected = true
        wait(10)
        verifyMapping(cardA)

        cardA.y = 744
        cardB.y = 372
        grid.contentY = 372
        wait(10)
        verifyMapping(cardA)
        verifyMapping(cardB)
        verify(cardA.canonicalRect.x !== cardB.canonicalRect.x)
    }

    function test_boundaryMovementRemainsReactive() {
        cardA.y = -360
        grid.contentY = 0
        wait(10)
        verifyMapping(cardA)
        cardA.y = 12
        grid.contentY = 260
        wait(10)
        verifyMapping(cardA)
        cardA.y = 384
        grid.contentY = 520
        wait(10)
        verifyMapping(cardA)
    }
}
