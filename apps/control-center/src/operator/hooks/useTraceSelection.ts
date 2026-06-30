import { useState, useEffect, useCallback, useMemo } from "react";
import { TraceStep } from "../../unoApiClient";

export type TraceFilter = "all" | "observe" | "execute" | "errors";

export function useTraceSelection(traceSteps: TraceStep[]) {
  const [selectedStepNum, setSelectedStepNum] = useState<number | null>(null);
  const [followLatest, setFollowLatest] = useState(true);
  const [activeFilter, setActiveFilter] = useState<TraceFilter>("all");

  useEffect(() => {
    if (followLatest && traceSteps.length > 0) {
      const latestNum = traceSteps[traceSteps.length - 1].step;
      setSelectedStepNum(prev => prev !== latestNum ? latestNum : prev);
    }
  }, [traceSteps, followLatest]);

  const selectedStep = useMemo(
    () => traceSteps.find(s => s.step === selectedStepNum) ?? null,
    [traceSteps, selectedStepNum],
  );

  const filteredSteps = useMemo(() => {
    if (activeFilter === "all") return traceSteps;
    if (activeFilter === "errors") return traceSteps.filter(s => s.meta?.success === false);
    return traceSteps.filter(s => s.phase === activeFilter);
  }, [traceSteps, activeFilter]);

  const goToPrevStep = useCallback(() => {
    setFollowLatest(false);
    setSelectedStepNum(prev => {
      if (prev == null) return prev;
      const idx = traceSteps.findIndex(s => s.step === prev);
      return idx > 0 ? traceSteps[idx - 1].step : prev;
    });
  }, [traceSteps]);

  const goToNextStep = useCallback(() => {
    setFollowLatest(false);
    setSelectedStepNum(prev => {
      if (prev == null) return prev;
      const idx = traceSteps.findIndex(s => s.step === prev);
      return idx < traceSteps.length - 1 ? traceSteps[idx + 1].step : prev;
    });
  }, [traceSteps]);

  const jumpToLatest = useCallback(() => {
    setFollowLatest(true);
    if (traceSteps.length > 0) {
      setSelectedStepNum(traceSteps[traceSteps.length - 1].step);
    }
  }, [traceSteps]);

  const selectStep = useCallback((stepNum: number) => {
    setFollowLatest(false);
    setSelectedStepNum(stepNum);
  }, []);

  return {
    selectedStepNum, setSelectedStepNum,
    selectedStep,
    followLatest, setFollowLatest,
    activeFilter, setActiveFilter,
    filteredSteps,
    goToPrevStep, goToNextStep, jumpToLatest, selectStep,
  };
}
