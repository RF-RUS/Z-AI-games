#!/usr/bin/env python3
import asyncio
import json


async def main() -> None:
  from playwright.async_api import async_playwright

  async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page(viewport={"width": 1280, "height": 900})
    await page.goto("https://pizz.uno/singleplayer", timeout=30000)
    await page.wait_for_timeout(2000)
    await page.evaluate("() => document.querySelector('#cookie-consent')?.remove()")
    await page.locator("a.singleplayer-play-game").click(timeout=8000)
    await page.wait_for_timeout(12000)
    info = await page.evaluate("""() => {
      const q = (s) => document.querySelector(s);
      const qa = (s) => [...document.querySelectorAll(s)];
      const top = q('.current-card-wrapper .card, #playedCards .card, div.table-center .card');
      const hand = qa('#player-hand .card, .bottom-hand .card');
      return {
        deck: q('#deck')?.outerHTML?.slice(0, 200),
        played: q('#playedCards')?.innerText?.slice(0, 100),
        top_card: top ? { class: top.className, text: top.innerText, html: top.outerHTML.slice(0, 300) } : null,
        hand_sample: hand.slice(0, 3).map(c => ({ class: c.className, text: c.innerText, playable: c.classList.contains('playable') })),
        turn: q('.player-turn-indicator')?.innerText,
        names: qa('.player-name').map(n => n.innerText),
        uno_btn: qa('button, a').filter(e => /uno/i.test(e.innerText)).map(e => ({ tag: e.tagName, text: e.innerText, id: e.id, cls: e.className })),
        chat: qa('[class*=chat], #chat').map(e => e.id || e.className),
      };
    }""")
    print(json.dumps(info, indent=2))
    await browser.close()


if __name__ == "__main__":
  asyncio.run(main())
