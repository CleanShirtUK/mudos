def register(context):
    context.register("providers", context.manifest.root / "providers")
    from lulu.plugins.steam import SteamAuthentication, SteamEntitlementSource, SteamProvider, SteamCmdExecutor
    steam = SteamProvider()
    context.register("session", steam)
    executor = SteamCmdExecutor()
    context.register("authentication", SteamAuthentication(steam, executor))
    context.register("installed_catalogue", SteamEntitlementSource())
    context.register("acquisition", {"provider": "steam", "executor": executor, "limit": 1})
