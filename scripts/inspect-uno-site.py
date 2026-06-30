#!/usr/bin/env python3
"""Inspect UNO web site DOM for profile selectors."""
import asyncio
import sys


async def main() -> None:
  try:
    from playwright.async_api import async_playwright
  except ImportError:
    print("NO_PLAYWRIGHT")
    sys.exit(1)

  url = sys.argv[1] if len(sys.argv) > 1 else "https://scuffeduno.online/"
  async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page(viewport={"width": 1280, "height": 900})
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)
    clicks = [
      "text=Singleplayer", "text=Single Player", "text=Play Solo", "text=Vs AI",
      "text=Play", "text=Start", "text=2P", "text=Easy",
      "button:has-text('Single')", "button:has-text('Play')",
    ]
    for sel in clicks:
      try:
        loc = page.locator(sel).first
        if await loc.count() > 0 and await loc.is_visible():
          await loc.click(timeout=3000)
          await page.wait_for_timeout(4000)
          print("CLICKED:", sel)
          break
      except Exception:
        pass
    data = await page.evaluate("""() => {
      const out = { selectors: [], texts: [] };
      document.querySelectorAll('[id],[data-testid],[aria-label],[role]').forEach(el => {
        if (el.id) out.selectors.push('#' + el.id);
        if (el.dataset && el.dataset.testid) out.selectors.push('[data-testid="' + el.dataset.testid + '"]');
        if (el.getAttribute('aria-label')) out.selectors.push('[aria-label="' + el.getAttribute('aria-label') + '"]');
        const tag = el.tagName.toLowerCase();
        const cls = (el.className || '').toString().split(/\\s+/).filter(c => c && c.length < 50).slice(0, 2);
        if (cls.length) out.selectors.push(tag + '.' + cls.join('.'));
      });
      document.querySelectorAll('button, [role=button]').forEach(el => {
        const t = (el.textContent || '').trim().slice(0, 40);
        if (t) out.texts.push(t);
      });
      return out;
    }""")
    print("URL:", url)
    print("TITLE:", (await page.title()).encode("ascii", "replace").decode())
    print("---SELECTORS---")
    for s in sorted(set(data["selectors"]))[:80]:
      print(s)
    print("---BUTTONS---")
    for t in sorted(set(data["texts"]))[:30]:
      print(t)
    await browser.close()


if __name__ == "__main__":
  asyncio.run(main())
