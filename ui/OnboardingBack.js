.pragma library

// Onboarding remains the navigation owner until setup completes or the user
// explicitly chooses Continue to Home, regardless of connectivity changes.
function action(open, networkSettings, credentialView) {
    if (!open)
        return "shell"
    if (networkSettings && credentialView)
        return "close-credential"
    if (networkSettings)
        return "show-onboarding"
    return "stay-onboarding"
}
