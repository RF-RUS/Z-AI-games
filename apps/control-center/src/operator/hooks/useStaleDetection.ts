import { useState, useEffect } from "react";

export type DataFreshness = "fresh" | "stale" | "degraded" | "empty";

export function useStaleDetection(
  lastUpdateTs: number,
  pollFailed: boolean,
  hasData: boolean,
  thresholdMs = 10000,
): DataFreshness {
  const [freshness, setFreshness] = useState<DataFreshness>("empty");

  useEffect(() => {
    if (!hasData) {
      setFreshness("empty");
      return;
    }
    if (pollFailed) {
      setFreshness("degraded");
      return;
    }
    setFreshness(Date.now() - lastUpdateTs > thresholdMs ? "stale" : "fresh");
  }, [lastUpdateTs, pollFailed, hasData, thresholdMs]);

  useEffect(() => {
    if (!hasData || pollFailed) return;
    const interval = setInterval(() => {
      setFreshness(Date.now() - lastUpdateTs > thresholdMs ? "stale" : "fresh");
    }, 1000);
    return () => clearInterval(interval);
  }, [lastUpdateTs, pollFailed, hasData, thresholdMs]);

  return freshness;
}
