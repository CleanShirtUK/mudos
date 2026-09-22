"""Flatpak provider boundary."""

from .adapter import FlatpakAdapter, FlatpakApplication, FlatpakError, FlatpakJobExecutor

__all__ = ["FlatpakAdapter", "FlatpakApplication", "FlatpakError", "FlatpakJobExecutor"]
