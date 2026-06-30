"""End-to-end trace for web attach diagnostics on one fresh session."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
ORCH = "http://127.0.0.1:8100"
WEB = "http://127.0.0.1:8104"


def pp(title: str, data: object) -> None:
  print(f"\n=== {title} ===")
  print(json.dumps(data, indent=2, ensure_ascii=False)[:8000])


async def main() -> int:
  async with httpx.AsyncClient(timeout=130.0) as client:
    # Create session
    create_r = await client.post(
      f"{ORCH}/sessions",
      json={
        "config": {
          "adapter_type": "web",
          "adapter_id": "pending",
          "strategy_id": "heuristic",
          "model_assist_enabled": False,
        },
        "automatic": False,
        "web_profile_id": "scuffed-uno-web",
        "windows_profile_id": "scuffed-uno-web",
      },
    )
    create_r.raise_for_status()
    session = create_r.json()
    sid = session["session_id"]
    pp("CREATE /sessions", session)

    # Direct adapter-web attach (checkpoint source)
    attach_body = {
      "session_id": sid,
      "profile_id": "scuffed-uno-web",
      "mode": "playwright",
      "record_trace": True,
    }
    web_r = await client.post(f"{WEB}/attach", json=attach_body)
    pp(
      "1) adapter-web /attach raw",
      {
        "status_code": web_r.status_code,
        "headers": dict(web_r.headers),
        "body": web_r.text[:4000],
      },
    )
    web_json = None
    try:
      web_json = web_r.json()
    except Exception as exc:
      pp("1b) adapter-web body JSON parse error", {"error": str(exc)})

    # Orchestrator attach (live path)
    orch_attach_r = await client.post(
      f"{ORCH}/sessions/{sid}/attach-adapter",
      json={"adapter_type": "web", "profile_id": "scuffed-uno-web"},
    )
    pp(
      "orchestrator attach-adapter",
      {
        "status_code": orch_attach_r.status_code,
        "body": orch_attach_r.text[:2000],
      },
    )

    list_r = await client.get(f"{ORCH}/sessions")
    list_r.raise_for_status()
    listed = next((s for s in list_r.json() if s["session_id"] == sid), None)
    pp("3) GET /sessions (listed entry)", listed)

    detail_r = await client.get(f"{ORCH}/sessions/{sid}")
    pp("3b) GET /sessions/{id}", detail_r.json() if detail_r.status_code == 200 else detail_r.text)

    status_r = await client.get(f"{ORCH}/sessions/{sid}/status")
    pp("4) GET /status", status_r.json() if status_r.status_code == 200 else status_r.text)

    # Simulate UI mergeSession
    base = listed or {}
    status = status_r.json() if status_r.status_code == 200 else {}
    merged_diagnostics = status.get("attach_startup_diagnostics") or base.get("attach_startup_diagnostics")
    ui_debug = {
      "error": status.get("error") or base.get("error"),
      "attach_startup_diagnostics": merged_diagnostics,
      "last_recovery": status.get("last_recovery"),
    }
    pp("5) UI debug panel object (mergeSession simulation)", ui_debug)

    print("\n=== SUMMARY ===")
    print(f"session_id={sid}")
    print(f"adapter-web has startup_diagnostics={bool(web_json and web_json.get('startup_diagnostics'))}")
    print(f"list has attach_startup_diagnostics={listed.get('attach_startup_diagnostics') is not None if listed else 'missing'}")
    print(f"status has attach_startup_diagnostics={status.get('attach_startup_diagnostics') is not None if status else 'missing'}")
    print(f"ui merged diagnostics null={merged_diagnostics is None}")
    return 0


if __name__ == "__main__":
  raise SystemExit(asyncio.run(main()))
