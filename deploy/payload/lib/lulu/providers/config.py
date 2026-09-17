"""Persistent native provider configuration adapters."""

from pathlib import Path


class NativeConfigAdapter:
    """Small line-preserving adapter for selected INI-style native settings."""

    def __init__(self, path: Path):
        self.path = path

    def get(self, section: str, key: str, default: str | None = None) -> str | None:
        current = None
        if not self.path.is_file():
            return default
        for line in self.path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                current = stripped[1:-1]
            elif (current == section or (section == "" and current is None)) and "=" in line:
                name, value = line.split("=", 1)
                if name.strip() == key:
                    return value.strip()
        return default

    def set(self, section: str, key: str, value: str) -> None:
        source = self.path.read_text(encoding="utf-8") if self.path.is_file() else ""
        lines = source.splitlines()
        start = None if section == "" else next(
            (i for i, line in enumerate(lines) if line.strip() == f"[{section}]"), None
        )
        if section == "":
            match = next((i for i, line in enumerate(lines)
                          if "=" in line and "[" not in line and line.split("=", 1)[0].strip() == key), None)
            if match is not None:
                lines[match] = f'{key} = "{value.strip(chr(34))}"'
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix(self.path.suffix + ".tmp")
                temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
                temporary.replace(self.path)
                return
            lines.insert(0, f'{key} = "{value.strip(chr(34))}"')
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
            temporary.replace(self.path)
            return
        if start is None:
            if lines and lines[-1] != "":
                lines.append("")
            lines.extend([f"[{section}]", f"{key}={value}"])
        else:
            end = next((i for i in range(start + 1, len(lines)) if lines[i].strip().startswith("[")), len(lines))
            match = next((i for i in range(start + 1, end)
                          if "=" in lines[i] and lines[i].split("=", 1)[0].strip() == key), None)
            if match is None:
                lines.insert(end, f"{key}={value}")
            else:
                lines[match] = f"{key}={value}"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        temporary.replace(self.path)
