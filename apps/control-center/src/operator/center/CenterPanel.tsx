import HeroFrame from "./HeroFrame";
import TraceTimeline from "./TraceTimeline";
import { TraceStep } from "../../unoApiClient";
import { TraceFilter } from "../hooks/useTraceSelection";

interface Props {
  sessionId: string | null;
  selectedStep: TraceStep | null;
  steps: TraceStep[];
  filteredSteps: TraceStep[];
  selectedStepNum: number | null;
  followLatest: boolean;
  activeFilter: TraceFilter;
  adapterType: string | null;
  onStepSelect: (stepNum: number) => void;
  onFilterChange: (filter: TraceFilter) => void;
  onJumpToLatest: () => void;
  onPrev: () => void;
  onNext: () => void;
  onToggleFollow: () => void;
}

export default function CenterPanel({
  sessionId, selectedStep, steps, filteredSteps, selectedStepNum,
  followLatest, activeFilter, adapterType,
  onStepSelect, onFilterChange, onJumpToLatest, onPrev, onNext, onToggleFollow,
}: Props) {
  return (
    <main className="center-panel">
      <HeroFrame
        sessionId={sessionId}
        selectedStep={selectedStep}
        followLatest={followLatest}
        adapterType={adapterType}
        onPrev={onPrev}
        onNext={onNext}
        onToggleFollow={onToggleFollow}
      />
      <TraceTimeline
        steps={steps}
        filteredSteps={filteredSteps}
        selectedStepNum={selectedStepNum}
        followLatest={followLatest}
        activeFilter={activeFilter}
        onStepSelect={onStepSelect}
        onFilterChange={onFilterChange}
        onJumpToLatest={onJumpToLatest}
      />
    </main>
  );
}
