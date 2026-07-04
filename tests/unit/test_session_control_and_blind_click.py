"""Regression tests for operator-reported bugs:

1. Pause must HOLD — the autonomous loop must stop ticking when flow_state is
   PAUSED (previously it force-reset PAUSED back to ACTIVE and kept acting).
2. Preview-only windows profiles (match_automation="web_only") must NOT fall
   back to blind static layout_target clicks — this caused the mouse to return
   to the same fixed point every tick without ever hitting a real card.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from uno_adapter_windows.rpa.perception.target_locator import (
  ResolutionTrace,
  locate_selector,
)
from uno_orchestrator.orchestrator import SessionOrchestrator
from uno_schemas.adapter_windows import WindowMatcher, WindowsAdapterProfile
from uno_schemas.orchestrator import FlowState


class TestPauseHolds:
  @pytest.mark.asyncio
  async def test_loop_breaks_when_paused(self):
    session = MagicMock()
    session.detail.flow_state = FlowState.PAUSED
    session.detail.automatic = True
    session.detail.session_id = "s"

    orch = MagicMock(spec=SessionOrchestrator)
    orch._flow = MagicMock()
    orch._flow.run_cycle = AsyncMock(return_value={"correlation_id": "x"})
    orch._bus = MagicMock()
    orch._bus.publish = AsyncMock()

    await asyncio.wait_for(SessionOrchestrator._run_loop(orch, session), timeout=2.0)

    # Paused loop must exit without running any cycle, and must NOT resurrect
    # the state to ACTIVE.
    orch._flow.run_cycle.assert_not_awaited()
    assert session.detail.flow_state == FlowState.PAUSED


def _web_only_profile() -> WindowsAdapterProfile:
  return WindowsAdapterProfile(
    profile_id="real-uno-desktop",
    display_name="preview",
    window=WindowMatcher(title_regex="UNO"),
    layout_targets={"play_button": {"x_ratio": 0.56, "y_ratio": 0.34, "label": "Play"}},
    action_mappings={"play_red_five": "Play Red 5"},
    match_automation="web_only",
  )


def _desktop_profile() -> WindowsAdapterProfile:
  return WindowsAdapterProfile(
    profile_id="desktop",
    display_name="desktop",
    window=WindowMatcher(title_regex="UNO"),
    layout_targets={"play_button": {"x_ratio": 0.56, "y_ratio": 0.34, "label": "Play"}},
    action_mappings={"play_red_five": "Play Red 5"},
    match_automation=None,
  )


class TestNoBlindLayoutClickForWebOnly:
  bounds = {"left": 0, "top": 0, "right": 1000, "bottom": 800}

  def test_web_only_suppresses_layout_fallback(self):
    trace = ResolutionTrace()
    target = locate_selector(
      "play_red_five", _web_only_profile(), nodes=[],
      window_bounds=self.bounds, trace=trace,
    )
    assert target is None  # no blind click
    assert trace.source == "none"
    assert "web_only" in trace.error

  def test_normal_desktop_profile_still_uses_layout_fallback(self):
    trace = ResolutionTrace()
    target = locate_selector(
      "play_red_five", _desktop_profile(), nodes=[],
      window_bounds=self.bounds, trace=trace,
    )
    assert target is not None  # cold-start fallback preserved
    assert trace.source == "layout_targets"
