def register(context):
    context.register("providers", context.manifest.root / "providers")
    from lulu.plugins.steam import SteamAuthentication, SteamEntitlementSource, SteamProvider, SteamCmdExecutor
    steam = SteamProvider()
    context.register("session", steam)
    executor = SteamCmdExecutor()
    context.register("authentication", SteamAuthentication(steam, executor))
    context.register("installed_catalogue", SteamEntitlementSource())
    context.register("acquisition", {"provider": "steam", "executor": executor, "limit": 1})

    # A separate identity and executor keep the known-good SteamCMD path intact.
    # This contribution is absent unless an administrator explicitly opts in.
    from lulu.provider_config import ProviderConfigurationService
    experimental = ProviderConfigurationService.from_environment().provider(
        "providers.steam_aurelia")
    if experimental.enabled:
        from lulu.plugins.steam.aurelia import AureliaAcquisitionExecutor, AureliaClient
        aurelia = AureliaClient()
        context.register("acquisition", {
            "provider": "steam-aurelia",
            "executor": AureliaAcquisitionExecutor(aurelia),
            "limit": 1,
        })
