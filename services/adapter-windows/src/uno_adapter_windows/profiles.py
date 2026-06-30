"""Load Windows adapter profiles."""

from __future__ import annotations

from pathlib import Path

from uno_schemas.adapter_windows import WindowsAdapterProfile

PROFILES_DIR = Path(__file__).resolve().parent.parent.parent / "profiles"


def load_profile(profile_id: str) -> WindowsAdapterProfile:
  path = PROFILES_DIR / f"{profile_id}.json"
  if not path.exists():
    raise FileNotFoundError(f"profile not found: {profile_id}")
  return WindowsAdapterProfile.model_validate_json(path.read_text(encoding="utf-8"))


def list_profiles() -> list[WindowsAdapterProfile]:
  profiles: list[WindowsAdapterProfile] = []
  for file in sorted(PROFILES_DIR.glob("*.json")):
    profiles.append(WindowsAdapterProfile.model_validate_json(file.read_text(encoding="utf-8")))
  return profiles
