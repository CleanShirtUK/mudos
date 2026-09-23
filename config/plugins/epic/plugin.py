def register(context):
    context.register("providers", context.manifest.root / "providers")
    from lulu.plugins.epic import EpicAcquisitionExecutor, EpicAuthentication, EpicEntitlementSource, EpicLauncher
    context.register("installed_catalogue", EpicEntitlementSource())
    context.register("authentication", EpicAuthentication())
    context.register("acquisition", {"provider": "epic", "executor": EpicAcquisitionExecutor(), "limit": 1})
    context.register("launch", EpicLauncher())
