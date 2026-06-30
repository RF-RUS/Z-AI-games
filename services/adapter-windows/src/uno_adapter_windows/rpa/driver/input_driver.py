"""Humanized mouse/keyboard input within window bounds."""

from __future__ import annotations

import asyncio
import time

from uno_adapter_windows.rpa.driver.window_driver import clamp_point_to_bounds


async def humanized_move_and_click(x: float, y: float, bounds: dict[str, float] | None) -> tuple[int, int]:
  cx, cy = clamp_point_to_bounds(x, y, bounds)

  def _act() -> tuple[int, int]:
    from pywinauto import mouse

    try:
      pos = mouse.get_position()
      sx, sy = pos[0], pos[1]
    except Exception:
      sx, sy = cx, cy

    steps = 12
    for i in range(1, steps + 1):
      t = i / steps
      px = int(sx + (cx - sx) * t)
      py = int(sy + (cy - sy) * t)
      mouse.move(coords=(px, py))
      time.sleep(0.012)
    time.sleep(0.05)
    mouse.click(button="left", coords=(cx, cy))
    return cx, cy

  return await asyncio.to_thread(_act)


async def type_text(text: str) -> None:
  def _type():
    from pywinauto import keyboard
    keyboard.send_keys(text, with_spaces=True, pause=0.02)

  await asyncio.to_thread(_type)


async def press_keys(keys: str) -> None:
  def _press():
    from pywinauto import keyboard
    keyboard.send_keys(keys, pause=0.02)

  await asyncio.to_thread(_press)
