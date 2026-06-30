#!/usr/bin/env python3
"""Print model registry and profile status."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "schemas" / "src"))
sys.path.insert(0, str(ROOT / "services" / "model-registry-service" / "src"))

from uno_model_registry.registry import ModelRegistry

reg = ModelRegistry(ROOT / "models" / "registry", ROOT / "models" / "profiles")
print(json.dumps({
  "manifests": [m.model_dump() for m in reg.list_models()],
  "profiles": [p.model_dump() for p in reg.list_profiles()],
}, indent=2, default=str))
