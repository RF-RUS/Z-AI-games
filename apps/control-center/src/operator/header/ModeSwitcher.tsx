import { ControlMode } from "../../operatorStore";

interface Props {
  mode: ControlMode;
  onModeChange: (mode: ControlMode) => void;
}

export default function ModeSwitcher({ mode, onModeChange }: Props) {
  return (
    <div className="mode-switcher" role="radiogroup" aria-label="Control mode">
      {(["auto", "assist", "manual"] as ControlMode[]).map((m) => (
        <button
          key={m}
          type="button"
          className={`mode-btn ${mode === m ? "mode-btn-active" : ""}`}
          onClick={() => onModeChange(m)}
          role="radio"
          aria-checked={mode === m}
          title={
            m === "auto" ? "Bot plays autonomously" :
            m === "assist" ? "Bot proposes, you confirm" :
            "You play, bot observes"
          }
        >
          {m === "auto" ? "Auto" : m === "assist" ? "Assist" : "Manual"}
        </button>
      ))}
    </div>
  );
}
