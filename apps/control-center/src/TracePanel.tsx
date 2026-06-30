import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import {
  listTraceSteps,
  traceFrameUrl,
  traceLatestFrameUrl,
  TraceStep,
} from "./unoApiClient";

interface Props {
  sessionId: string | null;
  traceEnabled: boolean;
  onStepSelect?: (step: TraceStep | null) => void;
  selectedStepId?: number | null;
}

const PHASE_LABELS: Record<string, string> = {
  observe: "Observe",
  perceive: "Perceive",
  execute: "Execute",
};

const PHASE_COLORS: Record<string, string> = {
  observe: "#2196F3",
  perceive: "#9C27B0",
  execute: "#FF9800",
};

export default function TracePanel({ sessionId, traceEnabled, onStepSelect, selectedStepId }: Props) {
  const [steps, setSteps] = useState<TraceStep[]>([]);
  // Store selected STEP NUMBER, not object reference
  const [selectedStepNum, setSelectedStepNum] = useState<number | null>(null);
  const [followLatest, setFollowLatest] = useState(true);
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const prevStepsLenRef = useRef(0);

  // Derive selectedStep from step number + current steps array (stable reference)
  const selectedStep = useMemo(() => {
    if (selectedStepNum != null) {
      return steps.find(s => s.step === selectedStepNum) ?? null;
    }
    return null;
  }, [steps, selectedStepNum]);

  // Resolve the hero image URL (stable derivation)
  const heroSrc = useMemo(() => {
    if (selectedStep && selectedStep.screenshots.length > 0) {
      const dirName = selectedStep.step_dir_name
        || selectedStep.path.replace(/\\/g, "/").split("/").pop()
        || "";
      return traceFrameUrl(sessionId!, dirName, selectedStep.screenshots[0]);
    }
    if (sessionId) {
      return traceLatestFrameUrl(sessionId);
    }
    return null;
  }, [selectedStep, sessionId]);

  const fetchSteps = useCallback(async () => {
    if (!sessionId || !traceEnabled) return;
    const data = await listTraceSteps(sessionId);

    setSteps(prevSteps => {
      // Detect if we have new steps
      const hasNewSteps = data.length > prevStepsLenRef.current;
      prevStepsLenRef.current = data.length;

      // If followLatest is on and we have new data, select the latest step
      if (followLatest && data.length > 0) {
        const latestNum = data[data.length - 1].step;
        setSelectedStepNum(prev => {
          // Only update if actually changed (avoids unnecessary re-render)
          if (prev !== latestNum) {
            console.log("[TracePanel] followLatest: selecting step", latestNum);
            return latestNum;
          }
          return prev;
        });
      }

      return data;
    });
  }, [sessionId, traceEnabled, followLatest]);

  useEffect(() => {
    fetchSteps();
    if (followLatest) {
      intervalRef.current = setInterval(fetchSteps, 3000);
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [fetchSteps, followLatest]);

  // Log render state for debugging
  console.log("[TracePanel] render:", {
    stepsLen: steps.length,
    selectedStepNum,
    heroSrc: heroSrc?.slice(-40),
    imageLoaded,
    imageError,
  });

  if (!traceEnabled) {
    return (
      <div className="trace-panel">
        <div className="trace-section-header">Visual Trace</div>
        <div className="trace-off-hint">
          Tracing is off. Set <code>AGENT_SCREENSHOT_TRACE=1</code> to enable.
        </div>
      </div>
    );
  }

  if (!sessionId) {
    return (
      <div className="trace-panel">
        <div className="trace-section-header">Visual Trace</div>
        <div className="trace-off-hint">Start a session to see evidence.</div>
      </div>
    );
  }

  const okCount = steps.filter(s => s.meta?.success === true).length;
  const failCount = steps.filter(s => s.meta?.success === false).length;

  return (
    <div className="trace-panel">
      {/* Section header */}
      <div className="trace-section-header">
        <span>Visual Trace</span>
        <span className="trace-step-count">
          {steps.length} {steps.length === 1 ? "step" : "steps"}
          {failCount > 0 && <span className="trace-fail-badge">{failCount} failed</span>}
        </span>
      </div>

      {/* Hero: large evidence screenshot */}
      <div className="trace-hero">
        {heroSrc ? (
          <img
            key={heroSrc}
            src={heroSrc}
            alt={selectedStep ? `Step ${selectedStep.step}` : "Latest evidence"}
            className={`trace-hero-img ${!imageLoaded ? "trace-hero-loading" : ""}`}
            onLoad={() => {
              console.log("[TracePanel] image loaded:", heroSrc?.slice(-40));
              setImageLoaded(true);
              setImageError(false);
            }}
            onError={(e) => {
              console.warn("[TracePanel] image failed:", heroSrc?.slice(-40));
              setImageError(true);
              setImageLoaded(false);
              // Try latest-frame fallback if step image failed
              const img = e.target as HTMLImageElement;
              const latestUrl = traceLatestFrameUrl(sessionId!);
              if (img.src !== latestUrl) {
                img.src = latestUrl;
              }
            }}
          />
        ) : (
          <div className="trace-hero-placeholder">No evidence available</div>
        )}

        {/* Overlay with current step info */}
        <div className="trace-hero-bar">
          {selectedStep ? (
            <>
              <span
                className="trace-hero-phase"
                style={{ color: PHASE_COLORS[selectedStep.phase] || "#999" }}
              >
                {PHASE_LABELS[selectedStep.phase] || selectedStep.phase}
              </span>
              <span className="trace-hero-step">Step {selectedStep.step}</span>
              {selectedStep.meta?.screen != null && (
                <span className="trace-hero-tag">{String(selectedStep.meta.screen)}</span>
              )}
              {selectedStep.meta?.error != null && (
                <span className="trace-hero-error">{String(selectedStep.meta.error).slice(0, 60)}</span>
              )}
            </>
          ) : (
            <span className="trace-hero-empty-text">Select a step to view its evidence</span>
          )}
        </div>
      </div>

      {/* Step timeline: readable horizontal flow */}
      <div className="trace-timeline">
        <div className="trace-timeline-scroll">
          {steps.length === 0 && (
            <div className="trace-timeline-empty">Waiting for trace data...</div>
          )}
          {steps.map((step) => {
            const ok = step.meta?.success === true;
            const fail = step.meta?.success === false;
            const isSelected = selectedStepNum === step.step;
            const color = fail ? "#f44336" : ok ? "#4caf50" : PHASE_COLORS[step.phase] || "#666";

            return (
              <button
                key={step.step}
                type="button"
                className={[
                  "trace-step-btn",
                  isSelected && "trace-step-selected",
                  fail && "trace-step-fail",
                ].filter(Boolean).join(" ")}
                onClick={() => {
                  console.log("[TracePanel] clicked step:", step.step);
                  setSelectedStepNum(step.step);
                  setFollowLatest(false);
                }}
                title={`Step ${step.step}: ${step.phase}${fail ? " (failed)" : ok ? " (ok)" : ""}`}
              >
                <span className="trace-step-dot" style={{ backgroundColor: color }} />
                <span className="trace-step-name">{step.step}</span>
                <span className="trace-step-phase-name">{(PHASE_LABELS[step.phase] || step.phase).slice(0, 4)}</span>
              </button>
            );
          })}
        </div>
        <div className="trace-timeline-footer">
          <label className="trace-follow-toggle">
            <input
              type="checkbox"
              checked={followLatest}
              onChange={(e) => {
                setFollowLatest(e.target.checked);
                if (e.target.checked && steps.length > 0) {
                  setSelectedStepNum(steps[steps.length - 1].step);
                }
              }}
            />
            <span>Follow latest</span>
          </label>
        </div>
      </div>
    </div>
  );
}
