interface Props {
  isYourTurn: boolean | null;
}

export default function TurnIndicator({ isYourTurn }: Props) {
  if (isYourTurn == null) return null;

  return (
    <div className={`turn-indicator ${isYourTurn ? "turn-yours" : "turn-opponent"}`}>
      {isYourTurn ? "Your turn" : "Opponent"}
    </div>
  );
}
