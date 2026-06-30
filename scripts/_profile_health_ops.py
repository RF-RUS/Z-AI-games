#!/usr/bin/env python3
"""Shared CLI helpers for profile health operations."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "schemas" / "src"))
sys.path.insert(0, str(ROOT / "services" / "adapter-web" / "src"))

from uno_adapter_web.health_store import load_reports  # noqa: E402
from uno_adapter_web.profiles import load_profile  # noqa: E402


def parse_args(description: str):
  import argparse
  p = argparse.ArgumentParser(description=description)
  p.add_argument("--profile", default="real-unoh-web")
  p.add_argument("--limit", type=int, default=20)
  p.add_argument("--json", action="store_true", help="Emit JSON only")
  return p


def load_ctx(profile_id: str, limit: int):
  profile = load_profile(profile_id)
  reports = load_reports(profile_id, limit=limit)
  return profile, reports
