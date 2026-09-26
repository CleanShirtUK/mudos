import QtQuick
import QtTest
import "../../ui" as UI

TestCase {
    name: "OnboardingActions"
    width: 1280
    height: 720
    when: windowShown

    UI.Onboarding { id: setup; width: parent.width; height: parent.height }
    SignalSpy { id: networkSpy; target: setup; signalName: "openNetworkSettings" }
    SignalSpy { id: localSpy; target: setup; signalName: "setUpLocally" }
    SignalSpy { id: homeSpy; target: setup; signalName: "continueToHome" }

    function init() {
        setup.online = false
        setup.networkAdapterAvailable = true
        setup.selectedAction = 0
        networkSpy.clear()
        localSpy.clear()
        homeSpy.clear()
    }

    function test_offline_controller_actions_have_visible_selection_and_large_controls() {
        compare(setup.actionCount, 3)
        var wifi = findChild(setup, "onboardingOfflineAction0")
        verify(wifi !== null)
        verify(wifi.implicitWidth >= 300)
        verify(wifi.implicitHeight >= 58)
        verify(wifi.highlighted)
        setup.activate()
        compare(networkSpy.count, 1)
        setup.move(1)
        compare(setup.selectedAction, 1)
        setup.activate()
        compare(localSpy.count, 1)
        setup.move(1)
        setup.activate()
        compare(homeSpy.count, 1)
    }

    function test_online_transition_selects_setup_not_accidental_home() {
        setup.selectedAction = 2 // Continue to Home while offline
        setup.online = true
        compare(setup.actionCount, 2)
        compare(setup.selectedAction, 0)
        var local = findChild(setup, "onboardingOnlineAction0")
        verify(local !== null)
        verify(local.highlighted)
        verify(local.implicitWidth >= 300)
        setup.activate()
        compare(localSpy.count, 1)
        compare(homeSpy.count, 0)
        setup.move(1)
        setup.activate()
        compare(homeSpy.count, 1)
        setup.online = false
        setup.selectedAction = 2
        setup.networkAdapterAvailable = false
        compare(setup.actionCount, 2)
        compare(setup.selectedAction, 0)
        setup.activate()
        compare(localSpy.count, 2)
    }
}
