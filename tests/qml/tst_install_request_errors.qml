import QtQuick
import QtTest
import "../../ui/InstallRequestErrors.js" as InstallRequestErrors

TestCase {
    name: "InstallRequestErrors"

    function test_backend_rejection_reason_is_preserved_for_visible_error() {
        var reason = InstallRequestErrors.responseReason(
                    '{"error":"acquisition is not retryable"}', "Install failed")
        compare(reason, "acquisition is not retryable")
        compare(InstallRequestErrors.installationFailure("Rocket League", reason),
                "Rocket League was not installed: acquisition is not retryable")
    }

    function test_provider_details_and_fallback_are_safe() {
        compare(InstallRequestErrors.responseReason(
                    '{"error":{"message":"A Steam remove job is already active"}}', "Install failed"),
                "A Steam remove job is already active")
        compare(InstallRequestErrors.responseReason("not-json", "Platform lookup failed"),
                "Platform lookup failed")
    }
}
