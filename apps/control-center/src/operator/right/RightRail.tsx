import { useState, useRef, useEffect } from "react";
import RightRailTabs from "./RightRailTabs";
import SummaryTab from "./SummaryTab";
import DiagnosticsTab from "./DiagnosticsTab";
import RawTab from "./RawTab";
import { Decision, Verification } from "../hooks/useOperatorPolling";
import { FlowStep } from "../../unoApiClient";
import { OperatorEvent, Escalation } from "../../operatorStore";

interface Props {
  decision: Decision;
  verification: Verification;
  escalations: Escalation[];
  events: OperatorEvent[];
  steps: FlowStep[];
  error: string | null;
  diagnostics: Record<string, unknown> | null;
  observation: Record<string, unknown> | null;
  traceMeta: Record<string, unknown> | null;
  onAcknowledgeEscalation: (id: string) => void;
  onTakeControl: () => void;
  onDismissEscalation: (id: string) => void;
  initialTab?: string;
}

export default function RightRail({
  decision, verification, escalations, events, steps, error, diagnostics,
  observation, traceMeta,
  onAcknowledgeEscalation, onTakeControl, onDismissEscalation,
  initialTab = "summary",
}: Props) {
  const [activeTab, setActiveTab] = useState(initialTab);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Preserve scroll position across tab switches
  const scrollPositions = useRef<Record<string, number>>({});

  useEffect(() => {
    if (scrollRef.current) {
      scrollPositions.current[activeTab] = scrollRef.current.scrollTop;
    }
  }, [activeTab]);

  const handleTabChange = (tab: string) => {
    setActiveTab(tab);
    // Restore scroll after render
    requestAnimationFrame(() => {
      if (scrollRef.current && scrollPositions.current[tab] != null) {
        scrollRef.current.scrollTop = scrollPositions.current[tab];
      }
    });
  };

  return (
    <aside className="right-rail" ref={scrollRef} aria-label="Agent details">
      <RightRailTabs activeTab={activeTab} onTabChange={handleTabChange} />

      {/* All tabs mounted, use display to switch — preserves state */}
      <div style={{ display: activeTab === "summary" ? "block" : "none" }}>
        <SummaryTab
          decision={decision}
          verification={verification}
          escalations={escalations}
          onAcknowledge={onAcknowledgeEscalation}
          onTakeControl={onTakeControl}
          onDismissEscalation={onDismissEscalation}
        />
      </div>
      <div style={{ display: activeTab === "diagnostics" ? "block" : "none" }}>
        <DiagnosticsTab
          events={events}
          steps={steps}
          error={error}
          diagnostics={diagnostics}
        />
      </div>
      <div style={{ display: activeTab === "raw" ? "block" : "none" }}>
        <RawTab observation={observation} traceMeta={traceMeta} />
      </div>
    </aside>
  );
}
