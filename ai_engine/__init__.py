"""Compatibility package for DecisionOS.

This package points Python imports at the existing `ai-engine` directory,
which cannot be imported directly because of the hyphen in its name.
"""

from pathlib import Path

_package_root = Path(__file__).resolve().parent
_legacy_root = _package_root.parent / "ai-engine"

__path__ = [str(_legacy_root)] if _legacy_root.exists() else [str(_package_root)]
