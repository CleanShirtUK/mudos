import QtQuick
import QtTest

// Regression contract for Recent's native mapping dependency.  This mirrors
// the production relationship: the card keeps its local geometry while its
// delegate and row ancestors provide the presented translation.
TestCase {
    name: "RecentNativeMapping"

    Item {
        id: orbitRenderSource
        width: 1920
        height: 1080

        Item {
            id: recentRow
            x: rowX
            property real rowX: 0

            Item {
                id: delegate
                x: delegateX
                property real delegateX: 400
                property var mappingDependency: ({
                    rowX: recentRow.x,
                    delegateX: delegate.x,
                    delegateWidth: width,
                    delegateHeight: height,
                    transition: transition,
                    retarget: retarget
                })
                property real transition: 1
                property real retarget: 0

                Item {
                    id: card
                    width: 240
                    height: 472
                    property var dependency: delegate.mappingDependency
                    readonly property rect canonicalRect: {
                        var dependencyRead = dependency
                        var topLeft = mapToItem(orbitRenderSource, 0, 0)
                        var bottomRight = mapToItem(orbitRenderSource, width, height)
                        return Qt.rect(topLeft.x, topLeft.y,
                                       bottomRight.x - topLeft.x,
                                       bottomRight.y - topLeft.y)
                    }
                }
            }
        }
    }

    function test_stationaryCompactCard() {
        compare(card.canonicalRect.x, 400)
        compare(card.canonicalRect.width, 240)
    }

    function test_delegateTranslationInvalidatesMapping() {
        var before = card.canonicalRect.x
        delegate.delegateX = 520
        verify(card.canonicalRect.x !== before)
        compare(card.canonicalRect.x, 520)
    }

    function test_rowTranslationInvalidatesMapping() {
        delegate.delegateX = 400
        recentRow.rowX = 180
        compare(card.canonicalRect.x, 580)
        recentRow.rowX = 0
    }

    function test_focalResizeAndTranslation() {
        delegate.delegateX = 300
        card.width = 760
        recentRow.rowX = 90
        compare(card.canonicalRect.x, 390)
        compare(card.canonicalRect.width, 760)
        card.width = 240
        recentRow.rowX = 0
    }

    function test_initiallyOffscreenEntersRail() {
        delegate.delegateX = 2200
        verify(card.canonicalRect.x > 2000)
        delegate.delegateX = 900
        compare(card.canonicalRect.x, 900)
    }

    function test_interruptedRetarget() {
        delegate.delegateX = 700
        delegate.transition = 0.25
        compare(card.canonicalRect.x, 700)
        delegate.delegateX = 1100
        delegate.retarget = 1
        compare(card.canonicalRect.x, 1100)
        delegate.delegateX = 820
        delegate.transition = 0.75
        compare(card.canonicalRect.x, 820)
    }
}
