def register(context):
    from lulu.plugins.romm import RommClient, RommConfig, RommExecutor
    config = RommConfig.from_file()
    client = RommClient(config) if config else None
    context.register("installed_catalogue", client)
    context.register("metadata", client)
    context.register("acquisition", {"provider": "romm", "executor": RommExecutor(client), "limit": 1})
