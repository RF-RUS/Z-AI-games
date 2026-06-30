#!/usr/bin/env python3
"""Inspect Pizzuno DOM to find correct card selectors."""
import asyncio

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

    await page.goto("https://pizz.uno/singleplayer", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(3000)

    start = page.locator("a.singleplayer-play-game")
    if await start.count() > 0:
        await start.click(force=True)
        await page.wait_for_timeout(5000)

    result = await page.evaluate("""() => {
        const body = document.body;
        const allElements = body.querySelectorAll('*');
        const tagCounts = {};
        const classSamples = {};
        for (let i = 0; i < allElements.length; i++) {
            const el = allElements[i];
            tagCounts[el.tagName] = (tagCounts[el.tagName] || 0) + 1;
            if (el.className && typeof el.className === 'string' && el.className.length > 0) {
                const classes = el.className.split(' ').filter(c => c.length > 0);
                for (const cls of classes) {
                    if (!classSamples[cls]) classSamples[cls] = el.tagName;
                }
            }
        }
        const bodyHTML = body.innerHTML.substring(0, 3000);
        return {
            url: window.location.href,
            title: document.title,
            elementCount: allElements.length,
            tagCounts: tagCounts,
            classSamples: classSamples,
            bodySnippet: bodyHTML
        };
    }""")

    import json
    print(json.dumps(result, indent=2))
    await browser.close()
    await pw.stop()

asyncio.run(main())
