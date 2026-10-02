def register(context):
    from lulu.plugins.steam import SteamProvider
    steam = SteamProvider()
    # Keep SteamProvider's process/AppID observation helpers for Sessiond's
    # runtime supervision, but do not register the legacy Steam client,
    # credential, catalogue, or SteamCMD acquisition backends.
    context.register("session", steam)

    # Aurelia is the only Steam entitlement and acquisition backend.
    from lulu.provider_config import ProviderConfigurationService
    aurelia_config = ProviderConfigurationService.from_environment().provider(
        "providers.steam_aurelia")
    if aurelia_config.enabled:
        from lulu.plugins.steam.aurelia import (
            AureliaAcquisitionExecutor, AureliaClient, AureliaEntitlementSource,
        )
        aurelia = AureliaClient()
        context.register("installed_catalogue", AureliaEntitlementSource(aurelia))
        context.register("acquisition", {
            "provider": "steam-aurelia",
            "executor": AureliaAcquisitionExecutor(aurelia),
            "limit": 1,
        })
