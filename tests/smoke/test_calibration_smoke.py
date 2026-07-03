"""Quick smoke test for the calibration endpoint."""
import sys

import pytest
from fastapi.testclient import TestClient
from uno_adapter_windows.api import app
from uno_schemas.adapter_windows import AttachWindowsAdapterRequest, WindowsAdapterMode

pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Calibration smoke requires Windows (pywinauto + powershell)",
)


def test_calibration_endpoint():
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
    assert aid and data.get("attached"), f"Attach failed: {data}"

    cal = client.get(f"/adapters/{aid}/calibration").json()
    assert cal.get("window_bounds"), "window_bounds should be present"
    client.post(f"/adapters/{aid}/detach")
