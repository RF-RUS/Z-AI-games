"""Regression: evidence capture must never stall the observe loop.

Session 294799aa (adapter 8d5d69f2): a UIA COM call (element.children()/
rectangle()) against the live animating UNO window hung inside the tree walk.
The walk's 4s wall-clock budget is only checked BETWEEN elements, so one stuck
COM call defeated it, and /evidence had no deadline — the orchestrator sat on
an opaque ReadTimeout for ~60s ("observe: ReadTimeout on GET .../evidence").

Three guards:
1. extract_ui_tree hard-caps the whole walk coroutine (UIA_WALK_HARD_TIMEOUT_S)
   and returns an empty sparse tree instead of blocking forever.
2. capture_evidence captures the screenshot FIRST (the primary perception
   input), so a hung walk can no longer gate the frame the agent reads.
3. The /evidence endpoint has its own backstop deadline and returns a
   structured degraded bundle (empty snapshot, no screenshot) instead of an
   opaque ReadTimeout.
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from uno_schemas.adapter_windows import (
    WindowMatcher,
    WindowsAdapterProfile,
)


def _profile() -> WindowsAdapterProfile:
    return WindowsAdapterProfile(
        profile_id="evidence-timeout-test",
        display_name="t",
        window=WindowMatcher(title_regex="X"),
    )


class _HangingWindow:
    """Fake UIA window whose children() blocks like a stuck COM call.

    rectangle() raises so _node_from_element yields no node; the walk then
    enters children() and sleeps past any budget.
    """

    def rectangle(self):
        raise RuntimeError("no rect")

    def children(self):
        time.sleep(1.0)
        return []

    def window_text(self):
        return ""

    def class_name(self):
        return "X"

    def is_enabled(self):
        return True

    def is_visible(self):
        return True


class TestExtractUiTreeHardTimeout:
    @pytest.mark.asyncio
    async def test_hung_com_call_returns_empty_tree_fast(self):
        from uno_adapter_windows import runtime

        with patch.object(runtime, "UIA_WALK_HARD_TIMEOUT_S", 0.2):
            t0 = time.monotonic()
            nodes, truncated, sparse = await runtime.extract_ui_tree(
                _HangingWindow(), "uia"
            )
            elapsed = time.monotonic() - t0

        # Degraded but fast: empty sparse tree, no wait on the hung call.
        assert nodes == []
        assert truncated is True
        assert sparse is True
        assert elapsed < 0.9

    @pytest.mark.asyncio
    async def test_healthy_walk_still_returns_nodes(self):
        from uno_adapter_windows import runtime

        class _Info:
            control_type = "Pane"
            automation_id = None

        class _FastWindow:
            element_info = _Info()

            def rectangle(self):
                class R:
                    left = 0
                    top = 0
                    right = 10
                    bottom = 10
                return R()

            def children(self):
                return [self._child]

            def window_text(self):
                return "Draw Pile: 5"

            def class_name(self):
                return "X"

            def is_enabled(self):
                return True

            def is_visible(self):
                return True

            def __init__(self):
                self._child = _FastLeaf()

        class _FastLeaf:
            element_info = _Info()

            def rectangle(self):
                class R:
                    left = 0
                    top = 0
                    right = 5
                    bottom = 5
                return R()

            def children(self):
                return []

            def window_text(self):
                return "Green 4"

            def class_name(self):
                return "Y"

            def is_enabled(self):
                return True

            def is_visible(self):
                return True

        nodes, truncated, sparse = await runtime.extract_ui_tree(_FastWindow(), "uia")
        assert not truncated
        names = [n.name for n in nodes]
        assert "Draw Pile: 5" in names and "Green 4" in names


class TestCaptureEvidenceScreenshotFirst:
    @pytest.mark.asyncio
    async def test_screenshot_delivered_even_if_walk_hangs(self, tmp_path):
        from PIL import Image

        from uno_adapter_windows import pywinauto_adapter as pwa
        from uno_adapter_windows import runtime
        from uno_adapter_windows.pywinauto_adapter import PywinautoWindowsAdapter

        png = tmp_path / "evidence.png"
        Image.new("RGB", (320, 240), (1, 2, 3)).save(png)

        adapter = PywinautoWindowsAdapter(session_id="t-ev", profile=_profile())
        import shutil

        shutil.rmtree(adapter.artifacts_dir, ignore_errors=True)  # init side effect
        adapter.artifacts_dir = tmp_path  # don't touch the real artifacts dir
        adapter._window = _HangingWindow()
        adapter._executor = None
        adapter.capture_screenshots = True

        with (
            patch.object(runtime, "UIA_WALK_HARD_TIMEOUT_S", 0.2),
            patch.object(
                pwa, "capture_window_screenshot",
                new=AsyncMock(return_value=str(png)),
            ),
        ):
            t0 = time.monotonic()
            bundle = await adapter.capture_evidence("ad1")
            elapsed = time.monotonic() - t0

        # The screenshot — the thing perception actually reads — is present,
        # even though the UIA walk hit its hard cap and came back empty.
        assert bundle.screenshot is not None
        assert bundle.screenshot.path == str(png)
        assert bundle.screenshot.width == 320 and bundle.screenshot.height == 240
        assert bundle.window_snapshot.nodes == []
        assert bundle.window_snapshot.sparse_tree is True
        assert bundle.window_snapshot.truncated is True
        assert elapsed < 0.9


class TestScreenshotMethodBudget:
    """Session 0859f748 + 0f04bb00: capture_as_image (a COM/UIA call) hung
    against the live UNO window. Two defects compounded:

    (a) the methods ran SEQUENTIALLY and the hung COM method sat FIRST, so the
        one stuck call staled the whole capture before the ~50ms GDI method that
        could have captured the frame was even tried -> frameless degraded
        bundle -> 'pcv=MISSING screenshot=NONE'.
    (b) the per-method budgets summed to 22s, OVER the 20s /evidence backstop,
        so a multi-method hang was guaranteed to discard a frame that had
        already been produced.

    The fix: try the reliable pure-GDI/ctypes PrintWindow methods FIRST and keep
    the worst-case budget sum under the backstop. Each method also runs under
    _bounded_call so a single hung method is abandoned and the next still runs."""

    def test_gdi_methods_are_tried_before_com(self):
        """The reliable GDI path must run first so a hung COM call can't delay
        the frame that perception reads. Regression for the 2026-08-28 hang.

        We check the ORDER inside the ``methods = [...]`` list (the execution
        order), not the order of the ``def m_*`` closures above it, which is
        unrelated to which method the loop calls first."""
        import re

        from uno_adapter_windows import runtime

        import inspect

        src = inspect.getsource(runtime.capture_window_screenshot)
        # Isolate the methods = [ ... ] block that drives the capture loop.
        m = re.search(r"methods\s*=\s*\[(.*?)\]", src, re.DOTALL)
        assert m, "capture_window_screenshot must define a methods list"
        block = m.group(1)

        def pos(token: str) -> int:
            i = block.find(token)
            assert i != -1, f"{token} not present in the methods list"
            return i

        # Both GDI/ctypes PrintWindow methods come before both COM methods.
        assert pos("m_printwindow_full") < pos("m_imagegrab")
        assert pos("m_printwindow_full") < pos("m_capture_as_image")
        assert pos("m_printwindow_plain") < pos("m_capture_as_image")

    @pytest.mark.asyncio
    async def test_hung_com_method_does_not_delay_gdi_frame(self, tmp_path):
        """A stuck capture_as_image (COM) must not delay the frame: the GDI
        method is tried first and returns the image, so the whole capture is
        fast even with a hung COM method present."""
        import os

        from PIL import Image

        from uno_adapter_windows import runtime

        class _Hang:
            handle = 1234

            def capture_as_image(self):
                time.sleep(2.0)  # simulates a stuck COM call
                return None

        good = Image.new("RGB", (320, 240), (200, 10, 10))  # red, not black
        with (
            patch.object(runtime, "_PRINTWINDOW_BUDGET_S", 0.2),
            patch.object(runtime, "_SCREENSHOT_COM_BUDGET_S", 0.2),
            patch.object(runtime, "_capture_via_printwindow", return_value=good),
        ):
            t0 = time.monotonic()
            path = await runtime.capture_window_screenshot(_Hang(), tmp_path, "t")
            elapsed = time.monotonic() - t0

        assert path is not None and os.path.exists(path)
        # The GDI method returned immediately; the hung COM method was never
        # awaited to completion.
        assert elapsed < 0.5

    @pytest.mark.asyncio
    async def test_all_methods_hung_returns_none_bounded(self, tmp_path):
        from uno_adapter_windows import runtime

        class _Hang:
            handle = 1234

            def capture_as_image(self):
                time.sleep(2.0)

            def rectangle(self):
                time.sleep(2.0)

        def _hung_printwindow(hwnd, flag):
            time.sleep(2.0)
            return None

        with (
            patch.object(runtime, "_PRINTWINDOW_BUDGET_S", 0.2),
            patch.object(runtime, "_SCREENSHOT_COM_BUDGET_S", 0.2),
            patch.object(runtime, "_capture_via_printwindow", side_effect=_hung_printwindow),
        ):
            t0 = time.monotonic()
            path = await runtime.capture_window_screenshot(_Hang(), tmp_path, "t")
            elapsed = time.monotonic() - t0

        assert path is None
        # Four abandoned methods, each capped at the per-method budget: the
        # frameless result arrives bounded (~0.8s), not after the hung calls.
        # The sum of all four live budgets (3+3+2+2 = 10s) must also stay under
        # the 20s /evidence backstop — a hung multi-method capture can never be
        # guaranteed to discard a frame that was already produced.
        assert elapsed < 1.5
        assert (
            runtime._PRINTWINDOW_BUDGET_S * 2 + runtime._SCREENSHOT_COM_BUDGET_S * 2
        ) < 20.0


class TestEvidenceEndpointBackstop:
    @pytest.mark.asyncio
    async def test_hung_capture_returns_degraded_bundle_fast(self):
        from uno_adapter_windows import api

        async def _hang(*a, **k):
            await asyncio.sleep(1.0)
            raise AssertionError("must not be reached after the deadline")

        fake = MagicMock()
        fake.backend = "uia"
        fake.profile_id = None
        fake.session_id = "s1"
        fake.capture_evidence = AsyncMock(side_effect=_hang)

        with (
            patch.object(api, "_EVIDENCE_DEADLINE_S", 0.2),
            patch.object(api, "get_adapter", return_value=fake),
        ):
            t0 = time.monotonic()
            bundle = await api.get_evidence("ad1", correlation_id="c1")
            elapsed = time.monotonic() - t0

        assert elapsed < 0.9
        assert bundle.screenshot is None
        assert bundle.window_snapshot.extracted == {}
        assert bundle.window_snapshot.truncated is True
        assert bundle.correlation_id == "c1"
        assert bundle.session_id == "s1"

    @pytest.mark.asyncio
    async def test_successful_capture_passes_through(self):
        from uno_adapter_windows import api

        real_bundle = MagicMock()
        real_bundle.correlation_id = None
        fake = MagicMock()
        fake.capture_evidence = AsyncMock(return_value=real_bundle)

        with patch.object(api, "get_adapter", return_value=fake):
            out = await api.get_evidence("ad1", correlation_id="c2")

        assert out is real_bundle
        assert real_bundle.correlation_id == "c2"
        fake.capture_evidence.assert_awaited_once_with("ad1")


class TestNoSyncComInEventLoop:
    """Session a4ab6f11 (adapter 32b50e89): the evidence path made SYNCHRONOUS
    pywinauto COM calls directly in the event loop:

    * visual_executor._apply_fixed_size -> window_bounds(window) [COM
      window.rectangle() fallback] — and it ran BEFORE the screenshot;
    * pywinauto_adapter._snapshot -> window.window_text()/class_name().

    A single stuck COM call against the live animating UNO (Electron) window
    blocks the WHOLE loop. The /evidence 20s backstop is an asyncio.wait_for on
    that same loop, so it can never fire — the orchestrator observes an opaque
    ReadTimeout and the agent gets no frame. Regression: every COM call on the
    evidence path must now run in a thread with a hard budget.
    """

    def test_read_window_bounds_uses_ctypes_before_com(self):
        """Pure-ctypes GetWindowRect must be attempted before the COM
        window.rectangle() fallback — a ctypes win means zero COM on the path.
        (Compare the actual CALL sites, not the comments.)"""
        import inspect
        import re

        from uno_adapter_windows.rpa.driver import window_driver

        src = inspect.getsource(window_driver.read_window_bounds)
        # Strip comments: they mention both calls and would confuse a naive
        # position check.
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
        ctypes_call = re.search(r"=\s*win32_bounds_for_handle\(", code)
        com_call = re.search(r"window\.rectangle\(\)", code)
        assert ctypes_call, "GetWindowRect (ctypes) call must be present"
        assert com_call, "COM rectangle() fallback must still be present"
        assert ctypes_call.start() < com_call.start(), (
            "GetWindowRect (ctypes) must be tried before the COM rectangle()"
        )

    @pytest.mark.asyncio
    async def test_apply_fixed_size_hung_bounds_does_not_stall(self, tmp_path):
        """A hung COM bounds read in _apply_fixed_size must be abandoned after
        the budget, not block the coroutine (and hence the 20s backstop)."""
        from uno_adapter_windows import runtime
        from uno_adapter_windows.rpa.driver import window_driver as wd
        from uno_adapter_windows.rpa.executor.visual_executor import (
            VisualRpaExecutor,
        )
        from uno_adapter_windows.rpa.session_state import RpaSessionState

        profile = _profile()
        profile.window.fixed_size = {"width": 1296, "height": 759}

        class _HungBoundsWindow:
            handle = 1234

            def rectangle(self):
                time.sleep(2.0)  # stuck COM call

        ex = VisualRpaExecutor(
            _HungBoundsWindow(), profile, "uia", tmp_path,
            RpaSessionState("ad1", "s1"), "s1", bounds={"left": 0, "top": 0, "right": 1, "bottom": 1},
        )
        from uno_adapter_windows.rpa.executor import visual_executor as vx
        with (
            patch.object(wd, "assert_window_size", return_value=None),
            # Kill the fast ctypes path so the COM fallback (the thing that
            # hangs) is actually exercised.
            patch.object(wd, "win32_bounds_for_handle", return_value=None),
            patch.object(vx, "_WINDOW_BOUNDS_BUDGET_S", 0.2),
        ):
            t0 = time.monotonic()
            await ex._apply_fixed_size()
            elapsed = time.monotonic() - t0

        assert elapsed < 0.9, "a stuck bounds read must be abandoned at the budget"

    @pytest.mark.asyncio
    async def test_snapshot_meta_hung_com_does_not_block_loop(self, tmp_path):
        """window_text/class_name in _snapshot must run off the loop with a
        budget; a hang degrades to the fallback title, not a stalled capture."""
        import uno_adapter_windows.pywinauto_adapter as pa
        from uno_adapter_windows import runtime

        assert pa._WINDOW_META_BUDGET_S <= 5.0

        class _HungMetaWindow:
            handle = 1234

            def window_text(self):
                time.sleep(2.0)  # stuck COM call

            def class_name(self):
                time.sleep(2.0)

            def rectangle(self):
                raise RuntimeError("no rect")

            def children(self):
                return []

        # __new__ bypasses the heavy __init__ (mkdir / launch); set only what
        # _snapshot reads.
        adapter = pa.PywinautoWindowsAdapter.__new__(pa.PywinautoWindowsAdapter)
        adapter._window = _HungMetaWindow()
        adapter._backend = "uia"
        adapter.window_title_hint = "UNO"
        adapter.profile = _profile()

        async def _no_tree(window, backend):
            return [], True, True

        with (
            patch.object(pa, "extract_ui_tree", _no_tree),
            patch.object(pa, "_WINDOW_META_BUDGET_S", 0.2),
        ):
            t0 = time.monotonic()
            snap = await adapter._snapshot()
            elapsed = time.monotonic() - t0

        assert elapsed < 0.9
        assert snap.window_title == "UNO"  # fallback, not the hung COM value


class TestWebOnlySkipsUia:
    """Session 47b8b2a6 (2026-08-29): match_automation="web_only" desktop
    profile (real UNO Electron client). Two leaks:

    * the UIA tree walk HUNG on every observe cycle (ui_tree_walk_timeout
      flood), leaked worker threads into the walk pool, and the evidence
      capture then exceeded its 20s backstop (degraded bundle, no frame);
    * a play_card that missed CV-grounding fell into the same doomed walk on
      the execute path and blew the 12s deadline ("execution exceeded 12s
      deadline" — no click delivered). The old should_skip_uia_card_lookup
      check only applied to BROWSER hosts, so desktop web_only never skipped.

    Regression: with match_automation="web_only" the walk must be skipped on
    BOTH paths — it can never contain canvas-drawn cards.
    """

    def _web_only_profile(self) -> WindowsAdapterProfile:
        p = _profile()
        p.match_automation = "web_only"
        return p

    @pytest.mark.asyncio
    async def test_snapshot_skips_uia_walk(self):
        """_snapshot on a web_only profile must not call extract_ui_tree."""
        import uno_adapter_windows.pywinauto_adapter as pa

        class _Window:
            handle = 1

            def window_text(self):
                return "UNO"

            def class_name(self):
                return "X"

        adapter = pa.PywinautoWindowsAdapter.__new__(pa.PywinautoWindowsAdapter)
        adapter._window = _Window()
        adapter._backend = "uia"
        adapter.window_title_hint = "UNO"
        adapter.profile = self._web_only_profile()

        walked = []

        async def _explode(window, backend):
            walked.append(1)
            return [], False, False

        with patch.object(pa, "extract_ui_tree", _explode):
            await adapter._snapshot()

        assert walked == [], "web_only profile must not walk the UIA tree in _snapshot"

    @pytest.mark.asyncio
    async def test_execute_skips_uia_walk(self):
        """_execute_visual on a web_only profile must not walk the tree — a
        missed CV-grounding turns into a fast structured refusal, not a
        6s+ doomed walk that eats the 12s execute deadline."""
        from uno_adapter_windows.rpa.executor import visual_executor as vx
        from uno_adapter_windows.rpa.session_state import RpaSessionState
        from uno_schemas.adapter_windows import VisualActionRequest
        from uno_adapter_windows.rpa.executor.visual_executor import VisualRpaExecutor

        class _BareWindow:
            handle = 1

        ex = VisualRpaExecutor(
            _BareWindow(), self._web_only_profile(), "uia", None,
            RpaSessionState("ad1", "s1"), "s1",
            bounds={"left": 0, "top": 0, "right": 100, "bottom": 100},
        )
        walked = []

        async def _explode(window, backend):
            walked.append(1)
            return [], False, False

        req = VisualActionRequest(
            domain_action="play_card", selector_key="play_red_five",
            capture_screenshots=False,
        )
        with patch.object(vx, "extract_ui_tree", _explode):
            t0 = time.monotonic()
            result = await ex._execute_visual("act-1", req)
            elapsed = time.monotonic() - t0

        assert walked == [], "web_only profile must not walk the UIA tree on execute"
        assert result.success is False and result.uncertain, (
            "a missed CV-grounding on web_only must refuse fast, not walk"
        )
        assert elapsed < 1.0

    @pytest.mark.asyncio
    async def test_ensure_focus_hung_com_bounded(self):
        """window.set_focus() is a COM call without its own timeout — on the
        animating UNO window it hung long enough to consume the whole 12s
        execute deadline. A hang must be abandoned at the budget instead."""
        from uno_adapter_windows.rpa.driver import window_driver as wd

        class _FocusHungWindow:
            def set_focus(self):
                time.sleep(2.0)  # stuck COM call

        with patch.object(wd, "_FOCUS_BUDGET_S", 0.2):
            t0 = time.monotonic()
            await wd.ensure_focus(_FocusHungWindow())
            elapsed = time.monotonic() - t0
        assert elapsed < 0.9, "hung set_focus must be bounded by the budget"
