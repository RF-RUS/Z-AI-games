import { FlowStep } from "../../unoApiClient";

interface Props {
  steps: FlowStep[];
}

const PIPELINE_STEPS = ["observe", "perceive", "legal_actions", "decide", "guard", "execute", "record"];

export default function PipelineDetails({ steps }: Props) {
  return (
    <div className="pipeline-details">
      {PIPELINE_STEPS.map(name => {
        const step = steps.find(s => s.step_name === name);
        const status = step
          ? step.result.success ? "done" : "failed"
          : "pending";
        return (
          <div key={name} className={`pipeline-row pipeline-${status}`}>
            <span className="pipeline-dot" />
            <span className="pipeline-name">{name}</span>
            {step && (
              <span className="pipeline-meta">
                {step.result.latency_ms > 0 && <span className="pipeline-latency">{step.result.latency_ms}ms</span>}
                {!step.result.success && step.result.error && (
                  <span className="pipeline-error">{step.result.error.slice(0, 40)}</span>
                )}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
