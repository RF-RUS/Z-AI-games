"""Quick smoke test for the calibration endpoint."""
from fastapi.testclient import TestClient
from uno_adapter_windows.api import app
from uno_schemas.adapter_windows import AttachWindowsAdapterRequest, WindowsAdapterMode
import subprocess, time

subprocess.run(["powershell", "-NoProfile", "-Command",
    "Get-Process python -ErrorAction SilentlyContinue | "
    "Where-Object { $_.MainWindowTitle -like '*UNO Mock*' } | Stop-Process -Force"],
    check=False)
time.sleep(0.5)

client = TestClient(app)
resp = client.post("/attach", json=AttachWindowsAdapterRequest(
    session_id="cal-smoke", mode=WindowsAdapterMode.PYWINAUTO,
    profile_id="local-mock-uno", launch_test_target=True,
).model_dump(mode="json"))
data = resp.json()
aid = data.get("adapter_id")
if not aid or not data.get("attached"):
    print(f"Attach failed: {data}")
else:
    cal = client.get(f"/adapters/{aid}/calibration").json()
    print(f"Window bounds: {cal.get('window_bounds')}")
    print(f"Client bounds: {cal.get('client_bounds')}")
    print(f"Offset:        {cal.get('offset')}")
    print(f"Coord space:   {cal.get('coordinate_space')}")
    assert cal.get("window_bounds"), "window_bounds should be present"
    client.post(f"/adapters/{aid}/detach")
    print("PASS")
