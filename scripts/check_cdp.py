import asyncio

import httpx


async def check():
    for i in range(10):
        await asyncio.sleep(1)
        try:
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get("http://127.0.0.1:9222/json/version")
                r.raise_for_status()
                data = r.json()
                print(f"t={i+1}s CDP OK: {data.get('Browser')}")
                return
        except Exception:
            print(f"t={i+1}s waiting...")
    print("CDP UNAVAILABLE after 10s")

asyncio.run(check())
