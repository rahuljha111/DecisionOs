"""Compatibility shim for the legacy ai-engine module layout."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_legacy_file = Path(__file__).resolve().parent.parent / "ai-engine" / "orchestrator.py"
_spec = spec_from_file_location("ai_engine._legacy_orchestrator", _legacy_file)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Unable to load legacy orchestrator from {_legacy_file}")

_legacy_module = module_from_spec(_spec)
_spec.loader.exec_module(_legacy_module)

stream_decision = _legacy_module.stream_decision
