"""Provider-neutral Usenet acquisition backed by NZBGet."""

from .nzbget import NzbGetClient, NzbGetConfig, NzbGetError, UsenetProvider, UsenetServerConfig


def build_executor(configuration):
    """Build NZBGet client/executor using the shared provider configuration."""
    client = NzbGetClient(NzbGetConfig(
        endpoint=str(configuration.get("endpoint", "http://127.0.0.1:6789/jsonrpc")),
        username=str(configuration.get("username", "mudos")),
        password=configuration.secret("rpc_password") or "",
        timeout_seconds=float(configuration.get("timeout_seconds", 10)),
        category=str(configuration.get("category", "mudos")),
        dupe_prefix=str(configuration.get("dupe_prefix", "mudos:")),
    ))
    return client, UsenetProvider(client)


__all__ = ["NzbGetClient", "NzbGetConfig", "NzbGetError", "UsenetProvider",
           "UsenetServerConfig", "build_executor"]
