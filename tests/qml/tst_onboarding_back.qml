import QtQuick
import QtTest
import "../../ui/OnboardingBack.js" as OnboardingBack

TestCase {
    name: "OnboardingBack"

    function test_setup_keeps_back_inside_onboarding_regardless_of_connectivity() {
        compare(OnboardingBack.action(true, false, false), "stay-onboarding")
        compare(OnboardingBack.action(true, true, false), "show-onboarding")
    }

    function test_wifi_credential_back_closes_only_credentials() {
        compare(OnboardingBack.action(true, true, true), "close-credential")
        compare(OnboardingBack.action(true, false, true), "stay-onboarding")
    }

    function test_only_finished_or_explicitly_dismissed_setup_returns_to_shell() {
        compare(OnboardingBack.action(false, true, true), "shell")
        compare(OnboardingBack.action(false, false, false), "shell")
    }
}
