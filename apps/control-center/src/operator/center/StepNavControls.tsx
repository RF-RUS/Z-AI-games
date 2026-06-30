interface Props {
  followLatest: boolean;
  onPrev: () => void;
  onNext: () => void;
  onToggleFollow: () => void;
}

export default function StepNavControls({ followLatest, onPrev, onNext, onToggleFollow }: Props) {
  return (
    <div className="step-nav-controls">
      <button type="button" className="step-nav-btn" onClick={onPrev} title="Previous step (\u2190)">
        \u25C0
      </button>
      <button type="button" className="step-nav-btn" onClick={onNext} title="Next step (\u2192)">
        \u25B6
      </button>
      <label className="follow-toggle">
        <input type="checkbox" checked={followLatest} onChange={onToggleFollow} />
        <span>Follow</span>
      </label>
    </div>
  );
}
