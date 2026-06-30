import DecisionCard from "./DecisionCard";
import VerificationCard from "./VerificationCard";
import EscalationBanner from "./EscalationBanner";
import { Decision, Verification } from "../hooks/useOperatorPolling";
import { Escalation } from "../../operatorStore";

interface Props {
  decision: Decision;
  verification: Verification;
  escalations: Escalation[];
  onAcknowledge: (id: string) => void;
  onTakeControl: () => void;
  onDismissEscalation: (id: string) => void;
}

export default function SummaryTab({ decision, verification, escalations, onAcknowledge, onTakeControl, onDismissEscalation }: Props) {
  return (
    <div className="tab-content">
      <DecisionCard decision={decision} />
      <VerificationCard verification={verification} />
      <EscalationBanner
        escalations={escalations}
        onAcknowledge={onAcknowledge}
        onTakeControl={onTakeControl}
        onDismiss={onDismissEscalation}
      />
    </div>
  );
}
