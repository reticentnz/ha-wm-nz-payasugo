"""Load PayAsUGO API modules without importing Home Assistant."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types


ROOT = Path(__file__).parents[1]
COMPONENT = ROOT / "custom_components" / "payasugo"


def _load_module(name: str, path: Path) -> None:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


custom_components = types.ModuleType("custom_components")
custom_components.__path__ = [str(ROOT / "custom_components")]
sys.modules["custom_components"] = custom_components

payasugo = types.ModuleType("custom_components.payasugo")
payasugo.__path__ = [str(COMPONENT)]
sys.modules["custom_components.payasugo"] = payasugo

_load_module("custom_components.payasugo.const", COMPONENT / "const.py")
_load_module("custom_components.payasugo.models", COMPONENT / "models.py")
_load_module("custom_components.payasugo.api", COMPONENT / "api.py")
