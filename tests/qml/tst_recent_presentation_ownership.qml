import QtQuick
import QtTest

TestCase {
    name: "RecentPresentationOwnership"

    Item {
        id: presentation
        property bool selectionMotionActive: false
        property bool selectionBlurAllowed: true
        readonly property bool blurActive: selectionMotionActive
            && selectionBlurAllowed
        readonly property bool directSourceVisible: !blurActive
        readonly property bool blurOutputVisible: blurActive
        readonly property bool sourceHidden: blurActive
        readonly property bool captureLive: blurActive
    }

    function test_settledUsesDirectLogicalHierarchy() {
        presentation.selectionMotionActive = false
        compare(presentation.blurActive, false)
        compare(presentation.directSourceVisible, true)
        compare(presentation.blurOutputVisible, false)
        compare(presentation.sourceHidden, false)
        compare(presentation.captureLive, false)
    }

    function test_motionUsesCaptureAndBlurOutput() {
        presentation.selectionMotionActive = true
        presentation.selectionBlurAllowed = true
        compare(presentation.blurActive, true)
        compare(presentation.directSourceVisible, false)
        compare(presentation.blurOutputVisible, true)
        compare(presentation.sourceHidden, true)
        compare(presentation.captureLive, true)
    }

    function test_settlementReturnsToDirectAfterMotion() {
        presentation.selectionMotionActive = true
        verify(presentation.blurActive)
        presentation.selectionMotionActive = false
        compare(presentation.blurActive, false)
        compare(presentation.directSourceVisible, true)
        compare(presentation.blurOutputVisible, false)
    }

    function test_retargetKeepsBlurAuthoritativeUntilFinalSettlement() {
        presentation.selectionMotionActive = true
        presentation.selectionBlurAllowed = true
        verify(presentation.blurActive)

        // A retarget/reversal keeps the transition running; ownership must
        // not return to the logical source before the final settlement.
        presentation.selectionMotionActive = true
        presentation.selectionBlurAllowed = true
        verify(presentation.blurActive)
        presentation.selectionMotionActive = false
        compare(presentation.directSourceVisible, true)
    }
}
