import DrawerSection from "./DrawerSection";
import EventLog from "../right/EventLog";
import CopyButton from "../shared/CopyButton";
import { FlowStep } from "../../unoApiClient";
import { OperatorEvent } from "../../operatorStore";

interface Props {
  events: OperatorEvent[];
  steps: FlowStep[];
  observation: Record<string, unknown> | null;
  error: string | null;
  sessionId: string | null;
}

export default function BottomDrawer({ events, steps, observation, error, sessionId }: Props) {
  return (
    <div className="bottom-drawer">
      <DrawerSection title="Event Log" count={events.length + steps.length}>
        <EventLog events={events} steps={steps} />
      </DrawerSection>
      <DrawerSection title="Raw Observation">
        {observation ? (
          <pre className="drawer-json">{JSON.stringify(observation, null, 2)}</pre>
        ) : (
          <p className="drawer-empty">No observation data</p>
        )}
      </DrawerSection>
      <DrawerSection title="Pipeline Steps" count={steps.length}>
        <div className="drawer-pipeline">
          {steps.slice(-10).map((step, i) => (
            <div key={i} className={`drawer-step ${step.result.success ? "step-ok" : "step-fail"}`}>
              <span>{step.step_name}</span>
              {step.result.latency_ms > 0 && <span className="step-latency">{step.result.latency_ms}ms</span>}
              {!step.result.success && step.result.error && <span className="step-error">{step.result.error.slice(0, 50)}</span>}
            </div>
          ))}
        </div>
      </DrawerSection>
      {error && (
        <DrawerSection title="Error Details" count={1} defaultOpen>
          <div className="drawer-error">
            <p>{error}</p>
            <CopyButton text={error} label="Copy error" />
          </div>
        </DrawerSection>
      )}
      {sessionId && (
        <div className="drawer-export">
          <CopyButton text={`curl http://127.0.0.1:8100/sessions/${sessionId}/status`} label="Copy status command" />
        </div>
      )}
    </div>
  );
}
