import { DataFreshness } from "../hooks/useStaleDetection";

interface Props {
  freshness: DataFreshness;
  lastUpdateTs: number;
}

export default function FreshnessIndicator({ freshness, lastUpdateTs }: Props) {
  const secondsAgo = Math.round((Date.now() - lastUpdateTs) / 1000);
  const label = secondsAgo < 5 ? "just now" : `${secondsAgo}s ago`;

  const className = freshness === "stale" ? "freshness-stale" :
                    freshness === "degraded" ? "freshness-degraded" :
                    freshness === "empty" ? "freshness-empty" :
                    "freshness-fresh";

  return (
    <span className={`freshness-indicator ${className}`}>
      {freshness === "degraded" ? "Poll failed" :
       freshness === "stale" ? `Stale (${label})` :
       freshness === "empty" ? "Waiting..." :
       label}
    </span>
  );
}
