"""Compatibility import for the extracted RomM plugin adapter."""
import sys
from .plugins.romm import executor as _implementation
sys.modules[__name__] = _implementation
