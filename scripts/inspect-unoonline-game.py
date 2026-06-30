#!/usr/bin/env python3
import asyncio


async def main() -> None:
  from playwright.async_api import async_playwright

  async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page(viewport={"width": 1280, "height": 900})
    await page.goto("https://unoonline.io/", timeout=30000)
    await page.wait_for_timeout(2000)
    await page.locator("button.btn_play").first.click(timeout=5000)
    await page.wait_for_timeout(2000)
    # close ad overlay
    for sel in ["#btn_close", "text=Close", "text=Continue"]:
      try:
        if await page.locator(sel).count() > 0:
          await page.locator(sel).first.click(timeout=2000)
          await page.wait_for_timeout(1000)
      except Exception:
        pass
    await page.wait_for_timeout(8000)
    els = await page.evaluate("""() => {
      return Array.from(document.querySelectorAll('*')).filter(el => {
        const t = (el.textContent||'').trim();
        const id = el.id || '';
        const role = el.getAttribute('role') || '';
        return (t.length < 20 && t.length > 0) || id || role;
      }).slice(0, 60).map(el => ({
        tag: el.tagName, id: el.id, cls: (el.className||'').toString().slice(0,40),
        text: (el.textContent||'').trim().slice(0,25), role: el.getAttribute('role')
      }));
    }""")
    for e in els:
      if e['text'] or e['id']:
        print(e)
    await page.screenshot(path="tests/fixtures/web_adapter/real-unoh/unoonline-screenshot.png")
    print("screenshot saved")
    await browser.close()


if __name__ == "__main__":
  asyncio.run(main())
