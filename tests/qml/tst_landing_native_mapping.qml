import QtQuick
import QtTest

// Landing-card mapping contract.  The cards keep local geometry while the
// reveal ancestor performs horizontal and vertical presentation movement.
TestCase {
    name: "LandingNativeMapping"

    Item {
        id: orbitRenderSource
        width: 1920
        height: 1080

        Item {
            id: reveal
            property real categoryProgress: 1
            property bool categoryTransitioning: false
            property int categoryFrom: 2
            property int categoryTarget: 0
            property int categoryDirection: 1
            property real travel: 1188
            property real rowX: 78
            x: rowX
            readonly property real offset: !categoryTransitioning ? 0
                : categoryTarget === 0 ? -travel * (1 - categoryProgress)
                : categoryFrom === 0 ? travel * categoryProgress
                : categoryDirection * travel * categoryProgress
            y: offset

            function categoryOffset() {
                if (!categoryTransitioning)
                    return 0
                if (categoryTarget === 0)
                    return -travel * (1 - categoryProgress)
                if (categoryFrom === 0)
                    return travel * categoryProgress
                return categoryDirection * travel * categoryProgress
            }

            Item {
                id: cardA
                x: 0
                width: 239.2704
                height: 385.92
                property var mappingDependency: ({
                    rowX: reveal.x,
                    delegateX: x,
                    width: width,
                    height: height
                })
                property real categoryProgress: reveal.categoryProgress
                property bool categoryTransitioning: reveal.categoryTransitioning
                property int categoryFrom: reveal.categoryFrom
                property int categoryTarget: reveal.categoryTarget
                property int categoryDirection: reveal.categoryDirection
                property real presentationAncestorY: reveal.y
                property real presentationAncestorScale: reveal.scale
                readonly property rect canonicalRect: {
                    var dependency = mappingDependency
                    var categoryDependency = categoryProgress
                        + (categoryTransitioning ? 1 : 0)
                        + categoryFrom + categoryTarget + categoryDirection
                        + presentationAncestorY + presentationAncestorScale
                    var topLeft = mapToItem(orbitRenderSource, 0, 0)
                    var bottomRight = mapToItem(orbitRenderSource, width, height)
                    return Qt.rect(topLeft.x + categoryDependency - categoryDependency,
                                   topLeft.y + categoryDependency - categoryDependency,
                                   bottomRight.x - topLeft.x,
                                   bottomRight.y - topLeft.y)
                }
            }

            Item {
                id: cardB
                x: 278
                width: cardA.width
                height: cardA.height
                property var mappingDependency: cardA.mappingDependency
                property real categoryProgress: reveal.categoryProgress
                property bool categoryTransitioning: reveal.categoryTransitioning
                property int categoryFrom: reveal.categoryFrom
                property int categoryTarget: reveal.categoryTarget
                property int categoryDirection: reveal.categoryDirection
                property real presentationAncestorY: reveal.y
                property real presentationAncestorScale: reveal.scale
                readonly property rect canonicalRect: {
                    var dependency = mappingDependency
                    var categoryDependency = categoryProgress
                        + (categoryTransitioning ? 1 : 0)
                        + categoryFrom + categoryTarget + categoryDirection
                        + presentationAncestorY + presentationAncestorScale
                    var topLeft = mapToItem(orbitRenderSource, 0, 0)
                    var bottomRight = mapToItem(orbitRenderSource, width, height)
                    return Qt.rect(topLeft.x + categoryDependency - categoryDependency,
                                   topLeft.y + categoryDependency - categoryDependency,
                                   bottomRight.x - topLeft.x,
                                   bottomRight.y - topLeft.y)
                }
            }

            Item {
                id: cardStore
                x: 556
                width: cardA.width
                height: cardA.height
                property var mappingDependency: cardA.mappingDependency
                property real categoryProgress: reveal.categoryProgress
                property bool categoryTransitioning: reveal.categoryTransitioning
                property int categoryFrom: reveal.categoryFrom
                property int categoryTarget: reveal.categoryTarget
                property int categoryDirection: reveal.categoryDirection
                property real presentationAncestorY: reveal.y
                property real presentationAncestorScale: reveal.scale
                readonly property rect canonicalRect: {
                    var dependency = mappingDependency
                    var categoryDependency = categoryProgress
                        + (categoryTransitioning ? 1 : 0)
                        + categoryFrom + categoryTarget + categoryDirection
                        + presentationAncestorY + presentationAncestorScale
                    var topLeft = mapToItem(orbitRenderSource, 0, 0)
                    var bottomRight = mapToItem(orbitRenderSource, width, height)
                    return Qt.rect(topLeft.x + categoryDependency - categoryDependency,
                                   topLeft.y + categoryDependency - categoryDependency,
                                   bottomRight.x - topLeft.x,
                                   bottomRight.y - topLeft.y)
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

    function test_settledAndHorizontalNavigation() {
        reveal.categoryTransitioning = false
        reveal.rowX = 78
        reveal.categoryProgress = 1
        wait(10)
        verifyMapping(cardA)
        verifyMapping(cardB)
        verifyMapping(cardStore)

        reveal.rowX = 430
        wait(10)
        verifyMapping(cardA)
        verifyMapping(cardB)
        verifyMapping(cardStore)
        verify(cardA.canonicalRect.x !== cardB.canonicalRect.x)
    }

    function test_verticalTransitionBothDirections() {
        reveal.rowX = 78
        reveal.categoryFrom = 2
        reveal.categoryTarget = 0
        reveal.categoryDirection = 1
        reveal.categoryTransitioning = true
        var marks = [0, 0.25, 0.5, 0.75, 1]
        for (var index = 0; index < marks.length; ++index) {
            reveal.categoryProgress = marks[index]
            wait(10)
            compare(reveal.y, -1188 * (1 - marks[index]))
            compare(cardA.categoryProgress, marks[index])
            verifyMapping(cardA)
            verifyMapping(cardB)
            verifyMapping(cardStore)
        }

        reveal.categoryFrom = 0
        reveal.categoryTarget = 2
        reveal.categoryDirection = -1
        for (index = 0; index < marks.length; ++index) {
            reveal.categoryProgress = marks[index]
            wait(10)
            verifyMapping(cardA)
            verifyMapping(cardB)
            verifyMapping(cardStore)
        }
    }

    function test_reversalAndRetarget() {
        reveal.categoryTransitioning = true
        reveal.categoryFrom = 2
        reveal.categoryTarget = 0
        reveal.categoryProgress = 0.5
        wait(10)
        verifyMapping(cardA)

        reveal.categoryFrom = 0
        reveal.categoryTarget = 2
        reveal.categoryDirection = -1
        reveal.categoryProgress = 0.35
        wait(10)
        verifyMapping(cardA)
        verifyMapping(cardB)
        verifyMapping(cardStore)
    }
}
