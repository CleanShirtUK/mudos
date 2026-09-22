def register(context):
    from lulu.provider_config import ProviderConfigurationService
    from lulu.plugins.torrent import TransmissionClient, TransmissionConfig, TorrentProvider

    configuration = ProviderConfigurationService.from_environment().provider("providers.torrent")
    if not configuration.enabled or not configuration.configured:
        # Optional providers are deliberately absent rather than fatal when
        # first-run provisioning has not configured them yet.
        return
    backend = str(configuration.get("backend", "transmission")).casefold()
    if backend != "transmission":
        return
    client = TransmissionClient(TransmissionConfig(
        endpoint=str(configuration.get("endpoint", "http://127.0.0.1:9091/transmission/rpc")),
        timeout_seconds=float(configuration.get("timeout_seconds", 10)),
        username=configuration.secret("username") or "",
        password=configuration.secret("password") or "",
        label=str(configuration.get("label", "mudos")),
    ))
    from lulu.questarr_metadata import QuestarrMetadataClient
    context.register("acquisition", {"provider": "torrent",
                                      "executor": TorrentProvider(client, questarr_metadata=QuestarrMetadataClient()),
                                      "limit": 1})
