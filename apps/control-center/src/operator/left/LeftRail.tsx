import GameStateCard from "./GameStateCard";
import AlertStack from "./AlertStack";
import { GameState } from "../hooks/useOperatorPolling";
import { Escalation } from "../../operatorStore";

interface Props {
  gameState: GameState;
  escalations: Escalation[];
  onAcknowledge: (id: string) => void;
  onTakeControl: () => void;
}

export default function LeftRail({ gameState, escalations, onAcknowledge, onTakeControl }: Props) {
  return (
    <aside className="left-rail" aria-label="Game state">
      <GameStateCard gameState={gameState} />
      <AlertStack
        escalations={escalations}
        onAcknowledge={onAcknowledge}
        onTakeControl={onTakeControl}
      />
    </aside>
  );
}
