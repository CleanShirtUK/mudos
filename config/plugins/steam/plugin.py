def register(context):
    context.register("providers", context.manifest.root / "providers")
    from lulu.plugins.steam import SteamEntitlementSource, SteamProvider, SteamCmdExecutor
    context.register("session", SteamProvider())
    context.register("installed_catalogue", SteamEntitlementSource())
    context.register("acquisition", {"provider": "steam", "executor": SteamCmdExecutor(), "limit": 1})
