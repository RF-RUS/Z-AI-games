#!/usr/bin/env python3
"""List recent profile health runs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _profile_health_ops import load_ctx, parse_args  # noqa: E402
from uno_adapter_web.health_store import to_history_entry  # noqa: E402


def main() -> None:
  args = parse_args("Profile health history").parse_args()
  _, reports = load_ctx(args.profile, args.limit)
  entries = [to_history_entry(r).model_dump(mode="json") for r in reports]
  if args.json:
    print(json.dumps(entries, indent=2))
    return
  if not entries:
    print(f"No health reports for {args.profile}")
    return
  for e in entries:
    print(f"{e['timestamp_ms']}\t{e['status']}\tfallback={e['fallback_usage_count']}\t{e['run_id'][:8]}")


if __name__ == "__main__":
  main()
