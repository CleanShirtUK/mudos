import QtQuick
import QtTest

// Contract regression for landing navigation cards. The probe deliberately
// keeps each card's local geometry fixed while the row and delegates move.
TestCase {
    name: "NavigationNativeMapping"

    Item {
        id: orbitRenderSource
        width: 1920
        height: 1080

        Item {
            id: navigationRow
            property real presentationX: 0
            property real categoryProgress: 0
            property real categoryTravel: 1152
            x: presentationX
            y: -categoryTravel * (1 - categoryProgress)

            Repeater {
                id: cards
                model: 2
                delegate: Item {
                    required property int index
                    property real presentationX: index * 278
                    x: presentationX
                    width: 260
                    height: 400
                    property var mappingDependency: ({
                        rowX: navigationRow.x,
                        delegateX: x,
                        categoryProgress: navigationRow.categoryProgress,
                        width: width,
                        height: height,
                        transition: transition
                    })
                    property real transition: 1

                    Item {
                        id: cardItem
                        anchors.fill: parent
                        property var dependency: parent.mappingDependency
                        readonly property rect canonicalRect: {
                            var dependencyRead = dependency
                            var topLeft = mapToItem(orbitRenderSource, 0, 0)
                            var bottomRight = mapToItem(orbitRenderSource,
                                                        width, height)
                            return Qt.rect(topLeft.x, topLeft.y,
                                           bottomRight.x - topLeft.x,
                                           bottomRight.y - topLeft.y)
                        }
                    }
                }
            }
        }
    }

    function test_adjacentSettledCardsAreUnique() {
        compare(cards.itemAt(0).canonicalRect.x, 0)
        compare(cards.itemAt(1).canonicalRect.x, 278)
        compare(cards.itemAt(0).canonicalRect.width,
                cards.itemAt(1).canonicalRect.width)
    }

    function test_delegateTranslationWithFixedLocalGeometry() {
        var card = cards.itemAt(0)
        var before = card.canonicalRect.x
        card.presentationX = 420
        verify(card.canonicalRect.x !== before)
        compare(card.canonicalRect.x, 420)
    }

    function test_rowTranslationWithFixedCardGeometry() {
        navigationRow.presentationX = 180
        compare(cards.itemAt(0).canonicalRect.x, 180)
        compare(cards.itemAt(1).canonicalRect.x, 458)
        navigationRow.presentationX = 0
    }

    function test_retargetAndResize() {
        var card = cards.itemAt(1)
        card.presentationX = 640
        card.transition = 0.25
        compare(card.canonicalRect.x, 640)
        card.width = 300
        compare(card.canonicalRect.width, 300)
        card.presentationX = 120
        card.transition = 0.75
        compare(card.canonicalRect.x, 120)
    }

    function test_categoryAncestorMovementInvalidatesMapping() {
        var card = cards.itemAt(0)
        navigationRow.categoryProgress = 0
        compare(card.canonicalRect.y, -1152)
        navigationRow.categoryProgress = 0.5
        compare(card.canonicalRect.y, -576)
        navigationRow.categoryProgress = 1
        compare(card.canonicalRect.y, 0)
    }

    function test_categoryRetargetAndReversalRemainReactive() {
        var card = cards.itemAt(1)
        navigationRow.categoryProgress = 0.25
        compare(card.canonicalRect.y, -864)
        navigationRow.categoryProgress = 0.75
        compare(card.canonicalRect.y, -288)
        navigationRow.categoryProgress = 0.1
        compare(card.canonicalRect.y, -1036.8)
    }
}
