import { AgentPlan, ExecutionTraceStep, AgentScreenState } from "./operatorStore";

interface Props {
  plan: AgentPlan | null;
  trace: ExecutionTraceStep[];
}

const STATE_ICONS: Record<AgentScreenState, string> = {
  lobby: "🏠",
  menu: "📋",
  in_game: "🎮",
  launcher: "🚀",
  unknown: "❓",
};

const PHASE_ICONS: Record<string, string> = {
  observe: "👁",
  interpret: "🔍",
  candidates: "📋",
  choose: "🧠",
  execute: "⚡",
  verify: "✅",
};

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function StrategyPanel({ plan, trace }: Props) {
  return (
    <div className="strategy-panel">
      <h3>Agent Strategy</h3>

      {plan ? (
        <div className="plan-content">
          <div className="plan-goal">
            <span className="plan-label">Goal</span>
            <span className="plan-value">{plan.goal}</span>
          </div>

          <div className="plan-state">
            <span className="plan-label">Screen</span>
            <span className="plan-value">
              {STATE_ICONS[plan.detectedState]} {plan.detectedState}
            </span>
          </div>

          <div className="plan-hypothesis">
            <span className="plan-label">Reasoning</span>
            <span className="plan-value">{plan.hypothesis}</span>
          </div>

          <div className="plan-next">
            <span className="plan-label">Next</span>
            <span className="plan-value plan-action">{plan.nextAction}</span>
            <span className="plan-why">{plan.whyAction}</span>
          </div>

          {plan.confidence > 0 && (
            <div className="plan-confidence">
              <span className="plan-label">Confidence</span>
              <div className="plan-conf-bar">
                <div
                  className="plan-conf-fill"
                  style={{
                    width: `${Math.round(plan.confidence * 100)}%`,
                    backgroundColor: plan.confidence >= 0.8 ? "#4caf50" : plan.confidence >= 0.5 ? "#ff9800" : "#f44336",
                  }}
                />
              </div>
              <span className="plan-conf-value">{Math.round(plan.confidence * 100)}%</span>
            </div>
          )}

          {plan.blockedReason && (
            <div className="plan-blocked">
              <span className="plan-label">⚠️ Blocked</span>
              <span className="plan-value plan-blocked-text">{plan.blockedReason}</span>
            </div>
          )}

          {plan.lastExecuted && (
            <div className="plan-last">
              <span className="plan-label">Last action</span>
              <span className="plan-value">{plan.lastExecuted}</span>
            </div>
          )}

          {plan.planSteps.length > 0 && (
            <div className="plan-steps">
              <span className="plan-label">Plan</span>
              <ol className="plan-steps-list">
                {plan.planSteps.map((step, i) => (
                  <li key={i} className="plan-step">{step}</li>
                ))}
              </ol>
            </div>
          )}

          {plan.verification && (
            <div className="plan-verification">
              <span className="plan-label">Verification ({plan.verification.action_family})</span>
              <div className="verification-row">
                <span className={`verification-badge verification-${plan.verification.delivery_status}`}>
                  {plan.verification.delivery_status === "delivered" ? "✓" : plan.verification.delivery_status === "failed" ? "✗" : "—"}
                </span>
                <span className="verification-text">
                  Delivery: {plan.verification.delivery_status} · Outcome: {plan.verification.outcome_status}
                </span>
              </div>
              {plan.verification.summary && (
                <div className="verification-summary">
                  <span className="verification-label">Note:</span>
                  <span className="verification-value">{plan.verification.summary}</span>
                </div>
              )}
              {plan.verification.observed_transition && (
                <div className="verification-transition">
                  <span className="verification-label">Coarse transition:</span>
                  <span className="verification-value">{plan.verification.observed_transition}</span>
                </div>
              )}
              {plan.verification.expected_transition && (
                <div className="verification-transition">
                  <span className="verification-label">Expected:</span>
                  <span className="verification-value">{plan.verification.expected_transition}</span>
                </div>
              )}
              {plan.verification.observability_signals && plan.verification.observability_signals.length > 0 && (
                <div className="verification-transition">
                  <span className="verification-label">Signals:</span>
                  <span className="verification-value">{plan.verification.observability_signals.join(", ")}</span>
                </div>
              )}
              {plan.verification.evidence_strength && plan.verification.evidence_strength !== "none" && (
                <div className="verification-transition">
                  <span className="verification-label">Evidence:</span>
                  <span className="verification-value">{plan.verification.evidence_strength}</span>
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        <p className="muted">Waiting for agent plan data...</p>
      )}

      {trace.length > 0 && (
        <div className="trace-content">
          <h4>Execution Trace</h4>
          <div className="trace-timeline">
            {trace.slice(-10).reverse().map((step, i) => (
              <div key={i} className={`trace-step ${step.success === false ? "trace-fail" : ""}`}>
                <span className="trace-phase">{PHASE_ICONS[step.phase] || "•"}</span>
                <span className="trace-msg">{step.message}</span>
                <span className="trace-time">{formatTime(step.ts)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
