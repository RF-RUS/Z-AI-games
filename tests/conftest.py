"""Shared pytest fixtures."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEST_TARGET_PORT = 8765


@pytest.fixture(scope="module")
def web_test_server():
  script = ROOT / "scripts" / "serve-test-target.py"
  proc = subprocess.Popen(
    [sys.executable, str(script), "--port", str(TEST_TARGET_PORT)],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
  )
  time.sleep(0.8)
  yield f"http://127.0.0.1:{TEST_TARGET_PORT}/"
  proc.terminate()
  proc.wait(timeout=5)


@pytest.fixture(scope="module")
def windows_test_app():
  if sys.platform != "win32":
    pytest.skip("Windows-only fixture")
  script = ROOT / "services" / "adapter-windows" / "test-target" / "uno_mock_app.py"
  proc = subprocess.Popen([sys.executable, str(script)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
  time.sleep(2.0)
  yield
  proc.terminate()
  proc.wait(timeout=5)
