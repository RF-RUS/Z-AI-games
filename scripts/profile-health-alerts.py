#!/usr/bin/env python3
"""Evaluate and emit profile health alerts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "schemas" / "src"))
sys.path.insert(0, str(ROOT / "services" / "adapter-web" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from _profile_health_ops import load_ctx, parse_args  # noqa: E402
from uno_adapter_web.profile_alerts import evaluate_alerts, persist_alerts  # noqa: E402


def main() -> None:
  args = parse_args("Profile health alerts").parse_args()
  profile, reports = load_ctx(args.profile, args.limit)
  alerts = evaluate_alerts(reports, profile)
  paths = persist_alerts(alerts)
  out = {"profile_id": args.profile, "alerts": [a.model_dump(mode="json") for a in alerts], "artifact_paths": paths}
  print(json.dumps(out, indent=2))
  if any(a.severity.value == "critical" for a in alerts):
    sys.exit(1)
  if any(a.severity.value == "warning" for a in alerts):
    sys.exit(2)
  sys.exit(0)


if __name__ == "__main__":
  main()
