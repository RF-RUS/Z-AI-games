import { TraceFilter } from "../hooks/useTraceSelection";

interface Props {
  activeFilter: TraceFilter;
  onFilterChange: (filter: TraceFilter) => void;
}

const FILTERS: Array<{ value: TraceFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "observe", label: "Observe" },
  { value: "execute", label: "Execute" },
  { value: "errors", label: "Errors" },
];

export default function TraceFilterBar({ activeFilter, onFilterChange }: Props) {
  return (
    <div className="trace-filter-bar" role="tablist" aria-label="Trace filter">
      {FILTERS.map(f => (
        <button
          key={f.value}
          type="button"
          className={`trace-filter-btn ${activeFilter === f.value ? "trace-filter-active" : ""}`}
          onClick={() => onFilterChange(f.value)}
          role="tab"
          aria-selected={activeFilter === f.value}
        >
          {f.label}
        </button>
      ))}
    </div>
  );
}
