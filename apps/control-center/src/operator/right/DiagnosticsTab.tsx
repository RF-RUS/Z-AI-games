import EventLog from "./EventLog";
import PipelineDetails from "./PipelineDetails";
import AttachDiagnostics from "./AttachDiagnostics";
import { FlowStep } from "../../unoApiClient";
import { OperatorEvent } from "../../operatorStore";

interface Props {
  events: OperatorEvent[];
  steps: FlowStep[];
  error: string | null;
  diagnostics: Record<string, unknown> | null;
}

export default function DiagnosticsTab({ events, steps, error, diagnostics }: Props) {
  return (
    <div className="tab-content">
      <div className="diag-section">
        <h4>Event Log</h4>
        <EventLog events={events} steps={steps} />
      </div>
      <div className="diag-section">
        <h4>Pipeline Steps</h4>
        <PipelineDetails steps={steps} />
      </div>
      {(error || diagnostics) && (
        <div className="diag-section">
          <h4>Attach Diagnostics</h4>
          <AttachDiagnostics error={error} diagnostics={diagnostics} />
        </div>
      )}
    </div>
  );
}
