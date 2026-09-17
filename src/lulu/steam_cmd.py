"""Compatibility import for the extracted Steam plugin adapter."""
import sys
from .plugins.steam import cmd as _implementation
sys.modules[__name__] = _implementation
