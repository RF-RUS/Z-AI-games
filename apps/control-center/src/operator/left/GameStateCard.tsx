import TopCard from "./TopCard";
import HandCards from "./HandCards";
import DirectionIndicator from "./DirectionIndicator";
import TurnIndicator from "./TurnIndicator";
import ScreenStateBadge from "./ScreenStateBadge";
import ConfidenceMeter from "./ConfidenceMeter";
import { GameState } from "../hooks/useOperatorPolling";

interface Props {
  gameState: GameState;
}

export default function GameStateCard({ gameState }: Props) {
  const hasAnyData = gameState.topCard || gameState.handCount != null || gameState.screenState !== "unknown";

  if (!hasAnyData) {
    return (
      <div className="game-state-card game-state-empty">
        <h3>Game State</h3>
        <p className="game-state-hint">Waiting for observation...</p>
      </div>
    );
  }

  return (
    <div className="game-state-card">
      <h3>Game State</h3>

      {gameState.topCard && (
        <TopCard color={gameState.topCard.color} value={gameState.topCard.value} />
      )}

      {gameState.handCards && gameState.handCards.length > 0 ? (
        <HandCards cards={gameState.handCards} />
      ) : gameState.handCount != null ? (
        <div className="game-state-row">
          <span className="game-state-label">Hand</span>
          <span className="game-state-value">{gameState.handCount} cards</span>
        </div>
      ) : null}

      <div className="game-state-details">
        {gameState.direction != null && <DirectionIndicator direction={gameState.direction} />}
        {gameState.isYourTurn != null && <TurnIndicator isYourTurn={gameState.isYourTurn} />}
        <ScreenStateBadge state={gameState.screenState} />
      </div>

      <ConfidenceMeter value={gameState.confidence} />
    </div>
  );
}
