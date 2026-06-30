import { useState, useEffect } from "react";
import HeroImage from "./HeroImage";
import StepBadge from "./StepBadge";
import StepNavControls from "./StepNavControls";
import { TraceStep } from "../../unoApiClient";
import { traceFrameUrl, traceLatestFrameUrl } from "../../unoApiClient";

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

  // For Windows adapter, fetch screenshot JSON and convert to data URL
  useEffect(() => {
    if (adapterType !== "windows" || !sessionId) {
      setDataUrl(null);
      return;
    }

    let cancelled = false;
    setFetching(true);

    fetch(`http://127.0.0.1:8100/sessions/${sessionId}/screenshot`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        if (cancelled) return;
        if (data.data_base64) {
          setDataUrl(`data:image/png;base64,${data.data_base64}`);
        } else {
          setDataUrl(null);
        }
        setFetching(false);
      })
      .catch(() => {
        if (!cancelled) {
          setDataUrl(null);
          setFetching(false);
        }
      });

    return () => { cancelled = true; };
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
