import ConfidenceBar from "../shared/ConfidenceBar";

interface Props {
  value: number | null;
}

export default function ConfidenceMeter({ value }: Props) {
  return (
    <div className="confidence-meter">
      <span className="confidence-meter-label">Confidence</span>
      <ConfidenceBar value={value} size="sm" showLabel />
    </div>
  );
}
