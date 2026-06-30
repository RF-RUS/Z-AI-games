import { useState, useEffect, useRef } from "react";

interface Props {
  src: string | null;
  alt?: string;
  onLoad?: () => void;
  onError?: () => void;
}

export default function HeroImage({ src, alt = "Agent evidence", onLoad, onError }: Props) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);
  const prevSrcRef = useRef(src);

  useEffect(() => {
    if (src !== prevSrcRef.current) {
      setLoaded(false);
      setError(false);
      prevSrcRef.current = src;
    }
  }, [src]);

  if (!src) {
    return <div className="hero-placeholder">No evidence available</div>;
  }

  return (
    <img
      key={src}
      src={src}
      alt={alt}
      className={`hero-img ${!loaded ? "hero-loading" : ""} ${error ? "hero-error" : ""}`}
      onLoad={() => { setLoaded(true); onLoad?.(); }}
      onError={() => { setError(true); onError?.(); }}
    />
  );
}
