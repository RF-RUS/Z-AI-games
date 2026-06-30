"""Load and validate web adapter profiles."""

from __future__ import annotations

import json
from pathlib import Path

from uno_schemas.adapter_web import WebAdapterProfile

PROFILES_DIR = Path(__file__).resolve().parent.parent.parent / "profiles"


def load_profile(profile_id: str) -> WebAdapterProfile:
  path = PROFILES_DIR / f"{profile_id}.json"
  if not path.exists():
    raise FileNotFoundError(f"profile not found: {profile_id}")
  data = json.loads(path.read_text(encoding="utf-8"))
  return WebAdapterProfile.model_validate(data)


def list_profiles() -> list[WebAdapterProfile]:
  profiles: list[WebAdapterProfile] = []
  for file in sorted(PROFILES_DIR.glob("*.json")):
    data = json.loads(file.read_text(encoding="utf-8"))
    profiles.append(WebAdapterProfile.model_validate(data))
  return profiles
