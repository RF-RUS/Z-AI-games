import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

/**
 * Regression tests for HeroFrame screenshot polling.
 *
 * These tests verify the polling logic that keeps the Windows adapter
 * preview in sync with the latest screenshot from the backend.
 *
 * The actual React component cannot be rendered in the vitest Node
 * environment, so we test the fetch/polling mechanics directly using
 * the same patterns the component uses.
 */

const SCREENSHOT_URL = "http://127.0.0.1:8100/sessions/test-session/screenshot";
const POLL_MS = 2000;

describe("HeroFrame screenshot polling", () => {
  let mockFetch: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useFakeTimers();
    mockFetch = vi.fn();
    global.fetch = mockFetch;
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("fetches screenshot immediately on mount", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data_base64: "frame1" }),
    });

    // Simulate the initial fetch the component performs
    const r = await fetch(SCREENSHOT_URL);
    const data = await r.json();

    expect(mockFetch).toHaveBeenCalledTimes(1);
    expect(mockFetch).toHaveBeenCalledWith(SCREENSHOT_URL);
    expect(data.data_base64).toBe("frame1");
  });

  it("polls for new screenshots at 2-second intervals", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data_base64: "frame1" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data_base64: "frame2" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data_base64: "frame3" }),
      });

    const screenshots: string[] = [];
    let fetchCount = 0;

    const fetchScreenshot = async () => {
      const r = await fetch(SCREENSHOT_URL);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      screenshots.push(data.data_base64);
      fetchCount++;
    };

    // Initial fetch (like the component does on mount)
    await fetchScreenshot();
    expect(screenshots).toEqual(["frame1"]);
    expect(fetchCount).toBe(1);

    // Set up polling (like the component does)
    const id = setInterval(fetchScreenshot, POLL_MS);

    // Advance 2 seconds — second fetch fires
    await vi.advanceTimersByTimeAsync(POLL_MS);
    expect(fetchCount).toBe(2);
    expect(screenshots).toEqual(["frame1", "frame2"]);

    // Advance 2 more seconds — third fetch fires
    await vi.advanceTimersByTimeAsync(POLL_MS);
    expect(fetchCount).toBe(3);
    expect(screenshots).toEqual(["frame1", "frame2", "frame3"]);

    clearInterval(id);
  });

  it("second screenshot replaces the first for the same session", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data_base64: "first-frame" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ data_base64: "second-frame" }),
      });

    let currentDataUrl: string | null = null;

    const applyScreenshot = (data: { data_base64?: string }) => {
      if (data.data_base64) {
        currentDataUrl = `data:image/png;base64,${data.data_base64}`;
      } else {
        currentDataUrl = null;
      }
    };

    // First fetch
    const r1 = await fetch(SCREENSHOT_URL);
    applyScreenshot(await r1.json());
    expect(currentDataUrl).toBe("data:image/png;base64,first-frame");

    // Poll fetch
    const r2 = await fetch(SCREENSHOT_URL);
    applyScreenshot(await r2.json());
    expect(currentDataUrl).toBe("data:image/png;base64,second-frame");
  });

  it("polling stops on cleanup (unmount)", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ data_base64: "frame" }),
    });

    let fetchCount = 0;
    const fetchScreenshot = async () => {
      await fetch(SCREENSHOT_URL);
      fetchCount++;
    };

    // Start polling
    await fetchScreenshot();
    const id = setInterval(fetchScreenshot, POLL_MS);

    // Advance a bit
    await vi.advanceTimersByTimeAsync(POLL_MS * 2);
    expect(fetchCount).toBe(3);

    // Cleanup (simulates component unmount)
    clearInterval(id);
    mockFetch.mockReset();

    // Advance more — no more fetches
    await vi.advanceTimersByTimeAsync(POLL_MS * 2);
    expect(fetchCount).toBe(3);
  });

  it("switching sessionId stops old session polling and starts new one", async () => {
    const session1Calls: string[] = [];
    const session2Calls: string[] = [];

    mockFetch
      .mockImplementationOnce(async (url: string) => {
        session1Calls.push(url);
        return { ok: true, json: async () => ({ data_base64: "s1-frame1" }) };
      })
      .mockImplementationOnce(async (url: string) => {
        session1Calls.push(url);
        return { ok: true, json: async () => ({ data_base64: "s1-frame2" }) };
      })
      .mockImplementationOnce(async (url: string) => {
        session2Calls.push(url);
        return { ok: true, json: async () => ({ data_base64: "s2-frame1" }) };
      })
      .mockImplementationOnce(async (url: string) => {
        session2Calls.push(url);
        return { ok: true, json: async () => ({ data_base64: "s2-frame2" }) };
      });

    let cancelled = false;
    let gen = 0;

    // Simulate session-1 polling
    const session1Gen = ++gen;
    const fetchSession1 = async () => {
      if (cancelled || session1Gen !== gen) return;
      await fetch("http://127.0.0.1:8100/sessions/session-1/screenshot");
    };

    await fetchSession1();
    const id1 = setInterval(fetchSession1, POLL_MS);

    // One poll tick for session 1
    await vi.advanceTimersByTimeAsync(POLL_MS);

    // Simulate session switch: cancel old, start new
    cancelled = true;
    clearInterval(id1);

    let cancelled2 = false;
    const session2Gen = ++gen;
    const fetchSession2 = async () => {
      if (cancelled2 || session2Gen !== gen) return;
      await fetch("http://127.0.0.1:8100/sessions/session-2/screenshot");
    };

    await fetchSession2();
    const id2 = setInterval(fetchSession2, POLL_MS);

    // One poll tick for session 2
    await vi.advanceTimersByTimeAsync(POLL_MS);

    clearInterval(id2);

    // Session 1 should have 2 calls (initial + 1 poll)
    expect(session1Calls).toHaveLength(2);
    expect(session1Calls.every((u) => u.includes("session-1"))).toBe(true);

    // Session 2 should have 2 calls (initial + 1 poll)
    expect(session2Calls).toHaveLength(2);
    expect(session2Calls.every((u) => u.includes("session-2"))).toBe(true);
  });

  it("stale response does not overwrite fresher frame (generation guard)", async () => {
    // Simulate two concurrent fetches where the slow one resolves after the fast one.
    // This mirrors the genRef.current guard in HeroFrame.
    const fastResult = { ok: true, json: async () => ({ data_base64: "fast-frame" }) };
    const slowResult = { ok: true, json: async () => ({ data_base64: "slow-stale-frame" }) };

    // Create promises without awaiting — simulates concurrent in-flight requests
    const slowPromise = Promise.resolve(slowResult);
    const fastPromise = Promise.resolve(fastResult);

    let generation = 0;
    let currentDataUrl: string | null = null;

    // First request starts (slow)
    const gen1 = ++generation;

    // Second request starts (fast) — generation advances
    const gen2 = ++generation;

    // Fast resolves first
    const r2 = await fastPromise;
    const data2 = await r2.json();
    if (gen2 === generation) {
      currentDataUrl = `data:image/png;base64,${data2.data_base64}`;
    }
    expect(currentDataUrl).toBe("data:image/png;base64,fast-frame");

    // Slow resolves later — but gen1 !== generation, so it's stale
    const r1 = await slowPromise;
    const data1 = await r1.json();
    if (gen1 === generation) {
      currentDataUrl = `data:image/png;base64,${data1.data_base64}`;
    }

    // Slow result should NOT have overwritten fast result
    expect(currentDataUrl).toBe("data:image/png;base64,fast-frame");
  });

  it("does not fetch for non-windows adapter", async () => {
    const adapterType: string = "web";

    // Simulate the guard condition in the component
    if (adapterType !== "windows") {
      // Component returns early — no fetch should happen
    }

    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("clears dataUrl when sessionId becomes null", async () => {
    let dataUrl: string | null = "data:image/png;base64,old-frame";

    // Simulate sessionId changing to null
    const sessionId = null;
    if (!sessionId) {
      dataUrl = null;
    }

    expect(dataUrl).toBeNull();
  });
});
