"""Non-destructive migration of conventional provider state."""

from pathlib import Path
import shutil


def migrate_tree(source: Path, target: Path) -> list[Path]:
    """Copy missing native files, never overwrite or delete user state."""
    migrated: list[Path] = []
    if not source.is_dir():
        return migrated
    for item in source.rglob("*"):
        relative = item.relative_to(source)
        destination = target / relative
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif item.is_file() and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)
            migrated.append(destination)
    return migrated
