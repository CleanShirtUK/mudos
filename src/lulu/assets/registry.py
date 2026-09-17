from pathlib import Path

from ..paths import PATHS


class AssetRegistry:
    """Resolve logical asset IDs without leaking filesystem policy to QML."""

    def __init__(self, root: Path | None = None):
        self.root = root or PATHS.assets_root

    def resolve(self, logical_id: str) -> Path:
        path = (self.root / logical_id).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError(f"asset escapes asset root: {logical_id}")
        return path
