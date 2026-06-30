import { useState } from "react";

interface Props {
  title: string;
  count?: number;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

export default function DrawerSection({ title, count, defaultOpen = false, children }: Props) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="drawer-section">
      <button
        type="button"
        className="drawer-header"
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
      >
        <span>{title}</span>
        {count != null && <span className="drawer-badge">{count}</span>}
        <span className="drawer-chevron">{isOpen ? "\u25B2" : "\u25BC"}</span>
      </button>
      {isOpen && <div className="drawer-content">{children}</div>}
    </div>
  );
}
