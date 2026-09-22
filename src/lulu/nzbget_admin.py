"""Narrow administrative boundary for NZBGet control credentials."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile


CONFIG_PATH = Path(os.environ.get("LULU_NZBGET_CONFIG", "/var/lib/nzbget/nzbget.conf"))
PACKAGED_WEB_DIR = "/usr/share/nzbget/webui"
PACKAGED_CONFIG_TEMPLATE = "/usr/share/nzbget/nzbget.conf"
MANAGED_SCRIPT_DIR = "/var/lib/nzbget/scripts"


def apply_control_credentials(username: str, password: str, path: Path = CONFIG_PATH) -> None:
    """Materialize provider-owned credentials into NZBGet's private config.

    The password is intentionally accepted only as an argument from the
    already-authenticated SecretStore boundary and is never logged. NZBGet's
    config remains private; provisioning grants only the lulu admin service
    the narrow write access needed for this operation.
    """
    if not username or not password or any(char in username + password for char in "\r\n"):
        raise ValueError("NZBGet control credentials must be non-empty and single-line")
    lines = path.read_text().splitlines()
    replacements = {"ControlUsername": username, "ControlPassword": password}
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        key, separator, _ = line.partition("=")
        if separator and key in replacements:
            output.append(f"{key}={replacements[key]}")
            seen.add(key)
        else:
            output.append(line)
    for key, value in replacements.items():
        if key not in seen:
            output.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=".nzbget.", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write("\n".join(output) + "\n")
    os.chmod(temporary, 0o660)
    os.replace(temporary, path)


def apply_packaged_paths(path: Path = CONFIG_PATH) -> None:
    """Keep package-owned Web UI/template paths in the managed config."""
    values = {
        "WebDir": PACKAGED_WEB_DIR,
        "ConfigTemplate": PACKAGED_CONFIG_TEMPLATE,
        # CachyOS's package has no /usr/share/nzbget/scripts directory;
        # retain the writable managed script directory instead.
        "ScriptDir": MANAGED_SCRIPT_DIR,
    }
    lines = path.read_text().splitlines()
    output: list[str] = []
    seen: set[str] = set()
    for line in lines:
        key, separator, _ = line.partition("=")
        if separator and key in values:
            output.append(f"{key}={values[key]}"); seen.add(key)
        else:
            output.append(line)
    for key, value in values.items():
        if key not in seen: output.append(f"{key}={value}")
    with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=".nzbget.", delete=False) as stream:
        temporary = Path(stream.name); stream.write("\n".join(output) + "\n")
    os.chmod(temporary, 0o660)
    os.replace(temporary, path)


def apply_news_server(host: str, port: int, tls: bool, connections: int,
                      username: str, password: str, enabled: bool = True,
                      path: Path = CONFIG_PATH) -> None:
    """Materialize the single primary Mudos news server as NZBGet Server1."""
    if not host or not (1 <= port <= 65535) or not (1 <= connections <= 999):
        raise ValueError("invalid Usenet server configuration")
    if any(char in host + username + password for char in "\r\n"):
        raise ValueError("Usenet server values must be single-line")
    values = {
        "Server1.Active": "yes" if enabled else "no",
        "Server1.Host": host,
        "Server1.Port": str(port),
        "Server1.Encryption": "yes" if tls else "no",
        "Server1.Username": username,
        "Server1.Password": password,
        "Server1.Connections": str(connections),
    }
    lines = path.read_text().splitlines()
    output: list[str] = []
    seen: set[str] = set()
    for line in lines:
        key, separator, _ = line.partition("=")
        if separator and key in values:
            output.append(f"{key}={values[key]}"); seen.add(key)
        else:
            output.append(line)
    for key, value in values.items():
        if key not in seen: output.append(f"{key}={value}")
    with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=".nzbget.", delete=False) as stream:
        temporary = Path(stream.name); stream.write("\n".join(output) + "\n")
    os.chmod(temporary, 0o660)
    os.replace(temporary, path)
