def register(context):
    from lulu.provider_config import ProviderConfigurationService
    from lulu.plugins.usenet import NzbGetClient, NzbGetConfig, UsenetProvider

    configuration = ProviderConfigurationService.from_environment().provider("providers.usenet")
    if not configuration.enabled or not configuration.configured:
        return
    client = NzbGetClient(NzbGetConfig(
        endpoint=str(configuration.get("endpoint", "http://127.0.0.1:6789/jsonrpc")),
        username=str(configuration.get("username", "mudos")),
        password=configuration.secret("rpc_password") or "",
        timeout_seconds=float(configuration.get("timeout_seconds", 10)),
        category=str(configuration.get("category", "mudos")),
        dupe_prefix=str(configuration.get("dupe_prefix", "mudos:")),
    ))
    context.register("acquisition", {"provider": "usenet",
                                      "executor": UsenetProvider(client),
                                      "limit": 1})
