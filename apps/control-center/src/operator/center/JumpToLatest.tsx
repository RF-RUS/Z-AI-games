interface Props {
  followLatest: boolean;
  onJump: () => void;
}

export default function JumpToLatest({ followLatest, onJump }: Props) {
  if (followLatest) return null;

  return (
    <button type="button" className="jump-to-latest-btn" onClick={onJump}>
      Jump to latest
    </button>
  );
}
