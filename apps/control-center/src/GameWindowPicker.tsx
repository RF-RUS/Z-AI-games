import { useState, useMemo, useEffect, useRef } from "react";
import { listWindowsCandidates, WindowCandidate } from "./unoApiClient";
import { SelectedGameWindow } from "./windowAttachPayload";

type Props = {
  selected: SelectedGameWindow | null;
  onSelect: (window: SelectedGameWindow | null) => void;
  disabled?: boolean;
  adapterType?: string;
};

function sortCandidates(candidates: WindowCandidate[]): WindowCandidate[] {
  return [...candidates].sort((a, b) => {
    if (a.is_visible && !b.is_visible) return -1;
    if (!a.is_visible && b.is_visible) return 1;
    if (a.is_focused && !b.is_focused) return -1;
    if (!a.is_focused && b.is_focused) return 1;
    if (!a.is_browser_host && b.is_browser_host) return -1;
    if (a.is_browser_host && !b.is_browser_host) return 1;
    return (a.title || "").localeCompare(b.title || "");
  });
}

function filterCandidates(candidates: WindowCandidate[], query: string): WindowCandidate[] {
  if (!query.trim()) return candidates;
  const q = query.toLowerCase();
  return candidates.filter((c) =>
    (c.title || "").toLowerCase().includes(q) ||
    (c.process_name || "").toLowerCase().includes(q) ||
    (c.class_name || "").toLowerCase().includes(q) ||
    String(c.pid || "").includes(q)
  );
}

function WindowPickerModal({ open, candidates, searchQuery, onSearch, onSelect, onClose }: {
  open: boolean;
  candidates: WindowCandidate[];
  searchQuery: string;
  onSearch: (q: string) => void;
  onSelect: (c: WindowCandidate) => void;
  onClose: () => void;
}) {
  const searchRef = useRef<HTMLInputElement>(null);
  const filtered = useMemo(() => filterCandidates(candidates, searchQuery), [candidates, searchQuery]);

  useEffect(() => {
    if (open) {
      setTimeout(() => searchRef.current?.focus(), 50);
      const handleKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
      window.addEventListener("keydown", handleKey);
      return () => window.removeEventListener("keydown", handleKey);
    }
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="window-picker-overlay" onClick={onClose}>
      <div className="window-picker-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="window-picker-header">
          <h3>Select Game Window</h3>
          <button type="button" className="window-picker-close" onClick={onClose}>×</button>
        </div>
        <input
          ref={searchRef}
          type="text"
          className="window-search-input"
          placeholder="Search by title, process, or PID..."
          value={searchQuery}
          onChange={(e) => onSearch(e.target.value)}
        />
        <div className="window-list">
          {filtered.length === 0 ? (
            <p className="muted window-picker-empty">
              {candidates.length === 0 ? "No windows found." : "No matches."}
            </p>
          ) : (
            filtered.map((c) => (
              <div
                key={c.handle}
                className={`window-item ${c.is_focused ? "window-focused" : ""} ${c.is_browser_host ? "window-browser" : ""}`}
                onClick={() => onSelect(c)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => { if (e.key === "Enter") onSelect(c); }}
              >
                <div className="window-item-main">
                  <span className="window-item-title">{c.title || "(untitled)"}</span>
                  <span className="window-item-status">
                    {c.is_focused && <span className="status-badge status-active">active</span>}
                    {c.is_browser_host && <span className="status-badge status-browser">browser</span>}
                  </span>
                </div>
                <div className="window-item-detail">
                  {c.process_name || c.class_name || "unknown"}
                  {c.pid ? ` · pid ${c.pid}` : ""} · hwnd {c.handle}
                </div>
                {c.attach_warning && <div className="window-item-warning">{c.attach_warning}</div>}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

export default function GameWindowPicker({ selected, onSelect, disabled, adapterType }: Props) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<WindowCandidate[]>([]);
  const [searchQuery, setSearchQuery] = useState("");

  const loadCandidates = async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await listWindowsCandidates();
      const filtered = adapterType === "windows"
        ? rows.filter((c) => !c.is_browser_host)
        : rows;
      setCandidates(sortCandidates(filtered));
      setOpen(true);
      setSearchQuery("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const pick = (candidate: WindowCandidate) => {
    onSelect({
      handle: candidate.handle,
      title: candidate.title,
      pid: candidate.pid,
      process_name: candidate.process_name,
    });
    setOpen(false);
  };

  return (
    <div className="game-window-picker">
      {selected ? (
        <div className="selected-window-summary">
          <div className="selected-window-info">
            <span className="selected-window-title">{selected.title || "(untitled)"}</span>
            <span className="selected-window-detail">
              {selected.process_name || "unknown"} · pid {selected.pid || "?"} · hwnd {selected.handle}
            </span>
          </div>
          <button type="button" className="btn btn-secondary btn-sm" disabled={disabled || loading} onClick={loadCandidates}>
            {loading ? "Loading..." : "Change window"}
          </button>
        </div>
      ) : (
        <button type="button" className="btn btn-secondary" disabled={disabled || loading} onClick={loadCandidates}>
          {loading ? "Scanning windows..." : "Select game window"}
        </button>
      )}
      {error && <p className="error-text">{error}</p>}

      <WindowPickerModal
        open={open}
        candidates={candidates}
        searchQuery={searchQuery}
        onSearch={setSearchQuery}
        onSelect={pick}
        onClose={() => setOpen(false)}
      />
    </div>
  );
}
