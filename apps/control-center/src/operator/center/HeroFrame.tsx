import { useState, useEffect, useRef } from "react";
import HeroImage from "./HeroImage";
import StepBadge from "./StepBadge";
import StepNavControls from "./StepNavControls";
import { TraceStep } from "../../unoApiClient";
import { traceFrameUrl, traceLatestFrameUrl } from "../../unoApiClient";

const SCREENSHOT_POLL_MS = 2000;

interface Props {
  sessionId: string | null;
  selectedStep: TraceStep | null;
  followLatest: boolean;
  adapterType: string | null;
  onPrev: () => void;
  onNext: () => void;
  onToggleFollow: () => void;
}

function buildTraceSrc(sessionId: string, step: TraceStep | null): string | null {
  if (step && step.screenshots.length > 0) {
    const dirName = step.step_dir_name
      || step.path.replace(/\\/g, "/").split("/").pop()
      || "";
    return traceFrameUrl(sessionId, dirName, step.screenshots[0]);
  }
  return traceLatestFrameUrl(sessionId);
}

export default function HeroFrame({ sessionId, selectedStep, followLatest, adapterType, onPrev, onNext, onToggleFollow }: Props) {
  const [dataUrl, setDataUrl] = useState<string | null>(null);
  const [fetching, setFetching] = useState(false);
  // Monotonic generation counter so stale responses cannot overwrite fresher frames
  const genRef = useRef(0);

  // For Windows adapter, poll screenshot JSON and convert to data URL
  useEffect(() => {
    if (adapterType !== "windows" || !sessionId) {
      setDataUrl(null);
      return;
    }

    let cancelled = false;
    const generation = ++genRef.current;
    let fetchCount = 0;

    const fetchScreenshot = async () => {
      try {
        const r = await fetch(`http://127.0.0.1:8100/sessions/${sessionId}/screenshot`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        if (cancelled || generation !== genRef.current) return;
        if (data.data_base64) {
          setDataUrl(`data:image/png;base64,${data.data_base64}`);
        } else {
          setDataUrl(null);
        }
        if (fetchCount === 0) setFetching(false);
      } catch {
        if (!cancelled && generation === genRef.current) {
          if (fetchCount === 0) {
            setDataUrl(null);
            setFetching(false);
          }
        }
      }
      fetchCount++;
    };

    setFetching(true);
    fetchScreenshot();
    const id = setInterval(fetchScreenshot, SCREENSHOT_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [sessionId, adapterType]);

  // For web adapter, use trace pipeline directly
  const traceSrc = adapterType !== "windows" ? buildTraceSrc(sessionId ?? "", selectedStep) : null;
  const src = adapterType === "windows" ? dataUrl : traceSrc;

  return (
    <div className="hero-frame">
      {fetching && !src ? (
        <div className="hero-loading-indicator">Loading evidence...</div>
      ) : (
        <HeroImage src={src} />
      )}
      <div className="hero-bar">
        <StepBadge
          stepNum={selectedStep?.step ?? null}
          phase={selectedStep?.phase ?? null}
          timestamp={null}
        />
        <StepNavControls
          followLatest={followLatest}
          onPrev={onPrev}
          onNext={onNext}
          onToggleFollow={onToggleFollow}
        />
      </div>
    </div>
  );
}
