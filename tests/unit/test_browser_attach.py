"""Browser attach ambiguity tests."""

from uno_adapter_windows.browser_attach import (
  BROWSER_HOST_WARNING,
  CAPTURE_CONTENT_MISMATCH_WARNING,
  TAB_TITLE_MISMATCH_WARNING,
  browser_candidate_warning,
  is_browser_host,
  title_core,
  verify_browser_attach,
)
from uno_schemas.adapter_windows import UiNodeSnapshot


def test_is_browser_host_detects_chrome():
  assert is_browser_host("chrome.exe", "Chrome_WidgetWin_1")
  assert not is_browser_host("python.exe", "TkTopLevel")


def test_browser_candidate_warning():
  assert browser_candidate_warning("chrome.exe") == BROWSER_HOST_WARNING
  assert browser_candidate_warning("python.exe") is None


def test_title_core_strips_browser_suffix():
  assert title_core("Scuffed Uno | Game - Google Chrome") == "Scuffed Uno | Game"


def test_verify_browser_attach_title_mismatch():
  warning, _ = verify_browser_attach(
    "Scuffed Uno | Game - Google Chrome",
    "UNO Operator - Google Chrome",
    [],
    process_name="chrome.exe",
    class_name="Chrome_WidgetWin_1",
  )
  assert warning == TAB_TITLE_MISMATCH_WARNING


def test_verify_browser_attach_content_mismatch():
  nodes = [
    UiNodeSnapshot(node_id="1", name="UNO Operator", control_type="Document"),
    UiNodeSnapshot(node_id="2", name="Session Control", control_type="Text"),
  ]
  warning, _ = verify_browser_attach(
    "Scuffed Uno | Game - Google Chrome",
    "Scuffed Uno | Game - Google Chrome",
    nodes,
    process_name="chrome.exe",
    class_name="Chrome_WidgetWin_1",
  )
  assert warning == CAPTURE_CONTENT_MISMATCH_WARNING


def test_verify_non_browser_has_no_warning():
  warning, _ = verify_browser_attach(
    "UNO Mock Test Target",
    "UNO Mock Test Target",
    [],
    process_name="python.exe",
  )
  assert warning is None
