#!/usr/bin/env python3
"""Find actual card selectors on Pizzuno after game starts."""
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

    print("Navigating to Pizzuno...")
    await page.goto("https://pizz.uno/singleplayer", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    print("Clicking Start Game...")
    start = page.locator("a.singleplayer-play-game")
    if await start.count() > 0:
        await start.click(force=True)
        print("Start Game clicked, waiting for game to load...")
        await page.wait_for_timeout(8000)
    else:
        print("Start Game button not found!")

    result = await page.evaluate("""() => {
        const allEls = document.querySelectorAll('*');
        const interesting = [];
        for (const el of allEls) {
            const cls = el.className;
            const id = el.id;
            const tag = el.tagName;
            if (typeof cls === 'string' && (cls.includes('card') || cls.includes('hand') || cls.includes('play') || cls.includes('deck') || cls.includes('draw') || cls.includes('table') || cls.includes('game'))) {
                interesting.push({
                    tag: tag,
                    id: id || null,
                    classes: cls,
                    childCount: el.children.length,
                    text: el.textContent ? el.textContent.substring(0, 50).trim() : null
                });
            }
            if (id && (id.includes('card') || id.includes('hand') || id.includes('play') || id.includes('deck') || id.includes('draw') || id.includes('table') || id.includes('game'))) {
                interesting.push({
                    tag: tag,
                    id: id,
                    classes: cls || null,
                    childCount: el.children.length,
                    text: el.textContent ? el.textContent.substring(0, 50).trim() : null
                });
            }
        }
        return {
            url: window.location.href,
            interesting: interesting,
            canvasCount: document.querySelectorAll('canvas').length
        };
    }""")

    print(json.dumps(result, indent=2))

    await page.screenshot(path="artifacts/dom-inspect-result.png")
    print("Screenshot saved to artifacts/dom-inspect-result.png")

    await browser.close()
    await pw.stop()

asyncio.run(main())
