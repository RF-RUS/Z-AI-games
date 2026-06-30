"""Full pipeline verification with all services running."""
import time

import httpx


def api(method, url, body=None):
    try:
        if method == "POST":
            r = httpx.post(url, json=body, timeout=15)
        else:
            r = httpx.get(url, timeout=8)
        return r.status_code, r.json() if "json" in r.headers.get("content-type","") else r.text[:500]
    except Exception as e:
        return None, str(e)[:200]

# Find UNO
_, candidates = api("GET", "http://127.0.0.1:8105/windows/candidates")
uno = None
for c in candidates:
    if c.get("pid") == 23992:
        uno = c
        break

if not uno:
    print("UNO.exe NOT FOUND")
    exit(1)

# Create session
spec = {"config":{"adapter_type":"windows","adapter_id":"pending","strategy_id":"heuristic","model_assist_enabled":False},"automatic":True,"web_profile_id":"local-mock-uno","windows_profile_id":"real-uno-desktop"}
code, created = api("POST", "http://127.0.0.1:8100/sessions", spec)
sid = created["session_id"]
print(f"Session: {sid[:8]}")

# Attach + Start + Tick
code, _ = api("POST", f"http://127.0.0.1:8100/sessions/{sid}/attach-adapter", {"adapter_type":"windows","profile_id":"real-uno-desktop","window_handle":uno["handle"]})
print(f"Attach: {code}")

code, _ = api("POST", f"http://127.0.0.1:8100/sessions/{sid}/start")
print(f"Start: {code}")

time.sleep(3)
code, ticked = api("POST", f"http://127.0.0.1:8100/sessions/{sid}/tick")
print(f"Tick: {code}")
time.sleep(5)

# Check screenshot
code, screenshot = api("GET", f"http://127.0.0.1:8100/sessions/{sid}/screenshot")
print(f"\nScreenshot: {code}")
if isinstance(screenshot, dict):
    w = screenshot.get("width")
    h = screenshot.get("height")
    b64 = screenshot.get("data_base64", "")
    print(f"  {w}x{h} data_base64={len(b64)} bytes")

# Check status
code, status = api("GET", f"http://127.0.0.1:8100/sessions/{sid}/status")
if isinstance(status, dict):
    snap = status.get("strategy_snapshot") or {}
    error = str(status.get("error", ""))
    
    print("\nStatus:")
    fs = status.get("flow_state", "?")
    ds = snap.get("detected_state", "?")
    conf = snap.get("confidence")
    tc = snap.get("top_card")
    hc = snap.get("hand_cards")
    src = snap.get("source")
    
    print(f"  flow_state: {fs}")
    print(f"  detected_state: {ds}")
    print(f"  confidence: {conf}")
    print(f"  top_card: {tc}")
    print(f"  hand_cards: {hc}")
    print(f"  source: {src}")
    
    if "Game state not extractable" in error:
        print("\n  OLD UIA ERROR STILL PRESENT")
    elif "All connection attempts" in error:
        print("\n  Connection error (perception-service may be down)")
    elif error:
        print(f"\n  error: {error[:150]}")
    else:
        print("\n  NO ERROR")
