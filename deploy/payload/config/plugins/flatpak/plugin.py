def register(context):
    from lulu.plugins.flatpak import FlatpakAdapter, FlatpakJobExecutor

    adapter = FlatpakAdapter()
    context.register("provider", adapter)
    context.register("catalogue", adapter)
    context.register("launch", adapter)
    context.register("browser_handoff", adapter)
    context.register("acquisition", {
        "provider": "flatpak",
        "executor": FlatpakJobExecutor(adapter),
        "limit": 1,
    })
