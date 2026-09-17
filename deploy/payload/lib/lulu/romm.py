"""Compatibility import for the extracted RomM plugin adapter."""
import sys
from .plugins.romm import client as _implementation
sys.modules[__name__] = _implementation
