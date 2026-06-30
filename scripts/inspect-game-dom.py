#!/usr/bin/env python3
"""Find actual DOM elements on running Pizzuno game."""
import asyncio
import json

from playwright.async_api import async_playwright


async def main():
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
    page = await ctx.new_page()

    async def block(route):
        await route.abort()

    await page.route("**/fundingchoicesmessages.google.com/**", block)
    await page.route("**/www.google.com/adsense/**", block)
    await page.route("**/pagead2.googlesyndication.com/**", block)
    await page.route("**/*.doubleclick.net/**", block)
    await page.route("**/www.googletagmanager.com/**", block)

    await page.goto("https://pizz.uno/singleplayer", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    accept = page.locator('button:has-text("Accept Cookies")')
    if await accept.count() > 0:
        await accept.first.click(force=True)
        await page.wait_for_timeout(1000)

    start = page.locator("a.singleplayer-play-game")
    if await start.count() > 0:
        await start.click(force=True)
        await page.wait_for_timeout(8000)

    result = await page.evaluate("""() => {
        const allEls = document.querySelectorAll('*');
        const elements = [];
        for (const el of allEls) {
            const cls = el.className;
            const id = el.id;
            const tag = el.tagName;
            const rect = el.getBoundingClientRect();
            if (rect.width > 50 && rect.height > 50 && rect.top > 400) {
                elements.push({
                    tag: tag,
                    id: id || null,
                    classes: typeof cls === 'string' ? cls : null,
                    rect: {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)},
                    text: el.textContent ? el.textContent.substring(0, 30).trim() : null,
                    childCount: el.children.length
                });
            }
        }
        return {
            url: window.location.href,
            bottomElements: elements.slice(0, 30)
        };
    }""")

    print(json.dumps(result, indent=2))
    await page.screenshot(path="artifacts/game-dom-bottom.png")
    await browser.close()
    await pw.stop()

asyncio.run(main())
