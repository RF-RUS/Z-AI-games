"""Lightweight screenshot trace manager for agent pipeline debugging.

Feature-flagged via environment variables:
  AGENT_SCREENSHOT_TRACE=1          — enable tracing
  AGENT_SCREENSHOT_TRACE_DIR=...    — custom trace directory (default: artifacts/agent_trace)

Saves frame.png + meta.json at observe, perceive, execute (before/after).
All trace operations are best-effort: never crash the agent loop.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_trace_logger = logging.getLogger("trace")


class TraceManager:
    _enabled: bool | None = None
    _base_dir: Path | None = None

    @classmethod
    def enabled(cls) -> bool:
        val = os.environ.get("AGENT_SCREENSHOT_TRACE", "0")
        result = val == "1"
        if not result and val != "0":
            _trace_logger.warning("AGENT_SCREENSHOT_TRACE has unexpected value=%r, treating as disabled", val)
        return result

    @classmethod
    def base_dir(cls) -> Path:
        if cls._base_dir is None:
            raw = os.environ.get("AGENT_SCREENSHOT_TRACE_DIR", "")
            if raw:
                cls._base_dir = Path(raw)
            else:
                cls._base_dir = Path("artifacts") / "agent_trace"
        return cls._base_dir

    @classmethod
    def reset(cls):
        cls._enabled = None
        cls._base_dir = None

    @classmethod
    def step_dir(cls, session_id: str, step_counter: int, phase: str) -> Path | None:
        if not cls.enabled():
            return None
        d = cls.base_dir() / session_id / f"{step_counter:03d}_{phase}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @classmethod
    def capture_viewport(cls, page, dest: Path, name: str = "frame.png") -> Path | None:
        """Capture viewport screenshot. Returns path or None on failure."""
        try:
            path = dest / name
            # Synchronous run in async context — caller must handle
            return path
        except Exception:
            return None

    @classmethod
    def write_meta(cls, dest: Path, data: dict) -> None:
        try:
            path = dest / "meta.json"
            content = json.dumps(data, indent=2, default=str, ensure_ascii=False)
            path.write_text(content, encoding="utf-8")
            _trace_logger.info("write_meta_ok path=%s size=%d", path, len(content))
        except Exception as e:
            _trace_logger.exception("write_meta_failed dest=%s error=%s", dest, e)

    @classmethod
    def _now_iso(cls) -> str:
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + f"{datetime.now(UTC).microsecond // 1000:03d}Z"

    @classmethod
    async def capture_observe(cls, session_id: str, step: int, page, screenshot_bytes: bytes,
                               extracted: dict, grounding: Any = None) -> None:
        """Trace observe phase: save the exact screenshot used for CV."""
        _trace_logger.info(
            "trace_observe_entered session=%s step=%d enabled=%s base_dir=%s pid=%d",
            session_id, step, cls.enabled(), cls.base_dir(), os.getpid(),
        )
        if not cls.enabled():
            _trace_logger.warning(
                "trace_observe_skipped session=%s reason=AGENT_SCREENSHOT_TRACE disabled env=%s",
                session_id, os.environ.get("AGENT_SCREENSHOT_TRACE", "NOT_SET"),
            )
            return
        try:
            dest = cls.step_dir(session_id, step, "observe")
            if not dest:
                _trace_logger.warning("trace_observe_no_dest session=%s step=%d", session_id, step)
                return

            (dest / "frame.png").write_bytes(screenshot_bytes)
            _trace_logger.info("trace_observe_frame_written path=%s size=%d", dest / "frame.png", len(screenshot_bytes))

            meta = {
                "timestamp": cls._now_iso(),
                "session_id": session_id,
                "step_counter": step,
                "phase": "observe",
            }
            if page:
                meta["url"] = page.url or ""
                try:
                    meta["title"] = await page.title()
                except Exception:
                    meta["title"] = ""
                try:
                    vp = await page.evaluate("() => ({w: window.innerWidth, h: window.innerHeight})")
                    meta["viewport"] = {"width": vp["w"], "height": vp["h"]}
                except Exception:
                    meta["viewport"] = {}
                try:
                    meta["dpr"] = float(await page.evaluate("() => window.devicePixelRatio || 1"))
                except Exception:
                    meta["dpr"] = 1.0

            meta["screen"] = extracted.get("screen_state")
            if grounding:
                meta["cv"] = {
                    "hand_cards": len(grounding.hand) if grounding else 0,
                    "draw_pile": grounding.draw_pile is not None,
                    "top_card": extracted.get("top_card") is not None,
                    "detection_confidence": grounding.detection_confidence if grounding else 0.0,
                }

            cls.write_meta(dest, meta)
            _trace_logger.info("trace_observe_meta_written path=%s", dest / "meta.json")

        except Exception:
            _trace_logger.exception("trace_observe_failed session=%s step=%d", session_id, step)

    @classmethod
    async def capture_perceive(cls, session_id: str, step: int, observation: Any,
                                grounding: Any = None) -> None:
        """Trace perceive phase: save observation metadata."""
        if not cls.enabled():
            return
        try:
            dest = cls.step_dir(session_id, step, "perceive")
            if not dest:
                return

            meta = {
                "timestamp": cls._now_iso(),
                "session_id": session_id,
                "step_counter": step,
                "phase": "perceive",
            }

            if observation:
                conf = getattr(observation, "confidence", None)
                if conf:
                    meta["confidence"] = {
                        "overall": getattr(conf, "overall", 0.0),
                        "game_state": getattr(conf, "game_state", 0.0),
                        "game_elements": getattr(conf, "game_elements", 0.0),
                    }
                meta["game_state"] = observation.game_state is not None
                meta["game_elements_count"] = len(observation.game_elements) if observation.game_elements else 0
                meta["game_type"] = observation.game_type
                meta["visible_chat_count"] = len(observation.visible_chat) if observation.visible_chat else 0

            if grounding:
                meta["cv"] = {
                    "hand_cards": len(grounding.hand),
                    "draw_pile": grounding.draw_pile is not None,
                    "detection_confidence": grounding.detection_confidence,
                }

            cls.write_meta(dest, meta)

        except Exception as trace_exc:
            try:
                import logging
                logging.getLogger("trace").warning("trace_perceive_failed error=%s", str(trace_exc))
            except Exception:
                pass

    @classmethod
    async def capture_execute_before(cls, session_id: str, step: int, page,
                                      action_type: str, selector_key: str,
                                      click_point: dict | None, dpr: float,
                                      resolution_tier: str, grounding: Any = None) -> None:
        """Trace execute phase: save before screenshot and action metadata."""
        if not cls.enabled():
            return
        try:
            dest = cls.step_dir(session_id, step, "execute")
            if not dest:
                return

            # Before screenshot
            if page:
                await page.screenshot(path=str(dest / "before.png"), full_page=False)

            meta = {
                "timestamp": cls._now_iso(),
                "session_id": session_id,
                "step_counter": step,
                "phase": "execute_before",
                "action_type": action_type,
                "selector_key": selector_key,
                "resolution_tier": resolution_tier,
                "dpr": dpr,
                "css_coords": click_point,
                "url": page.url if page else "",
            }
            if page:
                try:
                    meta["title"] = await page.title()
                except Exception:
                    meta["title"] = ""

            if grounding and click_point:
                # Find raw CV coords for this action
                slot_index = None
                if selector_key and selector_key.startswith("hand_slot_"):
                    try:
                        slot_index = int(selector_key.split("_")[-1])
                    except ValueError:
                        pass
                if slot_index is not None and grounding.hand:
                    for card in grounding.hand:
                        if card.slot_index == slot_index:
                            meta["raw_cv_coords"] = {"x": card.click_x, "y": card.click_y}
                            meta["cv_matched_by"] = "identity"
                            break
                elif selector_key == "draw" and grounding.draw_pile_click:
                    meta["raw_cv_coords"] = {"x": grounding.draw_pile_click[0], "y": grounding.draw_pile_click[1]}

            cls.write_meta(dest, meta)

        except Exception as trace_exc:
            try:
                import logging
                logging.getLogger("trace").warning("trace_execute_before_failed error=%s", str(trace_exc))
            except Exception:
                pass

    @classmethod
    async def capture_execute_after(cls, session_id: str, step: int, page,
                                     action_type: str, success: bool,
                                     error: str | None = None,
                                     grounding_before: Any = None,
                                     grounding_after: Any = None) -> None:
        """Trace execute phase: save after screenshot with stabilization delay."""
        if not cls.enabled():
            return
        try:
            dest = cls.step_dir(session_id, step, "execute")
            if not dest:
                return

            import asyncio as _aio
            await _aio.sleep(0.2)  # stabilization delay for visual changes

            if page:
                await page.screenshot(path=str(dest / "after.png"), full_page=False)

            meta = {
                "timestamp": cls._now_iso(),
                "session_id": session_id,
                "step_counter": step,
                "phase": "execute_after",
                "action_type": action_type,
                "success": success,
                "error": error,
            }

            before_count = len(grounding_before.hand) if grounding_before else 0
            after_count = len(grounding_after.hand) if grounding_after else 0
            meta["hand_count_before"] = before_count
            meta["hand_count_after"] = after_count
            meta["hand_count_changed"] = before_count != after_count

            if grounding_after:
                meta["cv_after"] = {
                    "hand_cards": len(grounding_after.hand),
                    "draw_pile": grounding_after.draw_pile is not None,
                    "detection_confidence": grounding_after.detection_confidence,
                }

            cls.write_meta(dest, meta)

        except Exception as trace_exc:
            try:
                import logging
                logging.getLogger("trace").warning("trace_execute_after_failed error=%s", str(trace_exc))
            except Exception:
                pass
