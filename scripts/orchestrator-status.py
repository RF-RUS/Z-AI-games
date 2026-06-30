#!/usr/bin/env python3
"""Print orchestrator session status."""

import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8100"


def main() -> None:
  sid = sys.argv[1] if len(sys.argv) > 1 else None
  if sid:
    for path in (f"/sessions/{sid}/status", f"/sessions/{sid}/steps"):
      r = urllib.request.urlopen(f"{BASE}{path}")
      print(json.dumps(json.loads(r.read()), indent=2))
  else:
    r = urllib.request.urlopen(f"{BASE}/sessions")
    print(json.dumps(json.loads(r.read()), indent=2))


if __name__ == "__main__":
  main()
