interface Props {
  activeTab: string;
  onTabChange: (tab: string) => void;
}

const TABS = [
  { id: "summary", label: "Summary", shortcut: "1" },
  { id: "diagnostics", label: "Diagnostics", shortcut: "2" },
  { id: "raw", label: "Raw", shortcut: "3" },
];

export default function RightRailTabs({ activeTab, onTabChange }: Props) {
  return (
    <div className="right-rail-tabs" role="tablist" aria-label="Right panel tabs">
      {TABS.map(tab => (
        <button
          key={tab.id}
          type="button"
          className={`right-tab ${activeTab === tab.id ? "right-tab-active" : ""}`}
          onClick={() => onTabChange(tab.id)}
          role="tab"
          aria-selected={activeTab === tab.id}
          title={`${tab.label} (${tab.shortcut})`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
