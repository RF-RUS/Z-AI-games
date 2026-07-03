import { useRef, useEffect } from "react";
import StepChip from "./StepChip";
import TraceFilterBar from "./TraceFilterBar";
import JumpToLatest from "./JumpToLatest";
import { TraceStep } from "../../unoApiClient";
import { TraceFilter } from "../hooks/useTraceSelection";

interface Props {
  steps: TraceStep[];
  filteredSteps: TraceStep[];
  selectedStepNum: number | null;
  followLatest: boolean;
  activeFilter: TraceFilter;
  onStepSelect: (stepNum: number) => void;
  onFilterChange: (filter: TraceFilter) => void;
  onJumpToLatest: () => void;
}

export default function TraceTimeline({
  steps, filteredSteps, selectedStepNum, followLatest, activeFilter,
  onStepSelect, onFilterChange, onJumpToLatest,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const followRef = useRef(followLatest);
  followRef.current = followLatest;

  useEffect(() => {
    if (followRef.current && scrollRef.current) {
      scrollRef.current.scrollLeft = scrollRef.current.scrollWidth;
    }
  }, [filteredSteps, followLatest]);

  return (
    <div className="trace-timeline">
      <div className="trace-timeline-header">
        <TraceFilterBar activeFilter={activeFilter} onFilterChange={onFilterChange} />
      </div>

      <div className="trace-scroll" ref={scrollRef}>
        {filteredSteps.length === 0 && (
          <span className="trace-empty-hint">
            {steps.length === 0 ? "Waiting for trace data..." : "No steps match filter"}
          </span>
        )}
        {filteredSteps.map(step => (
          <StepChip
            key={step.step}
            stepNum={step.step}
            phase={step.phase}
            isSelected={selectedStepNum === step.step}
            success={(step.meta?.success as boolean) ?? null}
            onClick={() => onStepSelect(step.step)}
          />
        ))}
      </div>

      <div className="trace-timeline-footer">
        <JumpToLatest followLatest={followLatest} onJump={onJumpToLatest} />
      </div>
    </div>
  );
}
