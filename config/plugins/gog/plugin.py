def register(context):
    context.register("providers", context.manifest.root / "providers")
    from lulu.plugins.gog import GogAcquisitionExecutor, GogAuthentication, GogEntitlementSource, GogLauncher
    context.register("installed_catalogue", GogEntitlementSource())
    context.register("authentication", GogAuthentication())
    context.register("acquisition", {"provider": "gog", "executor": GogAcquisitionExecutor(), "limit": 1})
    context.register("launch", GogLauncher())
