"""Content/platform definitions and their registry."""

from .model import BiosDefinition, ContentDefinition, PlatformDefinition
from .registry import PlatformRegistry, load_platforms

__all__ = ["BiosDefinition", "ContentDefinition", "PlatformDefinition", "PlatformRegistry", "load_platforms"]
