import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
import httpx

print("=== 1. TRACE DEBUG ===")
r = httpx.get("http://127.0.0.1:8104/trace/debug", timeout=3)
for k, v in r.json().items():
    print("  %s: %s" % (k, v))

print("\n=== 2. TRACE SESSIONS ===")
r2 = httpx.get("http://127.0.0.1:8104/trace/sessions", timeout=3)
for s in r2.json():
    print("  %s: %d steps" % (s["session_id"][:12], s["step_count"]))

print("\n=== 3. NEW SESSION ===")
r3 = httpx.post("http://127.0.0.1:8100/sessions", json={
    "config": {"adapter_type": "mock", "adapter_id": "pending"},
    "automatic": True, "web_profile_id": "local-mock-uno", "windows_profile_id": "local-mock-uno",
})
sid = r3.json()["session_id"]
print("  session_id:", sid)
httpx.post("http://127.0.0.1:8100/sessions/%s/attach-adapter" % sid, json={"adapter_type": "mock"}, timeout=120)
httpx.post("http://127.0.0.1:8100/sessions/%s/start" % sid, timeout=10)
time.sleep(3)

print("\n=== 4. TRACE FOR NEW SESSION ===")
r4 = httpx.get("http://127.0.0.1:8104/trace/%s/steps" % sid, timeout=3)
steps = r4.json()
print("  steps:", len(steps))
for st in steps[:5]:
    meta = st.get("meta") or {}
    print("  #%d %s: screen=%s" % (st["step"], st["phase"], meta.get("screen", "?")))

print("\n=== 5. VERIFY ON DISK ===")
from pathlib import Path

base = Path("artifacts/agent_trace")
if base.exists():
    for d in sorted(base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if d.is_dir():
            import time as t
            mtime = t.strftime("%H:%M", t.localtime(d.stat().st_mtime))
            steps = [s.name for s in d.iterdir() if s.is_dir()]
            print("  %s (%s): %d steps" % (d.name[:12], mtime, len(steps)))
