def register(context):
    from lulu.provider_config import ProviderConfigurationService
    from lulu.plugins.usenet import build_executor

    configuration = ProviderConfigurationService.from_environment().provider("providers.usenet")
    if not configuration.enabled or not configuration.configured:
        return
    _, executor = build_executor(configuration)
    context.register("acquisition", {"provider": "usenet",
                                      "executor": executor,
                                      "limit": 1})
