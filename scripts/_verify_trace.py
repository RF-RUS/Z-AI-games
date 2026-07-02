import sys
import time
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8")

print("=== 1. TRACE DEBUG ===")
r = httpx.get("http://127.0.0.1:8104/trace/debug", timeout=3)
for k, v in r.json().items():
    print(f"  {k}: {v}")

print("\n=== 2. TRACE SESSIONS ===")
r2 = httpx.get("http://127.0.0.1:8104/trace/sessions", timeout=3)
for s in r2.json():
    print(f"  {s['session_id'][:12]}: {s['step_count']} steps")

print("\n=== 3. NEW SESSION ===")
r3 = httpx.post("http://127.0.0.1:8100/sessions", json={
    "config": {"adapter_type": "mock", "adapter_id": "pending"},
    "automatic": True, "web_profile_id": "local-mock-uno", "windows_profile_id": "local-mock-uno",
})
sid = r3.json()["session_id"]
print("  session_id:", sid)
httpx.post(f"http://127.0.0.1:8100/sessions/{sid}/attach-adapter", json={"adapter_type": "mock"}, timeout=120)
httpx.post(f"http://127.0.0.1:8100/sessions/{sid}/start", timeout=10)
time.sleep(3)

print("\n=== 4. TRACE FOR NEW SESSION ===")
r4 = httpx.get(f"http://127.0.0.1:8104/trace/{sid}/steps", timeout=3)
steps = r4.json()
print("  steps:", len(steps))
for st in steps[:5]:
    meta = st.get("meta") or {}
    print(f"  #{st['step']} {st['phase']}: screen={meta.get('screen', '?')}")

print("\n=== 5. VERIFY ON DISK ===")
base = Path("artifacts/agent_trace")
if base.exists():
    for d in sorted(base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if d.is_dir():
            mtime = time.strftime("%H:%M", time.localtime(d.stat().st_mtime))
            steps = [s.name for s in d.iterdir() if s.is_dir()]
            print(f"  {d.name[:12]} ({mtime}): {len(steps)} steps")
