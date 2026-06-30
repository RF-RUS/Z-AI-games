import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { checkCdpPort, listCdpTabs, launchDebugChrome, getProfileCompatibility, CdpTab, ProfileCompatibility } from "./unoApiClient";

type Props = {
  selectedTab: CdpTab | null;
  onSelect: (tab: CdpTab | null) => void;
  disabled?: boolean;
  profileId?: string;
};

function isTabCompatible(tab: CdpTab, compatibility: ProfileCompatibility | null): boolean {
  if (!compatibility || compatibility.allowed_domains.length === 0) return true;
  try {
    const url = new URL(tab.url);
    const hostname = url.hostname.toLowerCase();
    return compatibility.allowed_domains.some(
      (d) => hostname === d || hostname.endsWith("." + d)
    );
  } catch {
    return false;
  }
}

function filterTabs(tabs: CdpTab[], query: string): CdpTab[] {
  if (!query.trim()) return tabs;
  const q = query.toLowerCase();
  return tabs.filter(
    (t) =>
      (t.title || "").toLowerCase().includes(q) ||
      (t.url || "").toLowerCase().includes(q)
  );
}

export default function BrowserTabPicker({ selectedTab, onSelect, disabled, profileId }: Props) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tabs, setTabs] = useState<CdpTab[]>([]);
  const [compatibility, setCompatibility] = useState<ProfileCompatibility | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);

  const loadCompatibility = useCallback(async () => {
    if (profileId) {
      const compat = await getProfileCompatibility(profileId);
      setCompatibility(compat);
    }
  }, [profileId]);

  useEffect(() => { loadCompatibility(); }, [loadCompatibility]);

  useEffect(() => {
    if (open) {
      setTimeout(() => searchRef.current?.focus(), 50);
    }
  }, [open]);

  const allFiltered = useMemo(() => filterTabs(tabs, searchQuery), [tabs, searchQuery]);
  const compatibleTabs = useMemo(
    () => allFiltered.filter((t) => isTabCompatible(t, compatibility)),
    [allFiltered, compatibility]
  );
  const incompatibleTabs = useMemo(
    () => allFiltered.filter((t) => !isTabCompatible(t, compatibility)),
    [allFiltered, compatibility]
  );

  const loadTabs = async () => {
    setLoading(true);
    setError(null);
    try {
      const tabList = await listCdpTabs();
      setTabs(tabList);
      setSearchQuery("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleLaunchAndConnect = async () => {
    setLoading(true);
    setError(null);
    try {
      const launchResult = await launchDebugChrome({ url: "about:blank" });
      if (!launchResult.success) {
        setError(launchResult.error || "Failed to launch Chrome");
        setLoading(false);
        return;
      }
      await loadTabs();
      setOpen(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleConnectExisting = async () => {
    setLoading(true);
    setError(null);
    try {
      const check = await checkCdpPort();
      if (!check.available) {
        setError(
          "Chrome debug port not available. Either:\n" +
          "1. Click 'Launch Debug Chrome' above, or\n" +
          "2. Close all Chrome windows, then launch with: chrome --remote-debugging-port=9222"
        );
        setLoading(false);
        return;
      }
      await loadTabs();
      setOpen(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  if (selectedTab) {
    const tabCompatible = isTabCompatible(selectedTab, compatibility);
    return (
      <div>
        <div className="selected-window-summary">
          <div className="selected-window-info">
            <span className="selected-window-title">{selectedTab.title || selectedTab.url}</span>
            <span className="selected-window-detail">{selectedTab.url}</span>
            {!tabCompatible && compatibility && (
              <span className="status-badge status-browser" style={{ marginLeft: 8, background: "#f4433622", color: "#f44336" }}>
                incompatible with {compatibility.display_name}
              </span>
            )}
          </div>
          <button type="button" className="btn btn-secondary btn-sm" disabled={disabled || loading} onClick={handleConnectExisting}>
            {loading ? "Loading..." : "Change tab"}
          </button>
        </div>
        {!tabCompatible && compatibility && (
          <p className="error-text" style={{ fontSize: "12px" }}>
            Selected tab is on a different domain than the {compatibility.display_name} profile expects.
            Change the tab or switch the profile.
          </p>
        )}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", gap: "8px", flexDirection: "column" }}>
      <div style={{ display: "flex", gap: "8px" }}>
        <button type="button" className="btn btn-primary" disabled={disabled || loading} onClick={handleLaunchAndConnect}>
          {loading ? "Launching..." : "Launch Debug Chrome"}
        </button>
        <button type="button" className="btn btn-secondary" disabled={disabled || loading} onClick={handleConnectExisting}>
          {loading ? "Scanning..." : "Connect to Running Chrome"}
        </button>
      </div>

      {open && (
        <div className="window-picker-overlay" onClick={() => setOpen(false)}>
          <div className="window-picker-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="window-picker-header">
              <h3>Select Browser Tab</h3>
              {compatibility && (
                <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                  Compatible with: {compatibility.display_name}
                </span>
              )}
              <button type="button" className="window-picker-close" onClick={() => setOpen(false)}>x</button>
            </div>
            {error && <pre className="error-text" style={{ padding: "0 16px", whiteSpace: "pre-wrap" }}>{error}</pre>}
            {(compatibleTabs.length > 0 || incompatibleTabs.length > 0) && (
              <>
                <input
                  ref={searchRef}
                  type="text"
                  className="window-search-input"
                  placeholder="Search by title or URL..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
                <div className="window-list">
                  {compatibleTabs.map((tab) => (
                    <div
                      key={tab.id}
                      className="window-item"
                      onClick={() => { onSelect(tab); setOpen(false); }}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => { if (e.key === "Enter") { onSelect(tab); setOpen(false); } }}
                    >
                      <div className="window-item-main">
                        <span className="window-item-title">{tab.title || "(untitled)"}</span>
                        <span className="window-item-status">
                          <span className="status-badge status-browser">browser</span>
                        </span>
                      </div>
                      <div className="window-item-detail">{tab.url}</div>
                    </div>
                  ))}
                  {incompatibleTabs.length > 0 && compatibleTabs.length > 0 && (
                    <div style={{ padding: "4px 16px", fontSize: "11px", color: "var(--text-muted)", borderTop: "1px solid var(--border)" }}>
                      Incompatible tabs (wrong domain for selected profile):
                    </div>
                  )}
                  {incompatibleTabs.map((tab) => (
                    <div
                      key={tab.id}
                      className="window-item window-browser"
                      style={{ opacity: 0.5, cursor: "not-allowed" }}
                    >
                      <div className="window-item-main">
                        <span className="window-item-title">{tab.title || "(untitled)"}</span>
                        <span className="window-item-status">
                          <span className="status-badge" style={{ background: "#f4433622", color: "#f44336" }}>wrong domain</span>
                        </span>
                      </div>
                      <div className="window-item-detail">{tab.url}</div>
                    </div>
                  ))}
                </div>
              </>
            )}
            {compatibleTabs.length === 0 && incompatibleTabs.length === 0 && !error && (
              <p className="muted window-picker-empty" style={{ padding: "16px" }}>
                {tabs.length === 0
                  ? "No open browser tabs found. Open a game page in Chrome first."
                  : "No tabs match the selected profile's domain."}
              </p>
            )}
          </div>
        </div>
      )}

      {error && !open && (
        <pre className="error-text" style={{ fontSize: "12px", whiteSpace: "pre-wrap" }}>{error}</pre>
      )}
    </div>
  );
}
